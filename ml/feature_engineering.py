"""Causal features only. The exact same code is used for training and serving."""
import math
from statistics import mean, pstdev
from backend.schemas import Telemetry

FEATURE_VERSION = 'peltier-v1'
FEATURES = ['chamber_temp_c', 'heatsink_temp_c', 'sht31_temp_c', 'humidity_pct',
    'primary_current_a', 'door_open', 'primary_cooling', 'backup_cooling',
    'thermal_delta_c', 'chamber_rate_c_min', 'current_mean_a', 'temperature_std_c',
    'door_open_s', 'current_ratio', 'temperature_mean_c']

def features_for(history: list[Telemetry]):
    if not history:
        return None
    t = history[-1]
    if not all(t.sensor_health.model_dump().values()):
        return None
    now = t.timestamp.timestamp()
    window = [x for x in history if 0 <= now - x.timestamp.timestamp() <= 60
        and x.boot_id == t.boot_id and x.device_id == t.device_id and x.mode == t.mode]
    temps = [x.chamber_temp_c for x in window if x.chamber_temp_c is not None]
    currents = [x.primary_current_a for x in window if x.primary_current_a is not None]
    valid = [x for x in window if x.chamber_temp_c is not None]
    span = now - valid[0].timestamp.timestamp()
    rate = (t.chamber_temp_c - valid[0].chamber_temp_c) * 60 / span if span > 0 else 0.0
    values = [t.chamber_temp_c, t.heatsink_temp_c, t.sht31_temp_c, t.humidity_pct,
        t.primary_current_a, float(t.door_open), float(t.primary_cooling), float(t.backup_cooling),
        t.heatsink_temp_c - t.chamber_temp_c, rate, mean(currents), pstdev(temps),
        t.door_open_s, t.primary_current_a / 5.0, mean(temps)]
    if not all(math.isfinite(x) for x in values):
        return None
    return dict(zip(FEATURES, values))
