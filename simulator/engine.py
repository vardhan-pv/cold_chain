"""Seeded illustrative thermal plant, NOT a calibrated digital twin."""
from datetime import datetime, timezone, timedelta
import random
import uuid
from backend.control import Controller
from backend.schemas import Telemetry

SCENARIOS = ['normal', 'primary_failure', 'temperature_rise', 'overcurrent', 'overheat',
    'door_open', 'sensor_failure', 'wifi_failure', 'backend_failure', 'backup_failure',
    'gps_unavailable', 'recovery']

class Simulator:
    def __init__(self, device_id='CCU-SIM-001', seed=42, start=None, scenario='normal'):
        self.device_id = device_id
        self.random = random.Random(seed)
        self.boot_id = uuid.uuid4().hex
        self.start = start or datetime.now(timezone.utc)
        self.scenario = scenario
        self.sequence = 0
        self.elapsed = 0.0
        self.chamber = 9.0 + self.random.uniform(-.4, .4)
        self.heatsink = 32.0
        self.local = Controller()
        self.history = []
        self.queue = []
        self.dropped = 0
        self.last_prediction = None

    def step(self, dt=5.0, activate_after=0):
        from ml.feature_engineering import features_for
        self.elapsed += dt
        self.sequence += 1
        fault = self.scenario if self.elapsed >= activate_after else 'normal'
        primary, backup = self.local.primary, self.local.backup
        primary_failed = fault in ('primary_failure', 'backup_failure', 'recovery')
        current = (0.03 if primary_failed else 5.0 + self.random.gauss(0, .12)) if primary else 0.0
        if fault == 'overcurrent' and primary:
            current = 8.5
        door = fault == 'door_open'
        heat = .008 + (.026 if door else 0)
        if primary and not primary_failed:
            heat -= .022
        if backup and fault != 'backup_failure':
            heat -= .027
        if fault in ('temperature_rise', 'backup_failure'):
            heat += .035
        self.chamber += heat * dt + self.random.gauss(0, .012)
        self.heatsink += ((42 if primary or backup else 30)-self.heatsink) * .12
        if fault == 'overheat':
            self.heatsink = 72.0
        health = dict(chamber=fault != 'sensor_failure', heatsink=True, sht31=True, current=True, door=True)
        gps_fix = fault != 'gps_unavailable'
        t = Telemetry(device_id=self.device_id, boot_id=self.boot_id, sequence=self.sequence,
            timestamp=self.start + timedelta(seconds=self.elapsed), uptime_ms=int(self.elapsed*1000),
            mode='SIMULATION', chamber_temp_c=self.chamber if health['chamber'] else None,
            heatsink_temp_c=self.heatsink, sht31_temp_c=self.chamber + self.random.gauss(.12, .04),
            humidity_pct=min(95, max(25, 61 + (12 if door else 0) + self.random.gauss(0, .8))),
            primary_current_a=max(0, current), door_open=door,
            door_open_s=max(0, self.elapsed-activate_after) if door else 0,
            gps=dict(fix=gps_fix, source='SIMULATED' if gps_fix else 'NONE',
                latitude=12.9 + self.elapsed*.0000001 if gps_fix else None,
                longitude=77.65 if gps_fix else None, speed_kmph=0 if gps_fix else None,
                satellites=8 if gps_fix else 0, age_s=0 if gps_fix else None),
            primary_cooling=primary, backup_cooling=backup,
            system_state=self.local.state, sensor_health=health)
        self.history.append(t)
        self.history = self.history[-60:]
        f = features_for(self.history)
        prediction = self.last_prediction or {}
        decision = self.local.update(t, risk=prediction.get('ensemble_probability'),
            rate=f['chamber_rate_c_min'] if f else 0)
        # Ground truth is the generated fault condition, never an input feature.
        anomaly = fault in ('temperature_rise','overcurrent','overheat','sensor_failure') or (
            primary_failed and primary) or (fault == 'backup_failure' and backup)
        return t, decision, int(anomaly)

    def enqueue(self, t, capacity=120):
        if len(self.queue) >= capacity:
            self.queue.pop(0)
            self.dropped += 1
        self.queue.append(t.model_copy(update={'buffered': True}))

    def network_available(self):
        return self.scenario not in ('wifi_failure', 'backend_failure')

    def acknowledgement(self, command):
        # Local update has already evaluated fresh sensors, dead time and latches.
        # A remote request can only be acknowledged when that controller agrees.
        matches = (command['boot_id'] == self.boot_id and
            command['based_on_sequence'] <= self.sequence and
            (command['primary_cooling'], command['backup_cooling']) == (self.local.primary, self.local.backup))
        return {'device_id': self.device_id, 'boot_id': self.boot_id, 'sequence': self.sequence,
            'outcome': 'APPLIED' if matches else 'REJECTED',
            'primary_cooling': self.local.primary, 'backup_cooling': self.local.backup,
            'reason': 'Local safety controller agrees; simulated outputs applied' if matches else
                      'Local safety controller disagrees; remote override inhibited'}
