"""GIS, nearby cooling facility discovery, and driving route calculation.

Supports:
- Google Places API (primary when GOOGLE_MAPS_API_KEY is configured)
- OpenStreetMap / Overpass API (fallback or primary when Google key is absent)
- OpenRouteService Directions API (driving routes when OPENROUTESERVICE_API_KEY is configured)
- In-memory TTL caching to avoid hammering external endpoints
- Haversine straight-line distance calculations via backend.routing.distance_km
"""
import logging, math, time, json
import urllib.request
import urllib.parse
from typing import Any
from backend.routing import distance_km
from backend.config import GOOGLE_MAPS_API_KEY, OPENROUTESERVICE_API_KEY, OPENROUTESERVICE_URL, OVERPASS_API_URL

log = logging.getLogger('cold_chain.gis')

# In-memory caches with timestamps
_FACILITY_CACHE: dict[str, tuple[float, list[dict[str, Any]], str]] = {}
_ROUTE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

FACILITY_CACHE_TTL_S = 600.0  # 10 minutes
ROUTE_CACHE_TTL_S = 300.0     # 5 minutes


def _fetch_url(url: str, headers: dict | None = None, data: bytes | None = None, timeout: float = 12.0) -> dict | None:
    req = urllib.request.Request(url, headers=headers or {'User-Agent': 'ColdChainLogistics/2.0'}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        log.warning(f"GIS external request failed for {url}: {e}")
    return None


def search_google_places(lat: float, lon: float, radius_m: int = 25000) -> list[dict[str, Any]]:
    """Search for real cold storage facilities via Google Places Nearby Search."""
    if not GOOGLE_MAPS_API_KEY:
        return []
    
    query = urllib.parse.urlencode({
        'location': f"{lat},{lon}",
        'radius': radius_m,
        'keyword': 'cold storage OR refrigerated warehouse OR cold chain logistics',
        'key': GOOGLE_MAPS_API_KEY
    })
    url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?{query}"
    res = _fetch_url(url, timeout=10.0)
    if not res or res.get('status') not in ('OK', 'ZERO_RESULTS'):
        return []

    facilities = []
    for place in res.get('results', []):
        loc = place.get('geometry', {}).get('location', {})
        p_lat = loc.get('lat')
        p_lon = loc.get('lng')
        if p_lat is None or p_lon is None:
            continue
        dist = distance_km(lat, lon, p_lat, p_lon)
        facilities.append({
            'id': f"GP-{place.get('place_id', 'unknown')}",
            'name': place.get('name', 'Refrigerated Facility'),
            'latitude': round(p_lat, 6),
            'longitude': round(p_lon, 6),
            'distance_km': round(dist, 2),
            'source': 'GOOGLE_PLACES',
            'verified_external': True,
            'address': place.get('vicinity') or place.get('formatted_address') or 'Location verified via Google Places',
            'place_type': 'refrigerated_warehouse',
            'available': True
        })
    return facilities


def search_overpass(lat: float, lon: float, radius_m: int = 25000) -> list[dict[str, Any]]:
    """Search for real cold storage/warehouse facilities via OpenStreetMap Overpass API."""
    # Query warehouses and cold storage nodes/ways within radius
    overpass_query = f"""
    [out:json][timeout:12];
    (
      node["industrial"="warehouse"](around:{radius_m},{lat},{lon});
      way["industrial"="warehouse"](around:{radius_m},{lat},{lon});
      node["warehouse"="cold_storage"](around:{radius_m},{lat},{lon});
      node["cold_storage"](around:{radius_m},{lat},{lon});
      node["building"="warehouse"](around:{radius_m},{lat},{lon});
      way["building"="warehouse"](around:{radius_m},{lat},{lon});
    );
    out center 35;
    """
    data = overpass_query.encode('utf-8')
    res = _fetch_url(OVERPASS_API_URL, data=data, timeout=15.0)
    if not res or 'elements' not in res:
        return []

    cold_keywords = ('cold', 'storage', 'freeze', 'chiller', 'refrigerat', 'ice', 'perishable', 'hvac')
    facilities = []
    for el in res.get('elements', []):
        tags = el.get('tags', {})
        name = tags.get('name') or tags.get('operator') or tags.get('description') or ''
        desc = tags.get('description', '')

        # Check relevance: explicitly marked cold storage or has matching keywords in name/tags
        is_cold = (
            'cold_storage' in tags or
            tags.get('warehouse') == 'cold_storage' or
            any(k in name.lower() for k in cold_keywords) or
            any(k in desc.lower() for k in cold_keywords)
        )
        if not is_cold:
            continue

        c_lat = el.get('lat') or el.get('center', {}).get('lat')
        c_lon = el.get('lon') or el.get('center', {}).get('lon')
        if c_lat is None or c_lon is None:
            continue

        display_name = name or f"Warehouse Facility ({tags.get('industrial') or tags.get('building') or 'Storage'})"
        dist = distance_km(lat, lon, c_lat, c_lon)
        addr_parts = [tags.get('addr:street'), tags.get('addr:city'), tags.get('addr:postcode')]
        addr_str = ', '.join([p for p in addr_parts if p]) or tags.get('addr:full') or 'Location verified via OpenStreetMap'

        facilities.append({
            'id': f"OSM-{el.get('type','node')}-{el.get('id', 0)}",
            'name': display_name,
            'latitude': round(c_lat, 6),
            'longitude': round(c_lon, 6),
            'distance_km': round(dist, 2),
            'source': 'OPENSTREETMAP',
            'verified_external': True,
            'address': addr_str,
            'place_type': tags.get('industrial') or tags.get('building') or 'refrigerated_warehouse',
            'available': True
        })
    return facilities


def get_nearby_cooling_facilities(lat: float, lon: float, radius_km: float = 30.0) -> dict[str, Any]:
    """Retrieve nearby verified cold storage facilities with caching and provider fallback."""
    now = time.time()
    cache_key = f"{round(lat, 2)}:{round(lon, 2)}"
    if cache_key in _FACILITY_CACHE:
        cached_time, cached_facilities, provider = _FACILITY_CACHE[cache_key]
        if now - cached_time < FACILITY_CACHE_TTL_S:
            return {
                'facilities': cached_facilities,
                'provider': provider,
                'cached': True,
                'radius_km': radius_km
            }

    facilities = []
    provider = "NONE"

    # 1. Try Google Places if configured
    if GOOGLE_MAPS_API_KEY:
        try:
            facilities = search_google_places(lat, lon, int(radius_km * 1000))
            if facilities:
                provider = "GOOGLE_PLACES"
        except Exception as e:
            log.warning(f"Google Places search error: {e}")

    # 2. Fallback to OpenStreetMap / Overpass
    if not facilities:
        try:
            facilities = search_overpass(lat, lon, int(radius_km * 1000))
            if facilities:
                provider = "OPENSTREETMAP"
        except Exception as e:
            log.warning(f"Overpass search error: {e}")

    # Sort ascending by straight-line distance
    facilities.sort(key=lambda f: f['distance_km'])

    _FACILITY_CACHE[cache_key] = (now, facilities, provider)
    return {
        'facilities': facilities,
        'provider': provider,
        'cached': False,
        'radius_km': radius_km
    }


def get_driving_route(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> dict[str, Any]:
    """Calculate driving route to target facility via OpenRouteService, with straight-line fallback."""
    now = time.time()
    cache_key = f"{round(origin_lat, 4)},{round(origin_lon, 4)}->{round(dest_lat, 4)},{round(dest_lon, 4)}"
    if cache_key in _ROUTE_CACHE:
        cached_time, cached_route = _ROUTE_CACHE[cache_key]
        if now - cached_time < ROUTE_CACHE_TTL_S:
            return {**cached_route, 'cached': True}

    straight_dist = distance_km(origin_lat, origin_lon, dest_lat, dest_lon)
    route_result = None

    if OPENROUTESERVICE_API_KEY:
        try:
            # Clean API key in case full query or URL was provided in environment
            clean_key = OPENROUTESERVICE_API_KEY.split('&')[0].split('?api_key=')[-1].strip()
            
            # Method 1: GET request with API key query parameter (supported by HeiGIT / ORS)
            get_query = urllib.parse.urlencode({
                'api_key': clean_key,
                'start': f"{origin_lon},{origin_lat}",
                'end': f"{dest_lon},{dest_lat}"
            })
            get_url = f"{OPENROUTESERVICE_URL}?{get_query}"
            res = _fetch_url(get_url, timeout=9.0)

            # Method 2: POST request to api.openrouteservice.org fallback if GET did not return routes
            if not res or ('features' not in res and 'routes' not in res):
                post_url = "https://api.openrouteservice.org/v2/directions/driving-car"
                payload = json.dumps({
                    "coordinates": [[origin_lon, origin_lat], [dest_lon, dest_lat]]
                }).encode('utf-8')
                headers = {
                    "Authorization": clean_key,
                    "Content-Type": "application/json"
                }
                res = _fetch_url(post_url, headers=headers, data=payload, timeout=8.0)

            # Parse GeoJSON format (returned by GET / HeiGIT)
            if res and 'features' in res and len(res['features']) > 0:
                feat = res['features'][0]
                summary = feat.get('properties', {}).get('summary', {})
                geom = feat.get('geometry', {})
                raw_coords = geom.get('coordinates', [])
                coords = [[p[1], p[0]] for p in raw_coords if len(p) >= 2]
                if coords:
                    route_result = {
                        'distance_km': round(summary.get('distance', straight_dist * 1000) / 1000.0, 2),
                        'duration_min': round(summary.get('duration', straight_dist * 1.5 * 60) / 60.0, 1),
                        'route': coords,
                        'source': 'OPENROUTESERVICE',
                        'road_route_available': True,
                        'status': 'OK'
                    }

            # Parse JSON routes format (returned by POST / api.openrouteservice.org)
            elif res and 'routes' in res and len(res['routes']) > 0:
                ors_route = res['routes'][0]
                summary = ors_route.get('summary', {})
                geom = ors_route.get('geometry')
                
                coords = []
                if isinstance(geom, dict) and 'coordinates' in geom:
                    coords = [[p[1], p[0]] for p in geom['coordinates']]
                elif isinstance(geom, list):
                    coords = [[p[1], p[0]] for p in geom]

                if coords:
                    route_result = {
                        'distance_km': round(summary.get('distance', straight_dist * 1000) / 1000.0, 2),
                        'duration_min': round(summary.get('duration', straight_dist * 1.5 * 60) / 60.0, 1),
                        'route': coords,
                        'source': 'OPENROUTESERVICE',
                        'road_route_available': True,
                        'status': 'OK'
                    }
        except Exception as e:
            log.warning(f"OpenRouteService routing error: {e}")

    # Fallback to straight-line connection if OpenRouteService is unavailable or unconfigured
    if not route_result:
        # Estimated driving time at 40 km/h average cold-chain speed
        duration_est = round((straight_dist / 40.0) * 60.0, 1)
        route_result = {
            'distance_km': round(straight_dist, 2),
            'duration_min': duration_est,
            'route': [[origin_lat, origin_lon], [dest_lat, dest_lon]],
            'source': 'ESTIMATED_STRAIGHT_LINE',
            'road_route_available': False,
            'status': 'ROUTE_ESTIMATED'
        }

    _ROUTE_CACHE[cache_key] = (now, route_result)
    return {**route_result, 'cached': False}
