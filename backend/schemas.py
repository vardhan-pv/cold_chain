"""One versioned wire contract, used by ingestion, simulation and firmware."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

STATES = Literal['NORMAL', 'WARNING', 'PRIMARY_FAULT', 'BACKUP_ACTIVE',
                 'RECOVERY', 'CRITICAL_FAILURE', 'REROUTING']

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class GPS(Contract):
    fix: bool = False
    source: Literal['GPS', 'SIMULATED', 'NONE'] = 'NONE'
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    speed_kmph: float | None = Field(None, ge=0, le=400)
    satellites: int = Field(0, ge=0, le=99)
    age_s: float | None = Field(None, ge=0)

    @model_validator(mode='after')
    def coherent_fix(self):
        if self.fix:
            if self.latitude is None or self.longitude is None or self.source == 'NONE':
                raise ValueError('A fix requires coordinates and a labelled source')
            if self.age_s is None or self.age_s > 30:
                raise ValueError('A fix must be at most 30 seconds old')
        elif any(v is not None for v in (self.latitude, self.longitude, self.speed_kmph)):
            raise ValueError('No fix: coordinates and speed must be null')
        return self

class SensorHealth(Contract):
    chamber: bool
    heatsink: bool
    sht31: bool
    current: bool
    door: bool

class Telemetry(Contract):
    schema_version: Literal['1.0'] = '1.0'
    device_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,48}$')
    boot_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    sequence: int = Field(ge=0)
    timestamp: datetime
    uptime_ms: int = Field(ge=0)
    mode: Literal['SIMULATION', 'HARDWARE']
    chamber_temp_c: float | None = Field(ge=-55, le=125)
    heatsink_temp_c: float | None = Field(ge=-55, le=125)
    sht31_temp_c: float | None = Field(ge=-40, le=125)
    humidity_pct: float | None = Field(ge=0, le=100)
    primary_current_a: float | None = Field(ge=0, le=20)
    door_open: bool | None
    door_open_s: float = Field(ge=0, default=0)
    gps: GPS
    primary_cooling: bool
    backup_cooling: bool
    system_state: STATES
    sensor_health: SensorHealth
    fault_injection: Literal['NONE', 'PRIMARY_FAILURE', 'BACKUP_FAILURE'] = 'NONE'
    buffered: bool = False
    vibration_detected: bool | None = None

    @field_validator('timestamp')
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('timestamp requires an explicit UTC offset')
        return value

    @model_validator(mode='after')
    def consistent(self):
        if self.primary_cooling and self.backup_cooling:
            raise ValueError('Cooling interlock violation: both outputs are ON')
        for flag, fields in {
            'chamber': ['chamber_temp_c'], 'heatsink': ['heatsink_temp_c'],
            'sht31': ['sht31_temp_c', 'humidity_pct'],
            'current': ['primary_current_a'], 'door': ['door_open'],
        }.items():
            ok = getattr(self.sensor_health, flag)
            if any((getattr(self, f) is not None) != ok for f in fields):
                raise ValueError(f'{flag}: invalid sensor values must be null; valid values required when healthy')
        if self.mode == 'HARDWARE' and self.gps.source == 'SIMULATED':
            raise ValueError('Use SIMULATION mode for simulated coordinates')
        if self.mode == 'SIMULATION' and self.gps.source == 'GPS':
            raise ValueError('Simulator coordinates must be labelled SIMULATED')
        if self.door_open is not True and self.door_open_s != 0:
            raise ValueError('Door duration must be zero unless the door is open')
        return self

class DeviceRegistration(Contract):
    device_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,48}$')
    name: str = Field(min_length=1, max_length=100)
    mode: Literal['SIMULATION', 'HARDWARE']

class CommandAcknowledgement(Contract):
    device_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,48}$')
    boot_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    sequence: int = Field(ge=0)
    outcome: Literal['APPLIED', 'REJECTED']
    primary_cooling: bool
    backup_cooling: bool
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode='after')
    def interlock(self):
        if self.primary_cooling and self.backup_cooling:
            raise ValueError('Acknowledgement violates the cooling interlock')
        return self

class ResetReconciliation(Contract):
    boot_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    reason: str = Field(min_length=15, max_length=500)

class WarehouseInput(Contract):
    warehouse_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,48}$')
    name: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    available: bool
    capacity: float = Field(ge=0)
    minimum_temperature: float
    maximum_temperature: float
    source: Literal['SIMULATED', 'VERIFIED'] = 'SIMULATED'

    @model_validator(mode='after')
    def temperature_order(self):
        if self.minimum_temperature > self.maximum_temperature:
            raise ValueError('Invalid facility temperature range')
        return self

class ScenarioRequest(Contract):
    scenario: Literal['normal', 'primary_failure', 'temperature_rise', 'overcurrent',
        'overheat', 'door_open', 'sensor_failure', 'wifi_failure',
        'backend_failure', 'backup_failure', 'gps_unavailable', 'recovery']

class ValidationRecord(Contract):
    device_id: str
    metric: Literal['starting_temperature_c', 'target_temperature_c', 'minimum_temperature_c',
        'cooldown_s', 'steady_state_temperature_c', 'humidity_pct', 'primary_current_a',
        'backup_current_a', 'heatsink_temperature_c', 'primary_detection_s',
        'backup_activation_s', 'recovery_s', 'rerouting_s', 'telemetry_success_pct',
        'ml_inference_ms', 'xgboost_f1', 'random_forest_f1', 'ensemble_f1']
    value: float
    mode: Literal['SIMULATION', 'HARDWARE']
    evidence: str = Field(min_length=10, max_length=1000)
    measured_at: datetime

    @field_validator('measured_at')
    @classmethod
    def aware(cls, value):
        return Telemetry.timezone_required(value)
