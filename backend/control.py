"""Deterministic controller. Outputs are recommendations; telemetry is observed state.

The simulator applies these locally. Physical control belongs to the ESP32 safety
loop and never depends on the API being reachable.
"""
from dataclasses import dataclass, asdict
from backend.schemas import Telemetry

@dataclass(frozen=True)
class Limits:
    low_c: float = 5.0
    high_c: float = 8.0
    warning_c: float = 10.0
    critical_c: float = 18.0
    hot_limit_c: float = 65.0
    current_limit_a: float = 7.0
    current_min_a: float = 0.3
    off_current_max_a: float = 0.5
    current_grace_s: float = 10.0
    fault_confirm_s: float = 10.0
    break_before_make_s: float = 2.0
    recovery_s: float = 30.0
    backup_timeout_s: float = 120.0
    initial_cooldown_s: float = 600.0
    door_warning_s: float = 30.0

class Controller:
    def __init__(self, snapshot=None, limits=None):
        self.limits = limits or Limits()
        self.state = 'NORMAL'
        self.primary = False
        self.backup = False
        self.entered = None
        self.bad_since = None
        self.good_since = None
        self.on_since = None
        self.primary_off_since = None
        self.backup_started = None
        self.last_time = None
        self.last_reason = 'Safe startup; outputs OFF'
        self.started = None
        self.cooled_once = False
        self.observed_primary_last = False
        self.off_transition_at = None
        if snapshot:
            for key in self.snapshot():
                if key in snapshot:
                    setattr(self, key, snapshot[key])

    def snapshot(self):
        return {k: v for k, v in self.__dict__.items() if k != 'limits'}

    def update(self, t: Telemetry, risk=None, rate=0.0):
        now = t.timestamp.timestamp()
        if self.last_time is not None and now <= self.last_time:
            raise ValueError('Controller requires strictly increasing sample time')
        self.last_time = now
        if self.entered is None:
            self.entered = now
        if self.started is None:
            self.started = now
        if t.chamber_temp_c is not None and t.chamber_temp_c <= self.limits.high_c:
            self.cooled_once = True
        if self.observed_primary_last and not t.primary_cooling:
            self.off_transition_at = now
        self.observed_primary_last = t.primary_cooling
        transitions = []
        L = self.limits

        def transition(state, reason, source='SENSOR_RULE'):
            if self.state != state:
                transitions.append({'previous_state': self.state, 'new_state': state,
                    'reason': reason, 'source': source, 'timestamp': t.timestamp.isoformat()})
                self.state, self.entered, self.last_reason = state, now, reason

        critical = None
        if not all((t.sensor_health.chamber, t.sensor_health.heatsink, t.sensor_health.current)):
            critical = 'Critical sensor invalid; cooling inhibited'
        elif t.heatsink_temp_c >= L.hot_limit_c:
            critical = 'Shared heatsink overtemperature; both cooling channels inhibited'
        elif t.primary_current_a >= L.current_limit_a:
            critical = 'Primary overcurrent; manual electrical inspection required'
        elif (not t.primary_cooling and t.primary_current_a > L.off_current_max_a and
              (self.off_transition_at is None or now-self.off_transition_at >= 0.5)):
            critical = 'Primary draws current while commanded OFF; backup inhibited'
        elif t.chamber_temp_c >= L.critical_c and (self.cooled_once or now-self.started >= L.initial_cooldown_s):
            critical = 'Chamber exceeded the configured demonstration critical limit'

        if critical and self.state not in ('CRITICAL_FAILURE', 'REROUTING'):
            transition('CRITICAL_FAILURE', critical)
        elif self.state == 'CRITICAL_FAILURE':
            # This is a request to route; a destination may still be unavailable.
            transition('REROUTING', 'Cooling latched OFF; request a compatible facility')
        elif self.state not in ('REROUTING',):
            if t.primary_cooling:
                if self.on_since is None:
                    self.on_since = now
            else:
                self.on_since = None

            electrical_fault = (t.primary_cooling and self.on_since is not None and
                now - self.on_since >= L.current_grace_s and t.primary_current_a < L.current_min_a)
            thermal_fault = (t.primary_cooling and t.door_open is False and
                t.chamber_temp_c > L.warning_c and rate > 0.15)
            injected = t.fault_injection == 'PRIMARY_FAILURE'
            bad = electrical_fault or thermal_fault or injected
            if bad:
                if self.bad_since is None:
                    self.bad_since = now
            else:
                self.bad_since = None
            warning = (bad or t.chamber_temp_c > L.warning_c or
                t.door_open_s >= L.door_warning_s or not t.sensor_health.sht31 or
                not t.sensor_health.door or (risk is not None and risk >= 0.65))

            if self.state in ('NORMAL', 'WARNING'):
                if bad and now - self.bad_since >= L.fault_confirm_s:
                    transition('PRIMARY_FAULT', 'Sustained primary cooling fault confirmed',
                               'FAULT_INJECTION' if injected else 'SENSOR_RULE')
                    self.primary_off_since = None
                elif warning:
                    transition('WARNING', 'Observe sensor evidence; maintain hysteresis control',
                               'ML_ADVISORY' if risk is not None and risk >= .65 and not bad else 'SENSOR_RULE')
                else:
                    transition('NORMAL', 'Warning cleared')
            elif self.state == 'PRIMARY_FAULT':
                if not t.primary_cooling and t.primary_current_a <= L.off_current_max_a:
                    if self.primary_off_since is None:
                        self.primary_off_since = now
                    if now - self.primary_off_since >= L.break_before_make_s:
                        transition('BACKUP_ACTIVE', 'Primary OFF evidence and dead time satisfied')
                        self.backup_started = now
                        self.good_since = None
                else:
                    self.primary_off_since = None
                if self.state == 'PRIMARY_FAULT' and now - self.entered > 20:
                    transition('CRITICAL_FAILURE', 'Primary OFF was not confirmed in time')
            elif self.state in ('BACKUP_ACTIVE', 'RECOVERY'):
                if t.fault_injection == 'BACKUP_FAILURE':
                    transition('CRITICAL_FAILURE', 'Injected backup failure', 'FAULT_INJECTION')
                elif t.chamber_temp_c <= L.high_c and rate <= 0.05:
                    if self.good_since is None:
                        self.good_since = now
                    if now - self.good_since >= L.recovery_s:
                        transition('RECOVERY', 'Backup temperature stabilized; maintenance still required')
                else:
                    self.good_since = None
                    if self.state == 'RECOVERY':
                        transition('BACKUP_ACTIVE', 'Recovery lost; reassessing backup')
                        self.backup_started = now
                    elif now - self.backup_started >= L.backup_timeout_s:
                        transition('CRITICAL_FAILURE', 'Backup failed to recover within observation window')

        # Critical state is latched. No automatic reset from a cloud request.
        if self.state in ('PRIMARY_FAULT', 'CRITICAL_FAILURE', 'REROUTING'):
            self.primary = self.backup = False
        else:
            wants = self.backup if self.state in ('BACKUP_ACTIVE', 'RECOVERY') else self.primary
            if t.chamber_temp_c >= L.high_c:
                wants = True
            elif t.chamber_temp_c <= L.low_c:
                wants = False
            if self.state in ('BACKUP_ACTIVE', 'RECOVERY'):
                self.primary, self.backup = False, wants
            else:
                self.primary, self.backup = wants, False
        assert not (self.primary and self.backup)
        return {'state': self.state, 'primary_cooling': self.primary,
            'backup_cooling': self.backup, 'alarm': self.state in ('CRITICAL_FAILURE', 'REROUTING'),
            'tier': 3 if self.state in ('CRITICAL_FAILURE', 'REROUTING') else
                2 if self.state in ('PRIMARY_FAULT', 'BACKUP_ACTIVE', 'RECOVERY') else
                1 if self.state == 'WARNING' else 0,
            'reason': self.last_reason, 'transitions': transitions,
            'authority': 'SIMULATED_LOCAL_CONTROL' if t.mode == 'SIMULATION' else 'ADVISORY_ONLY'}
