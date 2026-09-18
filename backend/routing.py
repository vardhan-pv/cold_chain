"""Offline, straight-line facility ranking. No road ETA or cargo-safety promise."""
import math

# Original project catalogue, with canonical field names. All facilities are fictional.
DEMO_WAREHOUSES = [{'warehouse_id': 'SIM-WH-001',
  'name': 'Simulated Cold Storage Alpha',
  'latitude': 12.915,
  'longitude': 77.64,
  'available': True,
  'capacity': 500.0,
  'minimum_temperature': 2.0,
  'maximum_temperature': 8.0,
  'source': 'SIMULATED'},
 {'warehouse_id': 'SIM-WH-002',
  'name': 'Simulated Cold Storage Beta',
  'latitude': 12.875,
  'longitude': 77.67,
  'available': True,
  'capacity': 250.0,
  'minimum_temperature': 0.0,
  'maximum_temperature': 10.0,
  'source': 'SIMULATED'},
 {'warehouse_id': 'SIM-WH-003',
  'name': 'Simulated Cold Storage Gamma',
  'latitude': 12.94,
  'longitude': 77.69,
  'available': True,
  'capacity': 1000.0,
  'minimum_temperature': -5.0,
  'maximum_temperature': 5.0,
  'source': 'SIMULATED'},
 {'warehouse_id': 'SIM-WH-004',
  'name': 'Simulated Cold Storage Delta',
  'latitude': 12.89,
  'longitude': 77.61,
  'available': False,
  'capacity': 700.0,
  'minimum_temperature': 2.0,
  'maximum_temperature': 8.0,
  'source': 'SIMULATED'},
 {'warehouse_id': 'SIM-WH-005',
  'name': 'Simulated Cold Storage Epsilon',
  'latitude': 12.86,
  'longitude': 77.63,
  'available': True,
  'capacity': 0.0,
  'minimum_temperature': 2.0,
  'maximum_temperature': 8.0,
  'source': 'SIMULATED'}]

def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0, 1-a)))

def reroute(t, warehouses, required_min=5.0, required_max=8.0, capacity=100, radius=100):
    common = {'location_source': t.gps.source, 'mode': t.mode,
        'method': 'HAVERSINE_STRAIGHT_LINE', 'road_route_available': False,
        'required_temperature_min': required_min, 'required_temperature_max': required_max,
        'required_capacity_kg': capacity, 'capacity_unit': 'kg',
        'selected': None, 'candidates': []}
    if not t.gps.fix:
        return {**common, 'status': 'NO_GPS_FIX', 'reason': 'No fresh position; no destination selected'}
    allowed = 'SIMULATED' if t.mode == 'SIMULATION' else 'VERIFIED'
    for w in warehouses:
        if (w['source'] == allowed and w['available'] and w['capacity'] >= capacity and
                w['minimum_temperature'] <= required_min and w['maximum_temperature'] >= required_max):
            d = distance_km(t.gps.latitude, t.gps.longitude, w['latitude'], w['longitude'])
            if d <= radius:
                common['candidates'].append({**w, 'distance_km': round(d, 3)})
    common['candidates'].sort(key=lambda w: (w['distance_km'], w['warehouse_id']))
    if common['candidates']:
        common['selected'] = common['candidates'][0]
        return {**common, 'status': 'SELECTED', 'reason': 'Nearest compatible available facility by straight-line distance'}
    return {**common, 'status': 'NO_COMPATIBLE_FACILITY', 'reason': 'No matching facility within configured radius'}
