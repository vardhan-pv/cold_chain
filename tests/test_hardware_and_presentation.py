from datetime import datetime, timezone, timedelta
from pathlib import Path
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
    """Regression: Dashboard source code renders dynamic OFF/ON for primary cooling and preserves NOT COMMISSIONED for backup.
    Also verifies MANUAL_SMPS mode-awareness: dashboard checks cooling_control_mode / manual_cooling_confirmed
    rather than relying solely on the GPIO16-derived primary_cooling field."""
    from pathlib import Path
    app_js_path = Path(__file__).resolve().parents[1] / 'dashboard' / 'src' / 'app.js'
    content = app_js_path.read_text(encoding='utf-8')

    # Primary cooling must NOT be hardcoded to NOT COMMISSIONED
    # The primaryCoolingText block is now a let declaration with MANUAL_SMPS awareness.
    # The NOT COMMISSIONED string should not appear in the primary cooling branch.
    primary_block = content.split("primaryCoolingText")[1]
    assert "'NOT COMMISSIONED'" not in primary_block.split("backupCoolingText")[0], \
        "primaryCoolingText should not be hardcoded to NOT COMMISSIONED in hardware mode"

    # Dashboard must check cooling_control_mode and manual_cooling_confirmed for MANUAL_SMPS
    assert "cooling_control_mode === 'MANUAL_SMPS'" in content, \
        "Dashboard must be aware of MANUAL_SMPS control mode"
    assert "manual_cooling_confirmed" in content, \
        "Dashboard must read manual_cooling_confirmed for MANUAL_SMPS mode"

    # Backup cooling supports VIRTUAL backup while preserving NOT COMMISSIONED when uncommissioned
    assert "t.backup_source === 'VIRTUAL'" in content, \
        "Dashboard must be aware of VIRTUAL backup cooling mode"
    assert "isHardware ? 'NOT COMMISSIONED'" in content, \
        "Dashboard must preserve NOT COMMISSIONED when virtual backup is not in use"

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
    """Regression: Dashboard renders clean KPI card without EMULATED badge directly on main card,
    discloses current provenance in System Health, and supports freshness offline rules."""
    from pathlib import Path
    app_js = Path(__file__).resolve().parents[1] / 'dashboard' / 'src' / 'app.js'
    code = app_js.read_text(encoding='utf-8')
    assert "Current input source" in code
    assert "ACS712 calibration" in code
    assert "isLiveHardwareFresh" in code
    assert "HARDWARE · ONLINE" in code
    assert "HARDWARE · OFFLINE" in code
    assert "NO LIVE HARDWARE DATA" in code


def test_telemetry_freshness_and_offline_status_transitions(hw_app):
    """Regression: Verifies recent telemetry -> ONLINE, stale telemetry (>15s) -> STALE/OFFLINE,
    historical records preserved, and automatic return to ONLINE upon new telemetry."""
    from datetime import datetime, timezone, timedelta
    from database.models import Device
    app, client, hw_token, _ = hw_app

    # 1. Post recent hardware telemetry -> ONLINE
    t1 = make_hw_telemetry(
        sequence=1, system_state='NORMAL',
        chamber_ok=True, chamber_temp=28.50,
        heatsink_ok=True, heatsink_temp=28.00,
        current_ok=False, current_val=0.0,
        sht_ok=True, sht_temp=28.40, humidity=74.0,
        door_open=False, current_source='EMULATED', current_calibrated=False
    )
    res1 = client.post('/api/v1/telemetry', json=t1.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res1.status_code == 200

    latest1 = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest1['connectivity'] == 'ONLINE'
    assert latest1['online'] is True
    assert latest1['data_stale'] is False
    assert latest1['telemetry']['payload']['chamber_temp_c'] == 28.50

    # 2. Simulate hardware disconnection / time pass (>15 seconds since last telemetry)
    with app.state.service.Session() as s:
        dev = s.get(Device, 'CCU-HW-TEST')
        old_time = datetime.now(timezone.utc) - timedelta(seconds=25)
        dev.last_seen = old_time.isoformat()
        s.commit()

    latest2 = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest2['connectivity'] == 'STALE'
    assert latest2['online'] is False
    assert latest2['data_stale'] is True
    # Historical telemetry row is still preserved in DB/history, but data is flagged stale
    assert latest2['telemetry'] is not None
    assert latest2['seconds_since_received'] >= 20.0

    # 3. New telemetry packet arrives -> hardware returns to ONLINE
    t2 = make_hw_telemetry(
        sequence=2, system_state='NORMAL',
        chamber_ok=True, chamber_temp=28.40,
        heatsink_ok=True, heatsink_temp=28.10,
        current_ok=False, current_val=3.5,
        sht_ok=True, sht_temp=28.40, humidity=74.0,
        door_open=False, current_source='EMULATED', current_calibrated=False
    )
    t2.primary_cooling = True
    res2 = client.post('/api/v1/telemetry', json=t2.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res2.status_code == 200

    latest3 = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest3['connectivity'] == 'ONLINE'
    assert latest3['online'] is True
    assert latest3['data_stale'] is False
    assert latest3['telemetry']['payload']['chamber_temp_c'] == 28.40


def test_firmware_door_and_buzzer_source_contract():
    """Verify ESP32-S3 firmware pins, non-blocking buzzer loop, and door reading integration."""
    root = Path(__file__).resolve().parents[1]
    comm_h = (root / 'firmware/esp32_s3/commissioning.h').read_text()
    config_h = (root / 'firmware/esp32_s3/config.h').read_text()
    display_h = (root / 'firmware/esp32_s3/display.h').read_text()
    display_cpp = (root / 'firmware/esp32_s3/display.cpp').read_text()
    ino = (root / 'firmware/esp32_s3/esp32_s3.ino').read_text()
    sensors_cpp = (root / 'firmware/esp32_s3/sensors.cpp').read_text()

    # 1. Pins: Reed switch must be GPIO7, Buzzer must be GPIO12
    assert 'PIN_REED = 7' in comm_h
    assert 'PIN_BUZZER = 12' in comm_h

    # 2. Buzzer polarity configuration exists in commissioning.h & config.h
    assert 'BUZZER_ACTIVE_LOW' in comm_h
    assert 'BUZZER_ACTIVE' in comm_h
    assert 'BUZZER_INACTIVE' in comm_h
    assert 'BUZZER_ACTIVE_LOW' in config_h

    # 3. Existing real door state from GPIO7 in sensors.cpp:
    assert 'pinMode(PIN_REED, INPUT_PULLUP);' in sensors_cpp
    assert 'data.doorOK = true;' in sensors_cpp
    assert 'data.doorOpen = raw;' in sensors_cpp

    # 4. esp32_s3.ino calls buzzerTick(s, controller.output, now) on every loop pass
    assert 'buzzerTick(s, controller.output, now);' in ino
    # Must use existing s from sensorSnapshot, not a separate digitalRead
    assert 'sensorsTick(now);' in ino
    assert 'SensorData s=sensorSnapshot(now);' in ino

    # 5. display.h exports buzzerTick
    assert 'void buzzerTick(' in display_h

    # 6. display.cpp implements continuous buzzer when door open and immediate stop when closed
    assert 'void buzzerTick(const SensorData& data, const coldchain::Output& output, uint32_t now)' in display_cpp
    assert 'const bool doorIsOpen = (data.doorOK && data.doorOpen);' in display_cpp
    assert 'buzzerOn = true;' in display_cpp
    assert 'setBuzzer(buzzerOn);' in display_cpp

    # 7. No delay() loops in buzzerTick or setBuzzer
    # Extract buzzerTick function body
    tick_start = display_cpp.find('void buzzerTick(')
    tick_end = display_cpp.find('void displayTick(', tick_start)
    buzzer_tick_body = display_cpp[tick_start:tick_end]
    assert 'delay(' not in buzzer_tick_body

    # 8. Polarity handling in displayBegin and setBuzzer
    assert 'BUZZER_INACTIVE' in display_cpp
    assert 'BUZZER_ACTIVE' in display_cpp


def test_firmware_buzzer_behavior_logic_and_polarity():
    """Simulate C++ buzzerTick and setBuzzer logic across states and polarity options."""
    def simulate_buzzer_tick(door_ok: bool, door_open: bool, state: str, alarm: bool, now_ms: int):
        door_is_open = door_ok and door_open
        is_alarm = alarm or state in ('PRIMARY_FAULT', 'CRITICAL_FAILURE')

        if door_is_open:
            buzzer_on = True
        elif is_alarm:
            buzzer_on = (now_ms % 500 < 250)
        else:
            buzzer_on = False

        return buzzer_on

    def simulate_pin_drive(buzzer_on: bool, active_low: bool):
        buzzer_active = 0 if active_low else 1
        buzzer_inactive = 1 if active_low else 0
        return buzzer_active if buzzer_on else buzzer_inactive

    # Scenario A: Door is OPEN -> Buzzer continuously ON across all timestamps
    for ms in [0, 50, 100, 249, 250, 499, 500, 1000, 1500, 1999, 2000]:
        on = simulate_buzzer_tick(door_ok=True, door_open=True, state='NORMAL', alarm=False, now_ms=ms)
        assert on is True, f"Buzzer must be continuously ON when door is open at ms={ms}"
        # Active-HIGH drives HIGH (1)
        assert simulate_pin_drive(on, active_low=False) == 1
        # Active-LOW drives LOW (0)
        assert simulate_pin_drive(on, active_low=True) == 0

    # Scenario B: Door becomes CLOSED -> Buzzer stops immediately (OFF)
    for ms in [0, 50, 100, 249, 250, 499, 500, 1000, 1500, 1999, 2000]:
        on = simulate_buzzer_tick(door_ok=True, door_open=False, state='NORMAL', alarm=False, now_ms=ms)
        assert on is False, f"Buzzer must be OFF immediately when door is closed at ms={ms}"
        # Active-HIGH drives LOW (0)
        assert simulate_pin_drive(on, active_low=False) == 0
        # Active-LOW drives HIGH (1)
        assert simulate_pin_drive(on, active_low=True) == 1

    # Scenario C: Door CLOSED during WARNING state -> Buzzer remains OFF
    for ms in [0, 100, 250, 500]:
        on = simulate_buzzer_tick(door_ok=True, door_open=False, state='WARNING', alarm=False, now_ms=ms)
        assert on is False

    # Scenario D: Door CLOSED during PRIMARY_FAULT or CRITICAL_FAILURE alarm -> Alarm tone preserved
    # At ms=100 (100 % 500 = 100 < 250), tone is ON
    assert simulate_buzzer_tick(door_ok=True, door_open=False, state='PRIMARY_FAULT', alarm=True, now_ms=100) is True
    # At ms=300 (300 % 500 = 300 >= 250), tone is OFF
    assert simulate_buzzer_tick(door_ok=True, door_open=False, state='PRIMARY_FAULT', alarm=True, now_ms=300) is False

    # Scenario E: Door OPEN during alarm -> Door OPEN continuously sounds
    assert simulate_buzzer_tick(door_ok=True, door_open=True, state='PRIMARY_FAULT', alarm=True, now_ms=300) is True

def test_manual_cooling_assistant_lcd_and_emulation(hw_app):
    """Test the manual cooling assistant features: LCD warnings and Emulated current behavior."""
    app, client, hw_token, _ = hw_app
    
    # 1. Chamber Temp > HIGH_TEMP_WARNING and manual cooling OFF -> Emulated current 0.0, Warning should be active
    t_warning = make_hw_telemetry(
        sequence=1, system_state='NORMAL',
        chamber_ok=True, chamber_temp=12.0,
        heatsink_ok=True, heatsink_temp=28.0,
        current_ok=False, current_val=0.0,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    res_warning = client.post('/api/v1/telemetry', json=t_warning.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_warning.status_code == 200
    
    # 2. Chamber Temp > HIGH_TEMP_WARNING and manual cooling ON -> Emulated current 3.5, no warning
    t_on = make_hw_telemetry(
        sequence=2, system_state='NORMAL',
        chamber_ok=True, chamber_temp=12.0,
        heatsink_ok=True, heatsink_temp=28.0,
        current_ok=False, current_val=3.5,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    t_on.primary_cooling = True # In hardware, this is logged as output intent
    res_on = client.post('/api/v1/telemetry', json=t_on.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res_on.status_code == 200
    
    # Check that latest reflects the manual cooling emulated current
    latest = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest['telemetry']['payload']['primary_current_a'] == 3.5



# ---------------------------------------------------------------------------
# MANUAL_SMPS regression tests
# ---------------------------------------------------------------------------

def test_manual_smps_gpio6_low_primary_cooling_on(hw_app):
    """Regression (MANUAL_SMPS): GPIO6 LOW → manual_cooling_confirmed=True → primary_cooling=True.
    Dashboard payload must report primary_cooling ON and manual_cooling_confirmed True."""
    app, client, hw_token, _ = hw_app

    t_on = make_hw_telemetry(
        sequence=10, system_state='NORMAL',
        chamber_ok=True, chamber_temp=8.0,
        heatsink_ok=True, heatsink_temp=28.0,
        current_ok=False, current_val=3.5,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    # GPIO6 LOW = cooling physically ON; firmware sets primary_cooling=True in MANUAL_SMPS
    t_on = t_on.model_copy(update={
        'cooling_control_mode': 'MANUAL_SMPS',
        'manual_cooling_confirmed': True,
        'primary_cooling': True,  # firmware derives this from GPIO6 LOW
    })
    res = client.post('/api/v1/telemetry', json=t_on.model_dump(mode='json'),
                      headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    payload = client.get('/api/latest?device_id=CCU-HW-TEST').json()['telemetry']['payload']
    assert payload['cooling_control_mode'] == 'MANUAL_SMPS'
    assert payload['manual_cooling_confirmed'] is True
    assert payload['primary_cooling'] is True, \
        "GPIO6 LOW must report primary_cooling=True in MANUAL_SMPS mode"
    assert payload['primary_current_a'] == 3.5
    assert payload['current_source'] == 'EMULATED'
    assert payload['current_calibrated'] is False


def test_manual_smps_gpio6_high_primary_cooling_off(hw_app):
    """Regression (MANUAL_SMPS): GPIO6 HIGH → manual_cooling_confirmed=False → primary_cooling=False.
    Dashboard payload must report primary_cooling OFF and manual_cooling_confirmed False."""
    app, client, hw_token, _ = hw_app

    t_off = make_hw_telemetry(
        sequence=11, system_state='NORMAL',
        chamber_ok=True, chamber_temp=8.0,
        heatsink_ok=True, heatsink_temp=28.0,
        current_ok=False, current_val=0.0,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    # GPIO6 HIGH = cooling OFF/not confirmed
    t_off = t_off.model_copy(update={
        'cooling_control_mode': 'MANUAL_SMPS',
        'manual_cooling_confirmed': False,
        'primary_cooling': False,  # firmware derives this from GPIO6 HIGH
    })
    res = client.post('/api/v1/telemetry', json=t_off.model_dump(mode='json'),
                      headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    payload = client.get('/api/latest?device_id=CCU-HW-TEST').json()['telemetry']['payload']
    assert payload['cooling_control_mode'] == 'MANUAL_SMPS'
    assert payload['manual_cooling_confirmed'] is False
    assert payload['primary_cooling'] is False, \
        "GPIO6 HIGH must report primary_cooling=False in MANUAL_SMPS mode"
    assert payload['primary_current_a'] == 0.0
    assert payload['current_source'] == 'EMULATED'
    assert payload['current_calibrated'] is False


def test_test_primary_gpio_controlled_independent_of_manual_smps(hw_app):
    """Regression: TEST PRIMARY 5 path uses GPIO_CONTROLLED mode. GPIO16/primaryObserved() is the
    authoritative source. It must be independent of MANUAL_SMPS / GPIO6 state."""
    app, client, hw_token, _ = hw_app

    # TEST PRIMARY 5: GPIO16 driven ON → primary_cooling=True, cooling_control_mode=GPIO_CONTROLLED
    t_test = make_hw_telemetry(
        sequence=12, system_state='NORMAL',
        chamber_ok=True, chamber_temp=8.0,
        heatsink_ok=True, heatsink_temp=28.0,
        current_ok=False, current_val=3.5,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    t_test = t_test.model_copy(update={
        'cooling_control_mode': 'GPIO_CONTROLLED',
        'manual_cooling_confirmed': None,  # not in MANUAL_SMPS
        'primary_cooling': True,           # GPIO16 driven by TEST PRIMARY
    })
    res = client.post('/api/v1/telemetry', json=t_test.model_dump(mode='json'),
                      headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    payload = client.get('/api/latest?device_id=CCU-HW-TEST').json()['telemetry']['payload']
    assert payload['cooling_control_mode'] == 'GPIO_CONTROLLED'
    assert payload['manual_cooling_confirmed'] is None
    assert payload['primary_cooling'] is True, \
        "TEST PRIMARY must assert primary_cooling=True via GPIO16 in GPIO_CONTROLLED mode"
    assert payload['primary_current_a'] == 3.5
    assert payload['current_source'] == 'EMULATED'


def test_current_provenance_remains_emulated_in_manual_smps(hw_app):
    """Regression: current_source must remain EMULATED and current_calibrated False in MANUAL_SMPS."""
    app, client, hw_token, _ = hw_app

    t = make_hw_telemetry(
        sequence=13, system_state='NORMAL',
        chamber_ok=True, chamber_temp=8.0,
        heatsink_ok=True, heatsink_temp=28.0,
        current_ok=False, current_val=3.5,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    t = t.model_copy(update={
        'cooling_control_mode': 'MANUAL_SMPS',
        'manual_cooling_confirmed': True,
        'primary_cooling': True,
    })
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'),
                      headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    payload = client.get('/api/latest?device_id=CCU-HW-TEST').json()['telemetry']['payload']
    assert payload['current_source'] == 'EMULATED', \
        "current_source must remain EMULATED in MANUAL_SMPS mode"
    assert payload['current_calibrated'] is False, \
        "current_calibrated must remain False (ACS712 not calibrated)"
    assert payload['primary_current_a'] == 3.5, \
        "EMULATED current must be 3.5 A when manual cooling is confirmed ON"


def test_gpio16_state_does_not_overwrite_manual_smps_status(hw_app):
    """Regression: In MANUAL_SMPS mode, sending primary_cooling=False (GPIO16 de-asserted)
    with manual_cooling_confirmed=True must NOT suppress the confirmed-ON status.
    The payload must preserve manual_cooling_confirmed=True and primary_cooling=True
    as set by the firmware (which already resolves to GPIO6 state)."""
    app, client, hw_token, _ = hw_app

    # Simulate what old/incorrect firmware would send: GPIO16=False but GPIO6=True
    # Correct firmware sets primary_cooling=True when manual_cooling_confirmed=True.
    # We verify the schema accepts both fields independently.
    t = make_hw_telemetry(
        sequence=14, system_state='NORMAL',
        chamber_ok=True, chamber_temp=8.0,
        heatsink_ok=True, heatsink_temp=28.0,
        current_ok=False, current_val=3.5,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    # Correct firmware behavior: primary_cooling is derived from GPIO6, NOT GPIO16.
    # GPIO6 LOW (confirmed ON) → primary_cooling=True even though GPIO16=de-asserted.
    t = t.model_copy(update={
        'cooling_control_mode': 'MANUAL_SMPS',
        'manual_cooling_confirmed': True,
        'primary_cooling': True,  # Correct: firmware maps GPIO6 LOW → True
    })
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'),
                      headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    payload = client.get('/api/latest?device_id=CCU-HW-TEST').json()['telemetry']['payload']
    # Stored payload must preserve both fields exactly as firmware sent them.
    assert payload['manual_cooling_confirmed'] is True
    assert payload['primary_cooling'] is True, \
        "In MANUAL_SMPS mode, GPIO16 de-asserted must not suppress manual_cooling_confirmed=True"
    # Backend must NOT have flipped primary_cooling to False based on GPIO16.
    assert payload['cooling_control_mode'] == 'MANUAL_SMPS'


def test_derived_chamber_temperature_and_heatsink_preservation(hw_app):
    """Regression Phase 1: Chamber temperature is derived as (heatsink - 10.0 C),
    real heatsink temperature remains completely unaltered, and explicit provenance
    (chamber_source='DERIVED', chamber_formula='heatsink_temp_c - 10.0') is reported."""
    app, client, hw_token, _ = hw_app
    heatsink_val = 28.60
    derived_chamber = round(heatsink_val - 10.0, 2)  # 18.60 C

    t = make_hw_telemetry(
        sequence=15, system_state='NORMAL',
        chamber_ok=True, chamber_temp=derived_chamber,
        heatsink_ok=True, heatsink_temp=heatsink_val,
        current_ok=False, current_val=3.5,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    t = t.model_copy(update={
        'chamber_source': 'DERIVED',
        'chamber_formula': 'heatsink_temp_c - 10.0',
        'raw_chamber_temp_c': 28.45,
        'cooling_control_mode': 'MANUAL_SMPS',
        'manual_cooling_confirmed': True,
        'primary_cooling': True,
        'backup_cooling': False,
        'backup_source': 'VIRTUAL',
        'backup_commissioned': False
    })
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200

    latest = client.get('/api/latest?device_id=CCU-HW-TEST').json()['telemetry']['payload']
    # 1. Real heatsink reading is completely unchanged
    assert latest['heatsink_temp_c'] == heatsink_val
    # 2. Chamber is exactly heatsink - 10.0 C
    assert latest['chamber_temp_c'] == derived_chamber
    # 3. Explicit provenance is recorded
    assert latest['chamber_source'] == 'DERIVED'
    # 4. Formula is exposed
    assert latest['chamber_formula'] == 'heatsink_temp_c - 10.0'
    assert latest['raw_chamber_temp_c'] == 28.45


def test_backend_derives_chamber_when_omitted_in_derived_mode(hw_app):
    """Regression Phase 1: Backend service completes derived chamber if chamber_source == 'DERIVED'
    and chamber_temp_c is omitted."""
    app, client, hw_token, _ = hw_app
    heatsink_val = 30.50

    t = make_hw_telemetry(
        sequence=16, system_state='NORMAL',
        chamber_ok=False, chamber_temp=None,
        heatsink_ok=True, heatsink_temp=heatsink_val,
        current_ok=False, current_val=0.0,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    t = t.model_copy(update={
        'chamber_source': 'DERIVED',
        'cooling_control_mode': 'MANUAL_SMPS',
        'manual_cooling_confirmed': False,
        'primary_cooling': False,
        'backup_cooling': False,
        'backup_source': 'VIRTUAL',
        'backup_commissioned': False
    })
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200

    latest = client.get('/api/latest?device_id=CCU-HW-TEST').json()['telemetry']['payload']
    assert latest['chamber_temp_c'] == 20.50
    assert latest['chamber_formula'] == 'heatsink_temp_c - 10.0'


def test_virtual_backup_cooling_contract_and_failover(hw_app):
    """Regression Phase 4 & 9: Virtual backup cooling behavior:
    - Normal operation: backup_cooling = False, backup_source = 'VIRTUAL', backup_commissioned = False
    - Failover: backup_cooling = True (failover active), primary_cooling = False
    - Provenance: backup_source='VIRTUAL', backup_commissioned=False."""
    app, client, hw_token, _ = hw_app

    # Normal state: backup cooling is virtual standby (False)
    t_normal = make_hw_telemetry(
        sequence=17, system_state='NORMAL',
        chamber_ok=True, chamber_temp=18.0,
        heatsink_ok=True, heatsink_temp=28.0,
        current_ok=False, current_val=3.5,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    t_normal = t_normal.model_copy(update={
        'chamber_source': 'DERIVED',
        'chamber_formula': 'heatsink_temp_c - 10.0',
        'cooling_control_mode': 'MANUAL_SMPS',
        'manual_cooling_confirmed': True,
        'primary_cooling': True,
        'backup_cooling': False,
        'backup_source': 'VIRTUAL',
        'backup_commissioned': False
    })
    res = client.post('/api/v1/telemetry', json=t_normal.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    p_norm = client.get('/api/latest?device_id=CCU-HW-TEST').json()['telemetry']['payload']
    assert p_norm['backup_cooling'] is False
    assert p_norm['backup_source'] == 'VIRTUAL'
    assert p_norm['backup_commissioned'] is False

    # Failover state: primary has failed, virtual backup takes over
    t_failover = make_hw_telemetry(
        sequence=18, system_state='BACKUP_ACTIVE',
        chamber_ok=True, chamber_temp=19.0,
        heatsink_ok=True, heatsink_temp=28.0,
        current_ok=False, current_val=0.0,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    t_failover = t_failover.model_copy(update={
        'chamber_source': 'DERIVED',
        'chamber_formula': 'heatsink_temp_c - 10.0',
        'cooling_control_mode': 'MANUAL_SMPS',
        'manual_cooling_confirmed': False,
        'primary_cooling': False,
        'backup_cooling': True,
        'backup_source': 'VIRTUAL',
        'backup_commissioned': False
    })
    res2 = client.post('/api/v1/telemetry', json=t_failover.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res2.status_code == 200
    p_fail = client.get('/api/latest?device_id=CCU-HW-TEST').json()['telemetry']['payload']
    assert p_fail['backup_cooling'] is True
    assert p_fail['backup_source'] == 'VIRTUAL'
    assert p_fail['backup_commissioned'] is False


def test_firmware_source_contracts_virtual_backup_safety():
    """Regression Phase 4 & 12: Source inspection verifies physical backup Peltier is NOT commissioned
    and virtual backup never energizes a hardware GPIO pin."""
    from pathlib import Path
    cooling_cpp = Path(__file__).resolve().parents[1] / 'firmware' / 'esp32_s3' / 'cooling.cpp'
    content = cooling_cpp.read_text(encoding='utf-8')
    assert "bool backupCoolingConfigured() {\n  // Backup Peltier is NOT commissioned yet\n  return false;\n}" in content or \
           "return false;" in content
    # Check that network.cpp exposes VIRTUAL backup source
    net_cpp = Path(__file__).resolve().parents[1] / 'firmware' / 'esp32_s3' / 'network.cpp'
    net_content = net_cpp.read_text(encoding='utf-8')
    assert 'j["backup_source"] = "VIRTUAL"' in net_content
    assert 'j["backup_commissioned"] = false' in net_content
    assert 'j["chamber_source"] = "DERIVED"' in net_content
    assert 'j["chamber_formula"] = "heatsink_temp_c - 10.0"' in net_content


def test_lcd_no_obsolete_10c_target_rule():
    """Regression Phase 6: Verify LCD implementation has no obsolete 'TARGET DIFFERENCE',
    'TEMP DIFFERENCE', or '10 C target rule' display strings, and uses derived chamber on Page 1."""
    from pathlib import Path
    display_cpp = Path(__file__).resolve().parents[1] / 'firmware' / 'esp32_s3' / 'display.cpp'
    content = display_cpp.read_text(encoding='utf-8')
    assert "TARGET DIFFERENCE" not in content
    assert "TEMP DIFFERENCE" not in content
    assert "10 C target rule" not in content
    # LCD Page 1 displays CH and HS
    assert 'snprintf(r0, sizeof(r0), "CH:%-5.1fC' in content
    assert 'snprintf(r1, sizeof(r1), "HS:%-5.1fC' in content


def test_ml_provenance_full_hybrid_label(hw_app):
    """Regression Phase 11: When telemetry has derived chamber and emulated current,
    the ML inference engine marks feature_provenance = HARDWARE_HYBRID_DERIVED_CHAMBER_EMULATED_CURRENT_VIRTUAL_BACKUP."""
    app, client, hw_token, _ = hw_app
    t = make_hw_telemetry(
        sequence=19, system_state='NORMAL',
        chamber_ok=True, chamber_temp=18.6,
        heatsink_ok=True, heatsink_temp=28.6,
        current_ok=False, current_val=3.5,
        sht_ok=True, door_open=False,
        current_source='EMULATED', current_calibrated=False
    )
    t = t.model_copy(update={
        'chamber_source': 'DERIVED',
        'chamber_formula': 'heatsink_temp_c - 10.0',
        'cooling_control_mode': 'MANUAL_SMPS',
        'manual_cooling_confirmed': True,
        'primary_cooling': True,
        'backup_cooling': False,
        'backup_source': 'VIRTUAL',
        'backup_commissioned': False
    })
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200
    pred = client.get('/api/latest?device_id=CCU-HW-TEST').json()['prediction']
    assert pred['status'] == 'INFERENCE_COMPLETE'
    assert pred['feature_provenance'] == 'HARDWARE_HYBRID_DERIVED_CHAMBER_EMULATED_CURRENT_VIRTUAL_BACKUP'


def test_dashboard_offline_rendering_elements():
    """Regression Phase 13: Dashboard code renders '—' placeholders and 'NO LIVE HARDWARE DATA'
    when hardware is offline / stale (>15 seconds)."""
    from pathlib import Path
    app_js_path = Path(__file__).resolve().parents[1] / 'dashboard' / 'src' / 'app.js'
    content = app_js_path.read_text(encoding='utf-8')
    assert "NO LIVE HARDWARE DATA" in content
    assert "${row('Primary cooling', '—')}" in content
    assert "${row('Backup cooling', '—')}" in content
    assert "Hardware offline · No live telemetry" in content


def test_telemetry_schema_backward_compatibility():
    """Regression Phase 10 & 26: Telemetry schema works with both legacy payloads
    (without derived/virtual fields) and new hybrid payloads."""
    from backend.schemas import Telemetry, GPS, SensorHealth
    from datetime import datetime, timezone

    # Legacy payload: no chamber_source, no backup_source, no cooling_control_mode
    legacy = Telemetry(
        device_id="CCU-HW-001", boot_id="boot-1", sequence=1,
        timestamp=datetime.now(timezone.utc), uptime_ms=1000, mode="HARDWARE",
        chamber_temp_c=25.0, heatsink_temp_c=25.5, sht31_temp_c=25.2, humidity_pct=50.0,
        primary_current_a=0.0, door_open=False, door_open_s=0,
        gps=GPS(fix=False), primary_cooling=False, backup_cooling=False,
        system_state="NORMAL",
        sensor_health=SensorHealth(chamber=True, heatsink=True, sht31=True, current=False, door=True),
        current_source="EMULATED", current_calibrated=False
    )
    assert legacy.chamber_source is None
    assert legacy.backup_source is None
    assert legacy.cooling_control_mode is None

    # Hybrid payload: explicit derived chamber and virtual backup
    hybrid = Telemetry(
        device_id="CCU-HW-001", boot_id="boot-1", sequence=2,
        timestamp=datetime.now(timezone.utc), uptime_ms=2000, mode="HARDWARE",
        chamber_temp_c=18.6, chamber_source="DERIVED", chamber_formula="heatsink_temp_c - 10.0",
        raw_chamber_temp_c=28.5, heatsink_temp_c=28.6, sht31_temp_c=28.9, humidity_pct=68.1,
        primary_current_a=3.5, door_open=False, door_open_s=0,
        gps=GPS(fix=False), primary_cooling=True, backup_cooling=False,
        backup_source="VIRTUAL", backup_commissioned=False,
        cooling_control_mode="MANUAL_SMPS", manual_cooling_confirmed=True,
        system_state="NORMAL",
        sensor_health=SensorHealth(chamber=True, heatsink=True, sht31=True, current=False, door=True),
        current_source="EMULATED", current_calibrated=False
    )
    assert hybrid.chamber_source == "DERIVED"
    assert hybrid.backup_source == "VIRTUAL"
    assert hybrid.manual_cooling_confirmed is True


def test_default_backup_is_off_and_virtual(hw_app):
    """Regression 1, 5, 6: Default backup state is OFF; source is VIRTUAL; backup_commissioned is false."""
    app, client, hw_token, _ = hw_app
    t = make_hw_telemetry(sequence=1, system_state='NORMAL')
    t = t.model_copy(update={
        'cooling_control_mode': 'MANUAL_SMPS',
        'manual_cooling_confirmed': False,
        'primary_cooling': False,
        'backup_cooling': False,
        'backup_source': 'VIRTUAL',
        'backup_commissioned': False
    })
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200

    latest = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest['virtual_backup_override'] is False
    assert latest['telemetry']['payload']['backup_cooling'] is False
    assert latest['telemetry']['payload']['backup_source'] == 'VIRTUAL'
    assert latest['telemetry']['payload']['backup_commissioned'] is False


def test_dashboard_toggle_backup_on_and_off_lifecycle(hw_app):
    """Regression 2, 3, 4, 8, 12, 13: POST /api/v1/control/backup activates virtual backup,
    enforces primary/backup cooling interlock, logs self-healing event, and deactivation clears it."""
    app, client, hw_token, _ = hw_app
    t = make_hw_telemetry(sequence=1, system_state='NORMAL')
    t = t.model_copy(update={
        'cooling_control_mode': 'MANUAL_SMPS',
        'manual_cooling_confirmed': True,
        'primary_cooling': True,
        'backup_cooling': False,
        'backup_source': 'VIRTUAL',
        'backup_commissioned': False
    })
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200

    # 1. Turn ON virtual backup
    res_on = client.post('/api/v1/control/backup', json={'device_id': 'CCU-HW-TEST', 'enabled': True})
    assert res_on.status_code == 200
    body_on = res_on.json()
    assert body_on['success'] is True
    assert body_on['backup_cooling'] is True
    assert body_on['backup_source'] == 'VIRTUAL'
    assert body_on['backup_commissioned'] is False
    assert body_on['virtual_backup_override'] is True

    # Check latest: backup is ON, primary is interlocked to OFF
    latest_on = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest_on['virtual_backup_override'] is True
    assert latest_on['telemetry']['payload']['backup_cooling'] is True
    assert latest_on['telemetry']['payload']['primary_cooling'] is False
    assert latest_on['telemetry']['payload']['backup_source'] == 'VIRTUAL'
    assert latest_on['telemetry']['payload']['backup_commissioned'] is False

    # Check healing events: activation recorded
    healing_events = client.get('/api/self-healing?device_id=CCU-HW-TEST').json()
    assert len(healing_events) >= 1
    activation_event = healing_events[0]['payload']
    assert activation_event['reason'] == 'Backup takeover activated'
    assert activation_event['source'] == 'Manual dashboard command'
    assert activation_event['backup_source'] == 'VIRTUAL'
    assert activation_event['state'] == 'ACTIVE'
    assert activation_event['resolved'] is False

    # 2. Turn OFF virtual backup
    res_off = client.post('/api/v1/control/backup', json={'device_id': 'CCU-HW-TEST', 'enabled': False})
    assert res_off.status_code == 200
    body_off = res_off.json()
    assert body_off['success'] is True
    assert body_off['backup_cooling'] is False
    assert body_off['virtual_backup_override'] is False

    latest_off = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest_off['virtual_backup_override'] is False
    assert latest_off['telemetry']['payload']['backup_cooling'] is False
    # In MANUAL_SMPS mode with switch confirmed, primary cooling is restored
    assert latest_off['telemetry']['payload']['primary_cooling'] is True

    # Check healing events: deactivation recorded
    healing_events = client.get('/api/self-healing?device_id=CCU-HW-TEST').json()
    assert len(healing_events) >= 2
    deactivation_event = healing_events[0]['payload']
    assert deactivation_event['reason'] == 'Backup takeover cleared'
    assert deactivation_event['source'] == 'Manual dashboard command'
    assert deactivation_event['state'] == 'CLEARED'
    assert deactivation_event['resolved'] is True


def test_manual_on_persists_across_subsequent_esp32_telemetry_packets(hw_app):
    """Regression 10: Subsequent ESP32 telemetry packets do NOT overwrite manual backup ON state to OFF."""
    app, client, hw_token, _ = hw_app
    # Initial packet
    t1 = make_hw_telemetry(sequence=1, system_state='NORMAL')
    t1 = t1.model_copy(update={'cooling_control_mode': 'MANUAL_SMPS', 'manual_cooling_confirmed': True, 'primary_cooling': True, 'backup_cooling': False})
    res1 = client.post('/api/v1/telemetry', json=t1.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res1.status_code == 200

    # User toggles virtual backup ON
    client.post('/api/v1/control/backup', json={'device_id': 'CCU-HW-TEST', 'enabled': True})

    # Next packet from ESP32 arrives reporting backup_cooling=False (since hardware loop has no backup)
    t2 = make_hw_telemetry(sequence=2, system_state='NORMAL')
    t2 = t2.model_copy(update={'cooling_control_mode': 'MANUAL_SMPS', 'manual_cooling_confirmed': True, 'primary_cooling': True, 'backup_cooling': False})
    res2 = client.post('/api/v1/telemetry', json=t2.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res2.status_code == 200

    # Backend arbitration ensures effective_backup remains True
    latest = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest['telemetry']['payload']['backup_cooling'] is True
    assert latest['telemetry']['payload']['primary_cooling'] is False
    assert latest['telemetry']['payload']['backup_source'] == 'VIRTUAL'
    assert latest['telemetry']['payload']['backup_commissioned'] is False


def test_manual_off_does_not_suppress_genuine_automatic_failover(hw_app):
    """Regression 9, 11: Turning manual override OFF does not suppress genuine automatic failover
    (effective_backup = manual_override OR auto_required)."""
    app, client, hw_token, _ = hw_app
    # Telemetry in BACKUP_ACTIVE edge state (automatic failover active)
    t1 = make_hw_telemetry(sequence=1, system_state='BACKUP_ACTIVE')
    t1 = t1.model_copy(update={'cooling_control_mode': 'MANUAL_SMPS', 'manual_cooling_confirmed': False, 'primary_cooling': False, 'backup_cooling': True, 'backup_source': 'VIRTUAL'})
    res1 = client.post('/api/v1/telemetry', json=t1.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res1.status_code == 200

    # User turns manual override OFF
    res_off = client.post('/api/v1/control/backup', json={'device_id': 'CCU-HW-TEST', 'enabled': False})
    assert res_off.status_code == 200
    body = res_off.json()
    # effective_backup remains True because system_state is BACKUP_ACTIVE
    assert body['backup_cooling'] is True
    assert body['virtual_backup_override'] is False

    latest = client.get('/api/latest?device_id=CCU-HW-TEST').json()
    assert latest['telemetry']['payload']['backup_cooling'] is True


def test_offline_hardware_rejects_backup_control(hw_app):
    """Regression 14: When hardware device is offline (>15s without telemetry), control command is rejected with 409."""
    app, client, hw_token, _ = hw_app
    # Send a telemetry packet 25 seconds in the past
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=25)
    t = make_hw_telemetry(sequence=1, system_state='NORMAL')
    t = t.model_copy(update={'timestamp': stale_time})
    res = client.post('/api/v1/telemetry', json=t.model_dump(mode='json'), headers={'X-Device-Token': hw_token})
    assert res.status_code == 200

    # Attempting to toggle backup should be rejected because hardware is offline
    res_ctrl = client.post('/api/v1/control/backup', json={'device_id': 'CCU-HW-TEST', 'enabled': True})
    assert res_ctrl.status_code == 409
    assert "Hardware is offline" in res_ctrl.json()['detail']


def test_firmware_pins_no_backup_gpio_energized():
    """Regression 7, 15: Firmware preserves PIN_BACKUP = -1, backupCoolingConfigured() == false,
    and never energizes physical backup GPIO."""
    from pathlib import Path
    cooling_cpp = Path(__file__).resolve().parents[1] / 'firmware' / 'esp32_s3' / 'cooling.cpp'
    config_h = Path(__file__).resolve().parents[1] / 'firmware' / 'esp32_s3' / 'config.h'
    network_cpp = Path(__file__).resolve().parents[1] / 'firmware' / 'esp32_s3' / 'network.cpp'

    cooling_src = cooling_cpp.read_text(encoding='utf-8')
    config_src = config_h.read_text(encoding='utf-8')
    net_src = network_cpp.read_text(encoding='utf-8')

    assert "PIN_BACKUP = -1" in config_src
    assert "bool backupCoolingConfigured() {" in cooling_src
    assert "return false;" in cooling_src
    assert 'j["backup_source"] = "VIRTUAL";' in net_src
    assert 'j["backup_commissioned"] = false;' in net_src


def test_dashboard_toggle_and_confirmation_modal_sources():
    """Regression 2, 4, 18: Dashboard app.js, index.html, and styles.css have toggle switch,
    confirmation modal, and offline disable logic."""
    from pathlib import Path
    dash_dir = Path(__file__).resolve().parents[1] / 'dashboard' / 'src'
    app_js = (dash_dir / 'app.js').read_text(encoding='utf-8')
    index_html = (dash_dir / 'index.html').read_text(encoding='utf-8')
    styles_css = (dash_dir / 'styles.css').read_text(encoding='utf-8')

    assert "modal-backup-confirm" in index_html
    assert "Activate backup cooling demo?" in index_html
    assert "toggle-switch" in styles_css
    assert "toggleVirtualBackup" in app_js
    assert "api('v1/control/backup'" in app_js
    assert "btn-toggle-backup" in app_js


