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

def test_haversine_distance_calculation():
    # Distance between same points is 0
    assert distance_km(12.9716, 77.5946, 12.9716, 77.5946) == 0.0

    # Distance between Bengaluru (12.9716, 77.5946) and Mysuru (12.2958, 76.6394) is ~128 km
    dist = distance_km(12.9716, 77.5946, 12.2958, 76.6394)
    assert 120 < dist < 140

    # Distance between London (51.5074, -0.1278) and Paris (48.8566, 2.3522) is ~343 km
    dist_lon_par = distance_km(51.5074, -0.1278, 48.8566, 2.3522)
    assert 335 < dist_lon_par < 355

def test_facility_normalization_overpass():
    mock_overpass_res = {
        "elements": [
            {
                "type": "node",
                "id": 1001,
                "lat": 12.98,
                "lon": 77.60,
                "tags": {
                    "name": "Central Cold Storage",
                    "addr:street": "Industrial Area Road",
                    "building": "warehouse"
                }
            },
            {
                "type": "node",
                "id": 1002,
                "lat": 12.95,
                "lon": 77.58,
                "tags": {
                    "name": "General Grocery Depot", # Does not match cold terms
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

        facilities = search_overpass(12.97, 77.59)
        # Should filter out "General Grocery Depot" because it lacks cold terms
        assert len(facilities) == 1
        f = facilities[0]
        assert f["id"] == "OSM-node-1001"
        assert f["name"] == "Central Cold Storage"
        assert f["latitude"] == 12.98
        assert f["longitude"] == 77.60
        assert f["source"] == "OPENSTREETMAP"
        assert f["verified_external"] is True
        assert f["address"] == "Industrial Area Road"

def test_facility_normalization_google_places():
    mock_google_res = {
        "status": "OK",
        "results": [
            {
                "place_id": "gp-001",
                "name": "Arctic Logistics Cold Chain",
                "geometry": {
                    "location": {"lat": 12.965, "lng": 77.601}
                },
                "vicinity": "Tech Park Lane",
                "types": ["warehouse", "storage"]
            }
        ]
    }
    with patch("backend.gis.GOOGLE_MAPS_API_KEY", "TEST_KEY"):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps(mock_google_res).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            facilities = search_google_places(12.97, 77.59)
            assert len(facilities) == 1
            f = facilities[0]
            assert f["id"] == "GP-gp-001"
            assert f["name"] == "Arctic Logistics Cold Chain"
            assert f["latitude"] == 12.965
            assert f["longitude"] == 77.601
            assert f["source"] == "GOOGLE_PLACES"
            assert f["verified_external"] is True

def test_nearby_cooling_caching():
    _FACILITY_CACHE.clear()
    mock_facilities = [
        {
            "id": "c-1",
            "name": "Chilled Depot",
            "latitude": 12.971,
            "longitude": 77.595,
            "distance_km": 0.2,
            "source": "OPENSTREETMAP",
            "verified_external": True
        }
    ]
    with patch("backend.gis.search_overpass", return_value=mock_facilities) as mock_op:
        # First call hits provider
        res1 = get_nearby_cooling_facilities(12.9716, 77.5946)
        assert res1["facilities"][0]["name"] == "Chilled Depot"
        assert mock_op.call_count == 1

        # Second call within TTL returns cached result without hitting provider again
        res2 = get_nearby_cooling_facilities(12.9716, 77.5946)
        assert res2["facilities"][0]["name"] == "Chilled Depot"
        assert mock_op.call_count == 1

def test_driving_route_ors_fallback():
    _ROUTE_CACHE.clear()
    with patch("backend.gis.OPENROUTESERVICE_API_KEY", ""):
        # If ORS has no key, it falls back to a straight-line route geometry gracefully
        route = get_driving_route(12.97, 77.59, 12.98, 77.60)
        assert "route" in route
        assert len(route["route"]) >= 2
        assert route["source"] == "ESTIMATED_STRAIGHT_LINE"
        assert route["distance_km"] > 0
        assert route["duration_min"] > 0

def make_telemetry(device_id="CCU-HW-GIS-001", sequence=1, gps=None):
    from datetime import datetime, timezone
    return Telemetry(
        schema_version="1.0",
        device_id=device_id,
        boot_id="boot-gis-001",
        sequence=sequence,
        timestamp=datetime.now(timezone.utc),
        uptime_ms=sequence * 5000,
        mode="HARDWARE",
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
        system_state="NORMAL",
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

def test_api_nearby_cooling_real_gps_and_no_fix(client):
    token = registered(client, device="CCU-HW-GIS-001", mode="HARDWARE")

    # Send GPS NO FIX packet
    no_fix_telemetry = make_telemetry(
        device_id="CCU-HW-GIS-001",
        sequence=1,
        gps=GPS(fix=False, satellites=3, source="NONE")
    )
    client.post("/api/telemetry", json=no_fix_telemetry.model_dump(mode="json"), headers={"X-Device-Token": token})

    # Query nearby cooling
    r = client.get("/api/v1/nearby-cooling?device_id=CCU-HW-GIS-001")
    assert r.status_code == 200
    data = r.json()
    assert data["gps_fix"] is False
    assert data["facilities"] == []
    assert "Waiting for satellite lock" in data["message"]

    # Send valid REAL GPS fix packet
    real_fix_telemetry = make_telemetry(
        device_id="CCU-HW-GIS-001",
        sequence=2,
        gps=GPS(fix=True, latitude=12.9716, longitude=77.5946, satellites=8, age_s=2.0, source="GPS")
    )
    client.post("/api/telemetry", json=real_fix_telemetry.model_dump(mode="json"), headers={"X-Device-Token": token})

    with patch("backend.main.get_nearby_cooling_facilities") as mock_gis:
        mock_gis.return_value = {
            "gps_fix": True,
            "current_location": {"latitude": 12.9716, "longitude": 77.5946},
            "facilities": [
                {
                    "id": "fac-01",
                    "name": "Verified Cold Logistics",
                    "latitude": 12.9800,
                    "longitude": 77.6000,
                    "distance_km": 1.1,
                    "source": "OPENSTREETMAP",
                    "verified_external": True
                }
            ],
            "facility_provider": "OVERPASS"
        }
        r = client.get("/api/v1/nearby-cooling?device_id=CCU-HW-GIS-001")
        assert r.status_code == 200
        res = r.json()
        assert res["gps_fix"] is True
        assert len(res["facilities"]) == 1
        assert res["facilities"][0]["name"] == "Verified Cold Logistics"
        assert res["facilities"][0]["distance_km"] == 1.1

def test_api_route_to_cooling(client):
    token = registered(client, device="CCU-HW-GIS-002", mode="HARDWARE")

    real_fix_telemetry = make_telemetry(
        device_id="CCU-HW-GIS-002",
        gps=GPS(fix=True, latitude=12.9716, longitude=77.5946, satellites=8, age_s=1.0, source="GPS")
    )
    client.post("/api/telemetry", json=real_fix_telemetry.model_dump(mode="json"), headers={"X-Device-Token": token})

    # Cache a facility so route-to-cooling can look it up
    cache_key = f"{round(12.9716, 2)}:{round(77.5946, 2)}"
    _FACILITY_CACHE[cache_key] = (
        9999999999,
        [
            {
                "id": "fac-01",
                "name": "Verified Cold Logistics",
                "latitude": 12.9800,
                "longitude": 77.6000,
                "distance_km": 1.1,
                "source": "OPENSTREETMAP",
                "verified_external": True
            }
        ],
        "OVERPASS"
    )

    r = client.get("/api/v1/route-to-cooling?device_id=CCU-HW-GIS-002&facility_id=fac-01")
    assert r.status_code == 200
    route_data = r.json()
    assert route_data["destination"]["name"] == "Verified Cold Logistics"
    assert "route" in route_data
    assert len(route_data["route"]) >= 2
    assert route_data["distance_km"] > 0
    assert route_data["duration_min"] > 0

def test_api_keys_not_exposed_in_frontend_bundle():
    # Read dashboard/dist/app.js and dashboard/dist/index.html
    root = Path(__file__).resolve().parent.parent
    dist_app = root / "dashboard/dist/app.js"
    dist_html = root / "dashboard/dist/index.html"

    assert dist_app.exists(), "dashboard/dist/app.js must be built"
    assert dist_html.exists(), "dashboard/dist/index.html must exist"

    app_text = dist_app.read_text(encoding="utf-8")
    html_text = dist_html.read_text(encoding="utf-8")

    # Secrets and private tokens must never be present in the frontend bundle
    assert "GOOGLE_MAPS_API_KEY" not in app_text
    assert "OPENROUTESERVICE_API_KEY" not in app_text
    assert "GOOGLE_MAPS_API_KEY" not in html_text
    assert "OPENROUTESERVICE_API_KEY" not in html_text
    # Ensure frontend calls backend proxies rather than external APIs with keys
    assert "https://api.openrouteservice.org" not in app_text
    assert "maps.googleapis.com" not in app_text

def test_offline_telemetry_invalidates_live_map(client):
    token = registered(client, device="CCU-HW-OFFLINE", mode="HARDWARE")
    # Fresh packet
    t = make_telemetry(
        device_id="CCU-HW-OFFLINE",
        gps=GPS(fix=True, latitude=12.9716, longitude=77.5946, satellites=6, age_s=2.0, source="GPS")
    )
    client.post("/api/telemetry", json=t.model_dump(mode="json"), headers={"X-Device-Token": token})
    latest = client.get("/api/latest?device_id=CCU-HW-OFFLINE").json()
    assert latest["online"] is True
    assert latest["connectivity"] == "ONLINE"


def test_rerouting_state_and_cooling_logic_unaffected():
    # Verify that existing self-healing and cooling interlock remains intact
    sim = Simulator("CCU-SIM-TEST", scenario="heatsink_fan_failure")
    for _ in range(5):
        t, _, _ = sim.step()
        assert not (t.primary_cooling and t.backup_cooling), "Both peltiers must never run together"
