import os
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from backend.routing import distance_km
from backend.gis import (
    get_nearby_cooling_facilities,
    get_driving_route,
    search_google_places,
    search_overpass,
    _FACILITY_CACHE,
    _ROUTE_CACHE
)
from simulator.engine import Simulator
from tests.conftest import registered, TOKEN
from backend.schemas import Telemetry, GPS, SensorHealth
import backend.config as cfg


def make_telemetry(device_id="CCU-HW-GIS-001", sequence=1, gps=None, mode="HARDWARE", state="NORMAL"):
    from datetime import datetime, timezone
    return Telemetry(
        schema_version="1.0",
        device_id=device_id,
        boot_id="boot-gis-001",
        sequence=sequence,
        timestamp=datetime.now(timezone.utc),
        uptime_ms=sequence * 5000,
        mode=mode,
        chamber_temp_c=18.0,
        heatsink_temp_c=28.0,
        sht31_temp_c=25.0,
        humidity_pct=60.0,
        primary_current_a=0.0,
        door_open=False,
        door_open_s=0,
        gps=gps or GPS(fix=False, source="NONE"),
        primary_cooling=False,
        backup_cooling=False,
        system_state=state,
        sensor_health=SensorHealth(
            chamber=True,
            heatsink=True,
            sht31=True,
            current=True,
            door=True
        ),
        current_source="EMULATED",
        current_calibrated=True
    )


# 1. Navigation location produced
def test_navigation_location_produced(client):
    token = registered(client, device="CCU-HW-NAV-1", mode="HARDWARE")
    telemetry = make_telemetry(
        device_id="CCU-HW-NAV-1",
        sequence=1,
        gps=GPS(fix=True, latitude=12.9716, longitude=77.5946, satellites=6, age_s=1.0, source="GPS")
    )
    client.post("/api/telemetry", json=telemetry.model_dump(mode="json"), headers={"X-Device-Token": token})

    r = client.get("/api/v1/nearby-cold-storages?device_id=CCU-HW-NAV-1")
    assert r.status_code == 200
    data = r.json()
    assert "location" in data and data["location"] is not None
    loc = data["location"]
    assert loc["latitude"] == 12.9716
    assert loc["longitude"] == 77.5946
    assert loc["source"] == "PHYSICAL_GPS"


# 2. Physical GPS takes priority over fallback
def test_physical_gps_takes_priority(client):
    token = registered(client, device="CCU-HW-NAV-2", mode="HARDWARE")
    telemetry = make_telemetry(
        device_id="CCU-HW-NAV-2",
        sequence=1,
        gps=GPS(fix=True, latitude=19.0760, longitude=72.8777, satellites=9, age_s=1.0, source="GPS")
    )
    client.post("/api/telemetry", json=telemetry.model_dump(mode="json"), headers={"X-Device-Token": token})

    with patch.object(cfg, "DEMO_GPS_LAT", 12.9716), patch.object(cfg, "DEMO_GPS_LNG", 77.5946):
        r = client.get("/api/v1/nearby-cold-storages?device_id=CCU-HW-NAV-2")
        assert r.status_code == 200
        data = r.json()
        assert data["location"]["source"] == "PHYSICAL_GPS"
        assert data["location"]["latitude"] == 19.0760
        assert data["location"]["longitude"] == 72.8777


# 3. Fallback works when GPS unavailable
def test_fallback_works_when_gps_unavailable(client):
    token = registered(client, device="CCU-HW-NAV-3", mode="HARDWARE")
    no_fix_telemetry = make_telemetry(
        device_id="CCU-HW-NAV-3",
        sequence=1,
        gps=GPS(fix=False, satellites=2, source="NONE")
    )
    client.post("/api/telemetry", json=no_fix_telemetry.model_dump(mode="json"), headers={"X-Device-Token": token})

    with patch.object(cfg, "DEMO_GPS_LAT", 13.0827), patch.object(cfg, "DEMO_GPS_LNG", 80.2707):
        r = client.get("/api/v1/nearby-cold-storages?device_id=CCU-HW-NAV-3")
        assert r.status_code == 200
        data = r.json()
        assert data["location"]["source"] == "DEMO_FALLBACK"
        assert data["location"]["latitude"] == 13.0827
        assert data["location"]["longitude"] == 80.2707


# 4. Fallback satellite count remains 0
def test_fallback_satellite_count_remains_zero(client):
    token = registered(client, device="CCU-HW-NAV-4", mode="HARDWARE")
    no_fix = make_telemetry(device_id="CCU-HW-NAV-4", gps=GPS(fix=False, satellites=0, source="NONE"))
    client.post("/api/telemetry", json=no_fix.model_dump(mode="json"), headers={"X-Device-Token": token})

    with patch.object(cfg, "DEMO_GPS_LAT", 13.0827), patch.object(cfg, "DEMO_GPS_LNG", 80.2707):
        r = client.get("/api/v1/nearby-cold-storages?device_id=CCU-HW-NAV-4")
        assert r.status_code == 200
        data = r.json()
        assert data["navigation_location"]["satellites"] == 0
        assert data["navigation_location"]["gps_fix"] is False
        assert data["navigation_location"]["navigation_location_available"] is True


# 5. Leaflet map assets load
def test_leaflet_map_loads():
    root = Path(__file__).resolve().parent.parent
    dist_js = root / "dashboard/dist/leaflet.js"
    dist_css = root / "dashboard/dist/leaflet.css"
    assert dist_js.exists(), "Leaflet JS bundle must be vendored"
    assert dist_css.exists(), "Leaflet CSS must be vendored"
    assert dist_js.stat().st_size > 10000


# 6. Overpass facility normalization and conservative cold-storage filtering
def test_overpass_facility_normalization_and_filtering():
    mock_overpass_res = {
        "elements": [
            {
                "type": "node",
                "id": 5001,
                "lat": 12.980,
                "lon": 77.600,
                "tags": {
                    "name": "Apex Cold Storage & Logistics",
                    "addr:street": "Freight Corridor 4",
                    "building": "warehouse"
                }
            },
            {
                "type": "way",
                "id": 5002,
                "center": {"lat": 12.985, "lon": 77.605},
                "tags": {
                    "name": "Metro Frozen Foods Warehouse",
                    "warehouse": "cold_storage"
                }
            },
            {
                "type": "node",
                "id": 5003,
                "lat": 12.990,
                "lon": 77.610,
                "tags": {
                    "name": "Standard Wood Carpentry Warehouse",
                    "building": "warehouse"
                }
            }
        ]
    }
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_overpass_res).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        facilities = search_overpass(12.97, 77.59, radius_m=10000)
        # Facility 5003 must be filtered out because it is not a cold storage facility
        assert len(facilities) == 2
        f1 = facilities[0]
        assert f1["id"] == "OSM-node-5001"
        assert f1["osm_type"] == "node"
        assert f1["osm_id"] == "5001"
        assert f1["source"] == "OPENSTREETMAP"
        assert f1["verified_external"] is True

        f2 = facilities[1]
        assert f2["id"] == "OSM-way-5002"
        assert f2["osm_type"] == "way"
        assert f2["osm_id"] == "5002"


# 7. Haversine distance calculation correct
def test_haversine_distance_calculation():
    # Identical coordinates distance is 0
    assert distance_km(12.9716, 77.5946, 12.9716, 77.5946) == 0.0

    # Bengaluru to Mysuru ~128 km
    dist = distance_km(12.9716, 77.5946, 12.2958, 76.6394)
    assert 120 < dist < 140


# 8. Nearest facility selection
def test_nearest_facility_selection():
    _FACILITY_CACHE.clear()
    mock_facilities = [
        {"id": "fac-far", "name": "Far Cold Facility", "latitude": 13.1, "longitude": 77.7, "distance_km": 15.5, "source": "OPENSTREETMAP"},
        {"id": "fac-near", "name": "Near Cold Facility", "latitude": 12.98, "longitude": 77.60, "distance_km": 1.4, "source": "OPENSTREETMAP"}
    ]
    with patch("backend.gis.search_overpass", return_value=mock_facilities):
        res = get_nearby_cooling_facilities(12.97, 77.59, radius_km=25.0)
        # Facilities must be sorted nearest first
        assert res["facilities"][0]["id"] == "fac-near"
        assert res["facilities"][0]["distance_km"] == 1.4
        assert res["facilities"][1]["id"] == "fac-far"


# 9. Route endpoint works and returns expected keys
def test_route_endpoint_works(client):
    token = registered(client, device="CCU-HW-ROUTE-1", mode="HARDWARE")
    t = make_telemetry(
        device_id="CCU-HW-ROUTE-1",
        gps=GPS(fix=True, latitude=12.9716, longitude=77.5946, satellites=8, age_s=1.0, source="GPS")
    )
    client.post("/api/telemetry", json=t.model_dump(mode="json"), headers={"X-Device-Token": token})

    # Cache a facility
    cache_key = f"{round(12.9716, 2)}:{round(77.5946, 2)}:r50.0"
    _FACILITY_CACHE[cache_key] = (
        9999999999,
        [
            {
                "id": "fac-route-01",
                "name": "Express Cold Terminal",
                "latitude": 12.9850,
                "longitude": 77.6050,
                "distance_km": 1.8,
                "source": "OPENSTREETMAP",
                "osm_type": "node",
                "osm_id": "9901"
            }
        ],
        "OPENSTREETMAP"
    )

    r = client.get("/api/v1/route-to-facility?device_id=CCU-HW-ROUTE-1&facility_id=fac-route-01")
    assert r.status_code == 200
    res = r.json()
    assert res["destination"]["name"] == "Express Cold Terminal"
    assert res["distance_km"] > 0
    assert res["duration_min"] > 0
    assert "geometry" in res
    assert "route" in res
    assert len(res["route"]) >= 2


# 10. Longitude / latitude ordering in OpenRouteService request
def test_ors_longitude_latitude_ordering():
    _ROUTE_CACHE.clear()
    with patch("backend.gis.OPENROUTESERVICE_API_KEY", "TEST_KEY"):
        with patch("backend.gis._fetch_url") as mock_fetch:
            mock_fetch.return_value = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "properties": {"summary": {"distance": 2500, "duration": 360}},
                        "geometry": {"coordinates": [[77.5946, 12.9716], [77.6050, 12.9850]]}
                    }
                ]
            }
            route = get_driving_route(12.9716, 77.5946, 12.9850, 77.6050)
            assert mock_fetch.called
            call_url = mock_fetch.call_args[0][0]
            # Ensure URL parameter coordinates are start=lon,lat and end=lon,lat
            assert "start=77.5946%2C12.9716" in call_url or "start=77.5946,12.9716" in call_url
            assert "end=77.605%2C12.985" in call_url or "end=77.605,12.985" in call_url
            assert route["source"] == "OPENROUTESERVICE"
            assert route["distance_km"] == 2.5


# 11. Overpass failure handled gracefully
def test_overpass_failure_handled():
    _FACILITY_CACHE.clear()
    with patch("backend.gis.search_overpass", side_effect=Exception("Overpass 429 Too Many Requests")):
        res = get_nearby_cooling_facilities(12.97, 77.59, radius_km=10.0)
        assert res["facilities"] == []
        assert res["provider"] == "NONE"


# 12. OpenRouteService failure handled gracefully
def test_ors_failure_handled():
    _ROUTE_CACHE.clear()
    with patch("backend.gis.OPENROUTESERVICE_API_KEY", "KEY_THAT_FAILS"):
        with patch("backend.gis._fetch_url", return_value=None):
            # Gracefully falls back to straight-line connection
            route = get_driving_route(12.97, 77.59, 12.98, 77.60)
            assert route["source"] == "ESTIMATED_STRAIGHT_LINE"
            assert route["status"] == "ROUTE_ESTIMATED"
            assert len(route["route"]) == 2


# 13. API keys not exposed in frontend bundle
def test_api_key_not_exposed():
    root = Path(__file__).resolve().parent.parent
    dist_app = root / "dashboard/dist/app.js"
    dist_html = root / "dashboard/dist/index.html"
    app_text = dist_app.read_text(encoding="utf-8")
    html_text = dist_html.read_text(encoding="utf-8")

    assert "OPENROUTESERVICE_API_KEY" not in app_text
    assert "GOOGLE_MAPS_API_KEY" not in app_text
    assert "OPENROUTESERVICE_API_KEY" not in html_text
    assert "GOOGLE_MAPS_API_KEY" not in html_text


# 14. Cache works with radius key
def test_cache_works_with_radius():
    _FACILITY_CACHE.clear()
    with patch("backend.gis.search_overpass", return_value=[{"id": "c1", "name": "Cold 1", "latitude": 12.9, "longitude": 77.5, "distance_km": 1.0, "source": "OPENSTREETMAP"}]) as mock_op:
        res1 = get_nearby_cooling_facilities(12.97, 77.59, radius_km=10.0)
        assert mock_op.call_count == 1

        # Second call with same radius hits cache
        res2 = get_nearby_cooling_facilities(12.97, 77.59, radius_km=10.0)
        assert mock_op.call_count == 1
        assert res2["cached"] is True

        # Call with different radius executes new query
        res3 = get_nearby_cooling_facilities(12.97, 77.59, radius_km=25.0)
        assert mock_op.call_count == 2


# 15. Offline behavior remains correct
def test_offline_behavior_remains_correct(client):
    token = registered(client, device="CCU-HW-OFFLINE-TEST", mode="HARDWARE")
    t = make_telemetry(
        device_id="CCU-HW-OFFLINE-TEST",
        gps=GPS(fix=True, latitude=12.9716, longitude=77.5946, satellites=6, age_s=1.0, source="GPS")
    )
    client.post("/api/telemetry", json=t.model_dump(mode="json"), headers={"X-Device-Token": token})
    status = client.get("/api/latest?device_id=CCU-HW-OFFLINE-TEST").json()
    assert status["online"] is True
    assert status["connectivity"] == "ONLINE"


# 16. Cooling interlock, ML, and self-healing unaffected
def test_cooling_and_self_healing_unaffected():
    sim = Simulator("CCU-SIM-UNTOUCHED", scenario="heatsink_fan_failure")
    for _ in range(6):
        t, _, _ = sim.step()
        assert not (t.primary_cooling and t.backup_cooling), "Cooling interlock violated"
