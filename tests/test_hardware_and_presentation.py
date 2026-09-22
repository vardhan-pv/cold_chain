from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.schemas import Telemetry, GPS, SensorHealth
from simulator.engine import Simulator
from database.models import ReroutingEvent, HealingEvent

OPERATOR = 'test-operator-token-hardware'

@pytest.fixture
def hw_app(tmp_path):
    app = create_app(f'sqlite:///{tmp_path/"hw_test.db"}', admin_token=OPERATOR)
    with TestClient(app) as client:
        client.headers['Authorization'] = 'Bearer ' + OPERATOR
        # Register Hardware device
        hw_token = client.post('/api/devices', json={'device_id': 'CCU-HW-TEST', 'name': 'Physical Test Node', 'mode': 'HARDWARE'}).json()['device_token']
        # Register Simulation device
        sim_token = client.post('/api/devices', json={'device_id': 'CCU-SIM-TEST', 'name': 'Sim Test Node', 'mode': 'SIMULATION'}).json()['device_token']
        yield app, client, hw_token, sim_token

def make_hw_telemetry(device_id='CCU-HW-TEST', sequence=1, system_state='NORMAL',
                      chamber_ok=False, chamber_temp=None, heatsink_ok=False, heatsink_temp=None,
                      current_ok=False, current_val=None, sht_ok=False, sht_temp=28.0, humidity=55.0, door_open=False,
                      current_source='NONE', current_calibrated=False):
    return Telemetry(
        schema_version='1.0',
        device_id=device_id,
        boot_id='boot-hw-001',
        sequence=sequence,
        timestamp=datetime.now(timezone.utc),
        uptime_ms=sequence * 5000,
        mode='HARDWARE',
        chamber_temp_c=chamber_temp,
        heatsink_temp_c=heatsink_temp,
        sht31_temp_c=sht_temp if sht_ok else None,
        humidity_pct=humidity if sht_ok else None,
        primary_current_a=current_val,
        door_open=door_open,
        door_open_s=0,
        gps=GPS(fix=False, source='NONE'),
        primary_cooling=False,
        backup_cooling=False,
        system_state=system_state,
        sensor_health=SensorHealth(
            chamber=chamber_ok,
            heatsink=heatsink_ok,
            sht31=sht_ok,
            current=current_ok,
            door=True
        ),
        fault_injection='NONE',
        buffered=False,
        current_source=current_source,
        current_calibrated=current_calibrated
    )

def test_hardware_pending_sensors_do_not_enter_critical_failure(hw_app):
    """Regression 1 & 3: Hardware with pending uncommissioned sensors must not enter CRITICAL_FAILURE; edge NORMAL remains current NORMAL."""
    app, client, hw_token, _ = hw_app
    t = make_hw_telemetry(sequence=1, system_state='NORMAL')
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    body = res.json()
    assert body['decision']['state'] == 'NORMAL'
    assert body['decision']['advisory_status'] == 'HARDWARE_PENDING_SENSORS'
    assert body['decision']['authority'] == 'ESP32_EDGE_LOOP'

def test_hardware_pending_sensors_do_not_create_rerouting(hw_app):
    """Regression 2: Hardware with pending uncommissioned sensors must not create rerouting events."""
    app, client, hw_token, _ = hw_app
    for seq in range(1, 5):
        t = make_hw_telemetry(sequence=seq, system_state='NORMAL')
        res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
        assert res.status_code == 200
    
    routes = client.get('/api/rerouting?device_id=CCU-HW-TEST').json()
    assert len(routes) == 0
    latest = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest['rerouting'] is None

def test_runtime_failure_of_commissioned_sensor_triggers_safety(hw_app):
    """Regression 4: A sensor that was commissioned and later fails at runtime triggers CRITICAL_FAILURE."""
    app, client, hw_token, _ = hw_app
    # Commission chamber, heatsink, current
    t1 = make_hw_telemetry(sequence=1, chamber_ok=True, chamber_temp=4.5, heatsink_ok=True, heatsink_temp=28.0, current_ok=True, current_val=0.0)
    res1 = client.post('/api/v1/telemetry', json=t1.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res1.status_code == 200
    assert res1.json()['decision']['state'] == 'NORMAL'

    # Now simulate runtime failure of chamber sensor
    t2 = make_hw_telemetry(sequence=2, chamber_ok=False, chamber_temp=None, heatsink_ok=True, heatsink_temp=28.0, current_ok=True, current_val=0.0)
    res2 = client.post('/api/v1/telemetry', json=t2.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res2.status_code == 200
    assert res2.json()['decision']['state'] == 'CRITICAL_FAILURE'

def test_hardware_ml_waiting_for_sensors(hw_app):
    """Regression 5: Hardware ML with null features returns waiting status, not fake inference."""
    app, client, hw_token, _ = hw_app
    t = make_hw_telemetry(sequence=1)
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    pred = res.json()['prediction']
    assert pred['status'] == 'HARDWARE_WAITING_FOR_SENSORS'
    assert pred['training_provenance'] == 'HARDWARE_PENDING_PHYSICAL_SENSORS'
    assert pred['xgboost_probability'] is None
    assert pred['ensemble_probability'] is None
    assert 'waiting for valid physical sensor data' in pred['message'].lower()

def test_simulation_ml_returns_real_probabilities(hw_app):
    """Regression 6: Simulation ML returns real model probabilities."""
    app, client, _, sim_token = hw_app
    sim = Simulator('CCU-SIM-TEST')
    t, _, _ = sim.step()
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': sim_token})
    assert res.status_code == 200
    pred = res.json()['prediction']
    assert pred['status'] == 'INFERENCE_COMPLETE'
    assert isinstance(pred['xgboost_probability'], float)
    assert isinstance(pred['random_forest_probability'], float)
    assert isinstance(pred['ensemble_probability'], float)

def test_historical_critical_event_does_not_override_current_normal(hw_app):
    """Regression 7: Historical event does not override current edge state."""
    app, client, hw_token, _ = hw_app
    # First telemetry: NORMAL
    t1 = make_hw_telemetry(sequence=1, system_state='NORMAL')
    client.post('/api/v1/telemetry', json=t1.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    
    # Inject an old healing event manually into db to test historical presentation isolation
    service = app.state.service
    with service.Session.begin() as s:
        s.add(HealingEvent(
            device_id='CCU-HW-TEST',
            timestamp=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            payload={
                'previous_state': 'PRIMARY_FAULT',
                'new_state': 'CRITICAL_FAILURE',
                'reason': 'Historical test event',
                'source': 'TEST',
                'mode': 'HARDWARE',
                'resolved': True
            }
        ))
    
    # Check latest status
    latest = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest['telemetry']['payload']['system_state'] == 'NORMAL'
    assert latest['rerouting'] is None

def test_hardware_and_simulation_isolation(hw_app):
    """Regression 8: Hardware and simulation history are kept completely separate."""
    app, client, hw_token, sim_token = hw_app
    # Hardware sample
    t_hw = make_hw_telemetry(sequence=1)
    client.post('/api/v1/telemetry', json=t_hw.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    
    # Simulation sample
    sim = Simulator('CCU-SIM-TEST')
    t_sim, _, _ = sim.step()
    client.post('/api/v1/telemetry', json=t_sim.model_dump(mode='json'), headers={'X-Device-Token': sim_token})
    
    hw_history = client.get('/api/history?device_id=CCU-HW-TEST').json()
    sim_history = client.get('/api/history?device_id=CCU-SIM-TEST').json()
    assert len(hw_history) == 1 and hw_history[0]['mode'] == 'HARDWARE'
    assert len(sim_history) == 1 and sim_history[0]['mode'] == 'SIMULATION'

def test_real_physical_hardware_validated_telemetry_integration(hw_app):
    """Test the exact physical hardware payload validated on the bench."""
    app, client, hw_token, _ = hw_app
    telemetry = Telemetry(
        schema_version='1.0',
        device_id='CCU-HW-TEST',
        boot_id='boot-phys-hw-001',
        sequence=1,
        timestamp=datetime.now(timezone.utc),
        uptime_ms=12345,
        mode='HARDWARE',
        chamber_temp_c=31.12,
        heatsink_temp_c=31.75,
        sht31_temp_c=32.63,
        humidity_pct=56.08,
        primary_current_a=None,
        door_open=True,
        door_open_s=10.0,
        gps=GPS(fix=False, source='NONE', latitude=None, longitude=None, speed_kmph=None, satellites=0, age_s=None),
        primary_cooling=False,
        backup_cooling=False,
        system_state='NORMAL',
        sensor_health=SensorHealth(chamber=True, heatsink=True, sht31=True, current=False, door=True),
        fault_injection='NONE',
        buffered=False,
        vibration_detected=False
    )
    res = client.post('/api/v1/telemetry', json=telemetry.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    body = res.json()
    assert body['stored'] is True
    assert body['decision']['state'] == 'NORMAL'
    assert body['decision']['advisory_status'] == 'HARDWARE_PENDING_SENSORS'
    assert body['decision']['authority'] == 'ESP32_EDGE_LOOP'

def test_hardware_warm_chamber_with_uncommissioned_cooling_does_not_trip_cooldown_timeout(hw_app):
    """Warm ambient chamber on uncommissioned hardware must not trip critical failure after initial cooldown window."""
    app, client, hw_token, _ = hw_app
    base_time = datetime.now(timezone.utc) - timedelta(seconds=650)
    t1 = Telemetry(
        schema_version='1.0',
        device_id='CCU-HW-TEST',
        boot_id='boot-hw-warm-001',
        sequence=1,
        timestamp=base_time,
        uptime_ms=1000,
        mode='HARDWARE',
        chamber_temp_c=31.5,
        heatsink_temp_c=32.0,
        sht31_temp_c=32.5,
        humidity_pct=55.0,
        primary_current_a=None,
        door_open=False,
        door_open_s=0,
        gps=GPS(fix=False, source='NONE'),
        primary_cooling=False,
        backup_cooling=False,
        system_state='NORMAL',
        sensor_health=SensorHealth(chamber=True, heatsink=True, sht31=True, current=False, door=True),
        fault_injection='NONE',
        buffered=True  # historical past sample
    )
    res1 = client.post('/api/v1/telemetry', json=t1.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res1.status_code == 200

    # Advance to current time (> 600s since started)
    t2 = Telemetry(
        schema_version='1.0',
        device_id='CCU-HW-TEST',
        boot_id='boot-hw-warm-001',
        sequence=2,
        timestamp=datetime.now(timezone.utc),
        uptime_ms=651000,
        mode='HARDWARE',
        chamber_temp_c=31.5,
        heatsink_temp_c=32.0,
        sht31_temp_c=32.5,
        humidity_pct=55.0,
        primary_current_a=None,
        door_open=False,
        door_open_s=0,
        gps=GPS(fix=False, source='NONE'),
        primary_cooling=False,
        backup_cooling=False,
        system_state='NORMAL',
        sensor_health=SensorHealth(chamber=True, heatsink=True, sht31=True, current=False, door=True),
        fault_injection='NONE',
        buffered=False
    )
    res2 = client.post('/api/v1/telemetry', json=t2.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res2.status_code == 200
    assert res2.json()['decision']['state'] == 'NORMAL'
    assert res2.json()['decision']['advisory_status'] == 'HARDWARE_PENDING_SENSORS'

def test_vibration_telemetry_optional_and_backward_compatible(hw_app):
    """Telemetry with and without vibration_detected must both validate cleanly."""
    app, client, hw_token, _ = hw_app
    t0 = datetime.now(timezone.utc) - timedelta(seconds=2)
    # Without vibration_detected
    t_without = make_hw_telemetry(sequence=1)
    payload1 = t_without.model_dump(mode='json')
    payload1['timestamp'] = t0.isoformat()
    res1 = client.post('/api/v1/telemetry', json=payload1, headers={'X-Device-Token': hw_token})
    assert res1.status_code == 200

    # With vibration_detected = True
    payload2 = t_without.model_dump(mode='json')
    payload2['sequence'] = 2
    payload2['timestamp'] = (t0 + timedelta(seconds=1)).isoformat()
    payload2['vibration_detected'] = True
    res2 = client.post('/api/v1/telemetry', json=payload2, headers={'X-Device-Token': hw_token})
    assert res2.status_code == 200

    latest = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest['telemetry']['payload']['vibration_detected'] is True

def test_gps_indoor_no_fix_with_satellites(hw_app):
    """Indoor GPS receiving satellite data without fix must not cause validation or safety error."""
    app, client, hw_token, _ = hw_app
    t = Telemetry(
        schema_version='1.0',
        device_id='CCU-HW-TEST',
        boot_id='boot-gps-001',
        sequence=1,
        timestamp=datetime.now(timezone.utc),
        uptime_ms=5000,
        mode='HARDWARE',
        chamber_temp_c=25.0,
        heatsink_temp_c=26.0,
        sht31_temp_c=26.5,
        humidity_pct=50.0,
        primary_current_a=None,
        door_open=False,
        door_open_s=0,
        gps=GPS(fix=False, source='NONE', latitude=None, longitude=None, speed_kmph=None, satellites=4, age_s=None),
        primary_cooling=False,
        backup_cooling=False,
        system_state='NORMAL',
        sensor_health=SensorHealth(chamber=True, heatsink=True, sht31=True, current=False, door=True),
        fault_injection='NONE',
        buffered=False
    )
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    assert res.json()['decision']['state'] == 'NORMAL'


def test_hardware_primary_cooling_commissioned_and_telemetry_reporting(hw_app):
    """Regression: Primary cooling is commissioned; telemetry reflects real physical ON/OFF states."""
    app, client, hw_token, _ = hw_app

    # Test Primary Cooling OFF state
    t_off = make_hw_telemetry(
        sequence=1, system_state='NORMAL',
        chamber_ok=True, chamber_temp=28.5,
        heatsink_ok=True, heatsink_temp=28.2,
        current_ok=False, current_val=None,
        sht_ok=True, door_open=False
    )
    t_off.primary_cooling = False
    t_off.backup_cooling = False
    res_off = client.post('/api/v1/telemetry', json=t_off.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_off.status_code == 200
    latest_off = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    payload_off = latest_off['telemetry']['payload']
    assert payload_off['primary_cooling'] is False
    assert payload_off['backup_cooling'] is False
    assert payload_off['primary_current_a'] is None
    assert payload_off['sensor_health']['current'] is False
    assert latest_off['telemetry']['decision']['state'] == 'NORMAL'
    assert latest_off['telemetry']['decision']['authority'] == 'ESP32_EDGE_LOOP'

    # Test Primary Cooling ON state (e.g. during safe test or active chilling)
    t_on = make_hw_telemetry(
        sequence=2, system_state='NORMAL',
        chamber_ok=True, chamber_temp=27.9,
        heatsink_ok=True, heatsink_temp=29.1,
        current_ok=False, current_val=None,
        sht_ok=True, door_open=False
    )
    t_on.primary_cooling = True
    t_on.backup_cooling = False
    res_on = client.post('/api/v1/telemetry', json=t_on.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_on.status_code == 200
    latest_on = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    payload_on = latest_on['telemetry']['payload']
    assert payload_on['primary_cooling'] is True
    assert payload_on['backup_cooling'] is False
    assert payload_on['primary_current_a'] is None
    assert latest_on['telemetry']['decision']['authority'] == 'ESP32_EDGE_LOOP'


def test_uncalibrated_current_does_not_trip_hardware_cooling_failure(hw_app):
    """Regression: Current pending calibration is not a hardware fault; edge authority preserved."""
    app, client, hw_token, _ = hw_app
    t = make_hw_telemetry(
        sequence=1, system_state='NORMAL',
        chamber_ok=True, chamber_temp=25.0,
        heatsink_ok=True, heatsink_temp=26.0,
        current_ok=False, current_val=None
    )
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    decision = res.json()['decision']
    assert decision['state'] == 'NORMAL'
    assert decision['advisory_status'] == 'HARDWARE_PENDING_SENSORS'
    assert decision['authority'] == 'ESP32_EDGE_LOOP'


def test_thermal_protection_heatsink_overtemp_triggers_critical_failure(hw_app):
    """Regression: Heatsink overtemperature (>=65C limit) triggers CRITICAL_FAILURE."""
    app, client, hw_token, _ = hw_app
    t = make_hw_telemetry(
        sequence=1, system_state='NORMAL',
        chamber_ok=True, chamber_temp=10.0,
        heatsink_ok=True, heatsink_temp=66.5,
        current_ok=False, current_val=None
    )
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    decision = res.json()['decision']
    assert decision['state'] == 'CRITICAL_FAILURE'
    assert 'heatsink overtemperature' in decision['reason'].lower()


def test_commissioned_sensor_loss_triggers_critical_failure(hw_app):
    """Regression: Loss of chamber or heatsink sensor once commissioned trips CRITICAL_FAILURE."""
    app, client, hw_token, _ = hw_app
    # First establish good chamber & heatsink readings
    t1 = make_hw_telemetry(
        sequence=1, system_state='NORMAL',
        chamber_ok=True, chamber_temp=8.0,
        heatsink_ok=True, heatsink_temp=30.0,
        current_ok=False, current_val=None
    )
    res1 = client.post('/api/v1/telemetry', json=t1.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res1.status_code == 200
    assert res1.json()['decision']['state'] == 'NORMAL'

    # Now chamber sensor drops out
    t2 = make_hw_telemetry(
        sequence=2, system_state='NORMAL',
        chamber_ok=False, chamber_temp=None,
        heatsink_ok=True, heatsink_temp=30.0,
        current_ok=False, current_val=None
    )
    res2 = client.post('/api/v1/telemetry', json=t2.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res2.status_code == 200
    decision = res2.json()['decision']
    assert decision['state'] == 'CRITICAL_FAILURE'
    assert 'chamber' in decision['reason'].lower()


def test_dashboard_code_does_not_label_primary_cooling_not_commissioned():
    """Regression: Dashboard source code renders dynamic OFF/ON for primary cooling and preserves NOT COMMISSIONED for backup."""
    from pathlib import Path
    app_js_path = Path(__file__).resolve().parents[1] / 'dashboard' / 'src' / 'app.js'
    content = app_js_path.read_text(encoding='utf-8')

    # Primary cooling must NOT be hardcoded to NOT COMMISSIONED
    assert "isHardware ? 'NOT COMMISSIONED" not in content.split("primaryCoolingText")[1].split(";")[0], \
        "primaryCoolingText should not be hardcoded to NOT COMMISSIONED in hardware mode"

    # Backup cooling must remain NOT COMMISSIONED in hardware mode
    assert "backupCoolingText = isHardware ? 'NOT COMMISSIONED'" in content

    # Primary current must display 'Waiting for calibration' when uncalibrated in hardware mode
    assert "Waiting for calibration" in content


def test_healthy_boot_primary_off_starts_normal(hw_app):
    """Regression 1 & 6 & 7 & 8 & 9: Healthy boot with primary OFF, auto false, backup uncommissioned,
    and ACS712 uncalibrated reports NORMAL and does not trigger REROUTING."""
    app, client, hw_token, _ = hw_app
    t = make_hw_telemetry(
        sequence=1, system_state='NORMAL',
        chamber_ok=True, chamber_temp=28.50,
        heatsink_ok=True, heatsink_temp=28.00,
        current_ok=False, current_val=None,
        sht_ok=True, sht_temp=28.40, humidity=74.0,
        door_open=False
    )
    t.primary_cooling = False
    t.backup_cooling = False
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    decision = res.json()['decision']
    assert decision['state'] == 'NORMAL'
    assert decision['primary_cooling'] is False
    assert decision['backup_cooling'] is False
    assert decision['alarm'] is False
    assert decision['authority'] == 'ESP32_EDGE_LOOP'


def test_door_open_warning_and_door_close_recovery_to_normal(hw_app):
    """Regression 2 & 4: Door open >= 30s transitions to WARNING; closing door recovers to NORMAL."""
    app, client, hw_token, _ = hw_app
    # Step 1: Door opened for 35s
    t_open = make_hw_telemetry(
        sequence=1, system_state='WARNING',
        chamber_ok=True, chamber_temp=28.50,
        heatsink_ok=True, heatsink_temp=28.00,
        current_ok=False, current_val=None,
        sht_ok=True, door_open=True
    )
    t_open.door_open_s = 35
    res_open = client.post('/api/v1/telemetry', json=t_open.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_open.status_code == 200
    assert res_open.json()['decision']['state'] == 'WARNING'

    # Step 2: Door closed
    t_closed = make_hw_telemetry(
        sequence=2, system_state='NORMAL',
        chamber_ok=True, chamber_temp=28.50,
        heatsink_ok=True, heatsink_temp=28.00,
        current_ok=False, current_val=None,
        sht_ok=True, door_open=False
    )
    t_closed.door_open_s = 0
    res_closed = client.post('/api/v1/telemetry', json=t_closed.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_closed.status_code == 200
    assert res_closed.json()['decision']['state'] == 'NORMAL'


def test_prolonged_door_or_rerouting_recovers_to_normal_when_resolved(hw_app):
    """Regression 3 & 4 & 5: When a historical REROUTING edge event clears, edge state and cloud recover to NORMAL."""
    app, client, hw_token, _ = hw_app
    # Step 1: System was in REROUTING
    t_reroute = make_hw_telemetry(
        sequence=1, system_state='REROUTING',
        chamber_ok=True, chamber_temp=28.50,
        heatsink_ok=True, heatsink_temp=28.00,
        current_ok=False, current_val=None,
        sht_ok=True, door_open=False
    )
    res_reroute = client.post('/api/v1/telemetry', json=t_reroute.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_reroute.status_code == 200
    assert res_reroute.json()['decision']['state'] == 'REROUTING'

    # Step 2: System recovers at the edge, sending NORMAL
    t_recover = make_hw_telemetry(
        sequence=2, system_state='NORMAL',
        chamber_ok=True, chamber_temp=28.50,
        heatsink_ok=True, heatsink_temp=28.00,
        current_ok=False, current_val=None,
        sht_ok=True, door_open=False
    )
    res_recover = client.post('/api/v1/telemetry', json=t_recover.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_recover.status_code == 200
    assert res_recover.json()['decision']['state'] == 'NORMAL'

    # Current authoritative state must be NORMAL, not stuck in REROUTING
    latest = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest['telemetry']['payload']['system_state'] == 'NORMAL'
    assert latest['telemetry']['decision']['state'] == 'NORMAL'


def test_reboot_after_resolved_incident_starts_normal_if_no_active_fault(hw_app):
    """Regression 10 & 11: Reboot after resolved incident starts in NORMAL when no active physical fault remains."""
    app, client, hw_token, _ = hw_app
    # Incident in past boot
    t_past = make_hw_telemetry(
        sequence=1, system_state='REROUTING',
        chamber_ok=True, chamber_temp=28.50,
        heatsink_ok=True, heatsink_temp=28.00,
        current_ok=False, current_val=None,
        sht_ok=True, door_open=False
    )
    t_past.boot_id = 'boot-hw-old-fault'
    res_past = client.post('/api/v1/telemetry', json=t_past.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_past.status_code == 200

    # Fresh reboot with new boot_id and healthy physical sensors
    t_boot = make_hw_telemetry(
        sequence=1, system_state='NORMAL',
        chamber_ok=True, chamber_temp=28.50,
        heatsink_ok=True, heatsink_temp=28.00,
        current_ok=False, current_val=None,
        sht_ok=True, door_open=False
    )
    t_boot.boot_id = 'boot-hw-fresh-reboot'
    res_boot = client.post('/api/v1/telemetry', json=t_boot.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_boot.status_code == 200
    decision = res_boot.json()['decision']
    assert decision['state'] == 'NORMAL'
    assert decision['alarm'] is False


def test_hybrid_emulated_current_hardware_mode_preserves_hardware_identity(hw_app):
    """Regression: HARDWARE mode remains HARDWARE; physical sensors remain real;
    current_source is EMULATED, current_calibrated is false, and physical ACS712 health remains uncalibrated (false)."""
    app, client, hw_token, _ = hw_app
    # Primary cooling OFF -> current ~0.0 A
    t_off = make_hw_telemetry(
        sequence=1, system_state='NORMAL',
        chamber_ok=True, chamber_temp=28.50,
        heatsink_ok=True, heatsink_temp=28.00,
        current_ok=False, current_val=0.0,
        sht_ok=True, sht_temp=28.40, humidity=74.0,
        door_open=False, current_source='EMULATED', current_calibrated=False
    )
    t_off.primary_cooling = False
    res_off = client.post('/api/v1/telemetry', json=t_off.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_off.status_code == 200
    payload_off = client.get('/api/latest?device_id=CCU-HW-TEST').json()['telemetry']['payload']
    assert payload_off['mode'] == 'HARDWARE'
    assert payload_off['chamber_temp_c'] == 28.50
    assert payload_off['heatsink_temp_c'] == 28.00
    assert payload_off['primary_cooling'] is False
    assert payload_off['primary_current_a'] == 0.0
    assert payload_off['current_source'] == 'EMULATED'
    assert payload_off['current_calibrated'] is False
    assert payload_off['sensor_health']['current'] is False  # Physical sensor is NOT claimed calibrated

    # Primary cooling ON -> configured demo current (3.5 A)
    t_on = make_hw_telemetry(
        sequence=2, system_state='NORMAL',
        chamber_ok=True, chamber_temp=28.40,
        heatsink_ok=True, heatsink_temp=28.20,
        current_ok=False, current_val=3.5,
        sht_ok=True, sht_temp=28.40, humidity=74.0,
        door_open=False, current_source='EMULATED', current_calibrated=False
    )
    t_on.primary_cooling = True
    res_on = client.post('/api/v1/telemetry', json=t_on.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_on.status_code == 200
    payload_on = client.get('/api/latest?device_id=CCU-HW-TEST').json()['telemetry']['payload']
    assert payload_on['mode'] == 'HARDWARE'
    assert payload_on['primary_cooling'] is True
    assert payload_on['primary_current_a'] == 3.5
    assert payload_on['current_source'] == 'EMULATED'
    assert payload_on['current_calibrated'] is False
    assert payload_on['sensor_health']['current'] is False


def test_ml_pipeline_runs_full_inference_with_emulated_current(hw_app):
    """Regression: ML feature engineering succeeds with explicit emulated current and runs
    XGBoost, Random Forest, and Weighted Ensemble inference with latency and threshold."""
    app, client, hw_token, _ = hw_app
    # Send historical and current samples with emulated current
    for seq in range(1, 4):
        t = make_hw_telemetry(
            sequence=seq, system_state='NORMAL',
            chamber_ok=True, chamber_temp=28.50 - seq * 0.05,
            heatsink_ok=True, heatsink_temp=28.00 + seq * 0.05,
            current_ok=False, current_val=3.5,
            sht_ok=True, sht_temp=28.40, humidity=74.0,
            door_open=False, current_source='EMULATED', current_calibrated=False
        )
        t.primary_cooling = True
        res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
        assert res.status_code == 200

    latest = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    prediction = latest['prediction']
    assert prediction['status'] == 'INFERENCE_COMPLETE'
    assert isinstance(prediction['xgboost_probability'], float)
    assert 0.0 <= prediction['xgboost_probability'] <= 1.0
    assert isinstance(prediction['random_forest_probability'], float)
    assert 0.0 <= prediction['random_forest_probability'] <= 1.0
    assert isinstance(prediction['ensemble_probability'], float)
    assert 0.0 <= prediction['ensemble_probability'] <= 1.0
    assert isinstance(prediction['threshold'], float)
    assert 0.0 < prediction['threshold'] < 1.0
    assert isinstance(prediction['inference_ms'], (int, float))
    assert prediction['inference_ms'] >= 0
    assert prediction['model_version'] is not None
    assert prediction['feature_provenance'] == 'HARDWARE_HYBRID_EMULATED_CURRENT'


def test_physical_safety_logic_independent_of_emulated_current(hw_app):
    """Regression: Emulated current does not trigger false electrical overcurrent faults,
    while genuine physical faults (heatsink overtemp, sensor loss) still trigger CRITICAL_FAILURE."""
    app, client, hw_token, _ = hw_app
    # Emulated current while cooling is commanded ON does not trip electrical overcurrent
    t_safe = make_hw_telemetry(
        sequence=1, system_state='NORMAL',
        chamber_ok=True, chamber_temp=28.50,
        heatsink_ok=True, heatsink_temp=28.00,
        current_ok=False, current_val=3.5,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    t_safe.primary_cooling = True
    res_safe = client.post('/api/v1/telemetry', json=t_safe.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_safe.status_code == 200
    assert res_safe.json()['decision']['state'] == 'NORMAL'

    # Genuine physical thermal fault (heatsink >= 65 C) still triggers CRITICAL_FAILURE
    t_thermal = make_hw_telemetry(
        sequence=2, system_state='NORMAL',
        chamber_ok=True, chamber_temp=28.50,
        heatsink_ok=True, heatsink_temp=66.00,
        current_ok=False, current_val=3.5,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    res_thermal = client.post('/api/v1/telemetry', json=t_thermal.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_thermal.status_code == 200
    assert res_thermal.json()['decision']['state'] == 'CRITICAL_FAILURE'
    assert 'heatsink overtemperature' in res_thermal.json()['decision']['reason'].lower()


def test_dashboard_provenance_and_ml_rendering_elements():
    """Regression: Dashboard renders EMULATED badge, ACS712 pending calibration,
    and active ML inference metadata in source code."""
    from pathlib import Path
    app_js = Path(__file__).resolve().parents[1] / 'dashboard' / 'src' / 'app.js'
    code = app_js.read_text(encoding='utf-8')
    assert "EMULATED" in code
    assert "ACS712 calibration: PENDING" in code
    assert "HARDWARE DATA (HYBRID EMULATED CURRENT)" in code
    assert "Latency:" in code
    assert "Threshold:" in code



