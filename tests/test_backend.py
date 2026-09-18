from datetime import timedelta,datetime,timezone
import pytest
from pydantic import ValidationError
from backend.schemas import Telemetry
from backend.main import create_app
from fastapi.testclient import TestClient
from simulator.engine import Simulator
from tests.conftest import registered,TOKEN

def send(c,t,token):
    return c.post('/api/telemetry',json=t.model_dump(mode='json'),headers={'X-Device-Token':token})

def test_complete_http_flow(client):
    token=registered(client)
    sim=Simulator('TEST-SIM',scenario='backup_failure')
    states=set()
    for _ in range(65):
        t,_,_=sim.step();r=send(client,t,token)
        assert r.status_code==200,r.text
        body=r.json();sim.last_prediction=body['prediction']
        states.add(body['decision']['state'])
        assert not (body['decision']['primary_cooling'] and body['decision']['backup_cooling'])
    assert {'WARNING','PRIMARY_FAULT','BACKUP_ACTIVE','CRITICAL_FAILURE','REROUTING'}<=states
    latest=client.get('/api/latest?device_id=TEST-SIM').json()
    assert latest['prediction']['status']=='INFERENCE_COMPLETE'
    assert latest['prediction']['training_provenance']=='SIMULATED_DATA'
    assert latest['rerouting']['status']=='SELECTED'
    assert latest['rerouting']['selected']['source']=='SIMULATED'
    for path in ('history','predictions','faults','self-healing','rerouting','system-health'):
        assert client.get('/api/'+path+'?device_id=TEST-SIM').json()
    assert len(client.get('/api/history?device_id=TEST-SIM').json())==65

def test_authentication_and_device_isolation(client):
    token=registered(client)
    other=registered(client,'OTHER')
    t,_,_=Simulator('TEST-SIM').step()
    assert send(client,t,'wrong').status_code==401
    assert send(client,t,other).status_code==401
    assert client.get('/api/devices',headers={'Authorization':'Bearer invalid'}).status_code==401
    assert send(client,t,token).status_code==200
    assert 'token_hash' not in client.get('/api/devices').text
    assert client.post('/api/devices',json={'device_id':'TEST-SIM','name':'overwrite','mode':'HARDWARE'}).status_code==409

def test_duplicate_and_out_of_order(client):
    token=registered(client);sim=Simulator('TEST-SIM')
    t,_,_=sim.step();assert send(client,t,token).status_code==200
    assert send(client,t,token).json()['duplicate']
    changed=t.model_copy(update={'chamber_temp_c':22})
    assert send(client,changed,token).status_code==409
    newer,_,_=sim.step();send(client,newer,token)
    old=t.model_copy(update={'sequence':99,'timestamp':t.timestamp-timedelta(seconds=2)})
    result=send(client,old,token).json()
    assert result['archived'] and result['decision'] is None
    assert client.get('/api/latest?device_id=TEST-SIM').json()['telemetry']['sequence']==2

def test_buffered_readings_do_not_actuate(client):
    token=registered(client);t,_,_=Simulator('TEST-SIM',scenario='overheat').step()
    t=t.model_copy(update={'buffered':True})
    r=send(client,t,token).json()
    assert r['archived'] and r['decision'] is None
    assert not client.get('/api/faults?device_id=TEST-SIM').json()

@pytest.mark.parametrize('change',[
    {'primary_cooling':True,'backup_cooling':True},
    {'humidity_pct':101},{'chamber_temp_c':float('nan')},
    {'timestamp':'2026-09-16T12:00:00'},
    {'chamber_temp_c':None},
    {'gps':{'fix':True,'latitude':12,'longitude':77,'source':'SIMULATED','age_s':31}},
    {'mode':'HARDWARE'}, {'pressure_bar':5}])
def test_contract_rejects_invalid_data(change):
    t,_,_=Simulator().step();data=t.model_dump(mode='json');data.update(change)
    with pytest.raises(ValidationError):Telemetry.model_validate(data)

def test_invalid_sensor_is_preserved_and_not_given_fake_probability(client):
    token=registered(client);t,_,_=Simulator('TEST-SIM',scenario='sensor_failure').step()
    result=send(client,t,token).json()
    assert result['prediction']['ensemble_probability'] is None
    assert result['decision']['state']=='CRITICAL_FAILURE'
    assert client.get('/api/latest?device_id=TEST-SIM').json()['telemetry']['payload']['chamber_temp_c'] is None

def test_hardware_future_clock_and_mode(client):
    token=registered(client,'HW','HARDWARE');t,_,_=Simulator('HW').step()
    t=t.model_copy(update={'mode':'HARDWARE','gps':t.gps.model_copy(update={'source':'GPS'}),
        'timestamp':datetime.now(timezone.utc)+timedelta(minutes=5)})
    assert send(client,t,token).status_code==422
    t=t.model_copy(update={'mode':'SIMULATION','gps':t.gps.model_copy(update={'source':'SIMULATED'})})
    assert send(client,t,token).status_code==409

def test_restart_restores_controller_latch(tmp_path):
    url=f'sqlite:///{tmp_path / "persist.db"}'
    sim=Simulator('PERSIST',scenario='overheat')
    with TestClient(create_app(url,admin_token=TOKEN)) as c:
        c.headers['Authorization']='Bearer '+TOKEN
        token=registered(c,'PERSIST');t,_,_=sim.step()
        assert send(c,t,token).json()['decision']['state']=='CRITICAL_FAILURE'
    with TestClient(create_app(url,admin_token=TOKEN)) as c:
        c.headers['Authorization']='Bearer '+TOKEN
        t,_,_=sim.step()
        r=send(c,t,token).json()
        assert r['decision']['state']=='REROUTING'
        assert r['decision']['primary_cooling'] is False and r['decision']['backup_cooling'] is False

def test_validation_does_not_invent_measurements(client):
    registered(client)
    r=client.get('/api/validation?device_id=TEST-SIM').json()
    assert all(m['value'] is None for m in r['metrics'])
    assert next(m for m in r['metrics'] if m['metric']=='backup_current_a')['status']=='UNAVAILABLE_NO_SENSOR'
    assert client.get('/api/validation/export?device_id=TEST-SIM&format=csv').headers['content-type'].startswith('text/csv')
    payload=dict(device_id='TEST-SIM',metric='cooldown_s',value=45,mode='HARDWARE',
        evidence='A simulated test is not hardware evidence',measured_at=datetime.now(timezone.utc).isoformat())
    assert client.post('/api/validation',json=payload).status_code==409

def test_limits_unknown_device_and_route_alias(client):
    assert client.get('/api/history?device_id=unknown').status_code==404
    assert client.get('/api/history?device_id=unknown&limit=999999').status_code==422
    registered(client)
    assert client.get('/api/v1/status/TEST-SIM').status_code==200

def test_reconnection_respects_fault_detected_offline(client):
    token=registered(client);sim=Simulator('TEST-SIM')
    for _ in range(3):
        t,_,_=sim.step();send(client,t,token)
    sim.scenario='backup_failure'
    for _ in range(70):
        t,_,_=sim.step();sim.enqueue(t)
    for t in sim.queue:
        assert send(client,t,token).json()['decision'] is None
    t,_,_=sim.step();result=send(client,t,token).json()
    assert result['decision']['state']=='REROUTING'
    assert result['decision']['primary_cooling'] is False
    assert client.get('/api/latest?device_id=TEST-SIM').json()['rerouting']['status']=='SELECTED'

def test_nonfinite_http_input_is_422_not_server_error(client):
    token=registered(client);t,_,_=Simulator('TEST-SIM').step()
    raw=t.model_dump_json().replace('"chamber_temp_c":'+str(t.chamber_temp_c),'"chamber_temp_c":NaN')
    response=client.post('/api/telemetry',content=raw,headers={'X-Device-Token':token,'Content-Type':'application/json'})
    assert response.status_code==422,response.text
