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
                      current_ok=False, current_val=None, sht_ok=False, door_open=False):
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
        sht31_temp_c=None,
        humidity_pct=None,
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
        buffered=False
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
