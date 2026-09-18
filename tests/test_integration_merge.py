from datetime import datetime, timezone, timedelta
import hashlib
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from backend.main import create_app
from backend.archive import import_legacy
from database.models import ControlCommand, ArchiveRecord, database
from simulator.engine import Simulator
from simulator.client import exchange

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = 'integration-test-operator-token'

@pytest.fixture
def integrated(tmp_path):
    app = create_app(f'sqlite:///{tmp_path/"integrated.db"}', admin_token=OPERATOR)
    with TestClient(app) as client:
        client.headers['Authorization'] = 'Bearer '+OPERATOR
        token = client.post('/api/devices', json={'device_id':'MERGED', 'name':'Test', 'mode':'SIMULATION'}).json()['device_token']
        client.headers['X-Device-Token'] = token
        yield app, client

def initial(client, scenario='normal'):
    sim = Simulator('MERGED', scenario=scenario)
    telemetry, _, _ = sim.step()
    response = client.post('/api/v1/telemetry', json=telemetry.model_dump(mode='json'))
    assert response.status_code == 200, response.text
    return sim, telemetry, response.json()['command']

def test_closed_loop_recovers_and_confirms_commands(integrated):
    _, client = integrated
    sim = Simulator('MERGED', scenario='primary_failure')
    states = set()
    for _ in range(100):
        t, _, _ = sim.step()
        result = exchange(client, sim, t)
        states.add(result['decision']['state'])
    assert {'PRIMARY_FAULT','BACKUP_ACTIVE','RECOVERY'} <= states
    commands = client.get('/api/v1/control/MERGED/history').json()['commands']
    assert any(c['command_type']=='ACTIVATE_BACKUP_COOLING' and c['status']=='CONFIRMED' for c in commands)
    assert all(not (c['primary_cooling'] and c['backup_cooling']) for c in commands)
    faults = client.get('/api/faults?device_id=MERGED').json()
    primary = [f['payload'] for f in faults if f['payload']['fault_type']=='PRIMARY_FAILURE']
    assert len(primary)==1 and primary[0]['resolved']
    assert primary[0]['resolution']=='MITIGATED_BY_BACKUP'
    assert not primary[0]['hardware_repair_verified']
    exported=client.get('/api/history/export?device_id=MERGED')
    assert exported.status_code==200 and len(exported.json())==100
    assert exported.json()[0]['sequence']==1 and exported.json()[-1]['sequence']==100
    assert len(client.get('/api/history?device_id=MERGED&limit=10&offset=95').json())==5

def test_duplicate_does_not_repeat_command_or_action(integrated):
    _, client = integrated
    sim, t, command = initial(client)
    response = client.post('/api/v1/telemetry', json=t.model_dump(mode='json')).json()
    assert response['duplicate'] and not response['stored'] and response['command'] is None
    assert len(client.get('/api/commands?device_id=MERGED').json())==1

def test_ack_is_idempotent_but_needs_later_telemetry(integrated):
    _, client = integrated
    sim, _, command = initial(client)
    ack = sim.acknowledgement(command)
    path = f'/api/v1/control/{command["id"]}/acknowledge'
    first = client.post(path, json=ack)
    assert first.status_code==200 and first.json()['status']=='ACKNOWLEDGED'
    assert client.post(path, json=ack).json()==first.json()
    t, _, _ = sim.step()
    exchange(client, sim, t)
    assert client.post(path, json=ack).json()['status']=='CONFIRMED'

def test_device_token_cannot_poll_or_ack_another_device(integrated):
    _, client = integrated
    sim, _, command = initial(client)
    other = client.post('/api/devices', json={'device_id':'OTHER','name':'Other','mode':'SIMULATION'}).json()['device_token']
    assert client.get('/api/v1/control/MERGED/pending', headers={'X-Device-Token':other}).status_code==401
    assert client.post(f'/api/v1/control/{command["id"]}/acknowledge', json=sim.acknowledgement(command),
        headers={'X-Device-Token':other}).status_code==401

@pytest.mark.parametrize('change', [{'boot_id':'wrong-boot'},{'sequence':0},{'primary_cooling':False}])
def test_invalid_acknowledgements_rejected(integrated, change):
    _, client = integrated
    sim, _, command = initial(client)
    assert client.post(f'/api/v1/control/{command["id"]}/acknowledge',
        json={**sim.acknowledgement(command),**change}).status_code==409

def test_expired_command_is_persisted_and_cannot_be_applied(integrated):
    app, client = integrated
    sim, _, command = initial(client)
    with app.state.service.Session.begin() as session:
        row=session.get(ControlCommand,command['id'])
        row.expires_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    assert client.post(f'/api/v1/control/{command["id"]}/acknowledge',json=sim.acknowledgement(command)).status_code==409
    assert client.get('/api/v1/control/MERGED/pending').json()['command'] is None
    assert client.get('/api/commands?device_id=MERGED').json()[0]['status']=='EXPIRED'

def test_reboot_supersedes_pending_command(integrated):
    _, client = integrated
    sim, t, command=initial(client)
    replacement=Simulator('MERGED',start=t.timestamp+timedelta(seconds=1))
    t2,_,_=replacement.step()
    client.post('/api/telemetry',json=t2.model_dump(mode='json')).raise_for_status()
    old=next(c for c in client.get('/api/commands?device_id=MERGED').json() if c['id']==command['id'])
    assert old['status']=='SUPERSEDED'
    assert client.post(f'/api/v1/control/{command["id"]}/acknowledge',json=sim.acknowledgement(command)).status_code==409

def test_critical_moving_gps_creates_one_recommendation(integrated):
    _,client=integrated
    sim=Simulator('MERGED',scenario='backup_failure')
    for _ in range(100):
        t,_,_=sim.step()
        exchange(client,sim,t)
    routes=client.get('/api/v1/rerouting/MERGED/history').json()['events']
    assert len(routes)==1 and routes[0]['payload']['status']=='SELECTED'
    assert routes[0]['payload']['triggered_by_fault'] is not None

def test_missing_gps_can_recover_without_duplicate_incident(integrated):
    _,client=integrated
    sim=Simulator('MERGED',scenario='overheat')
    t,_,_=sim.step()
    t=t.model_copy(update={'gps':t.gps.model_copy(update={
        'fix':False,'source':'NONE','latitude':None,'longitude':None,'speed_kmph':None,'age_s':None})})
    client.post('/api/telemetry',json=t.model_dump(mode='json')).raise_for_status()
    assert client.get('/api/rerouting?device_id=MERGED').json()[0]['payload']['status']=='NO_GPS_FIX'
    t,_,_=sim.step()
    client.post('/api/telemetry',json=t.model_dump(mode='json')).raise_for_status()
    rows=client.get('/api/rerouting?device_id=MERGED').json()
    assert len(rows)==1 and rows[0]['payload']['status']=='SELECTED'

def test_archive_import_lossless_idempotent_readonly(integrated):
    app,client=integrated
    archives=client.get('/api/archive').json()
    assert len(archives)==3
    for source in archives:
        path=ROOT/'archive/databases'/source['source_name']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==source['source_sha256']
        result=import_legacy(app.state.service,path)
        assert result['already_imported']
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as old:
            old.row_factory=sqlite3.Row
            for table,count in source['table_counts'].items():
                result=client.get(f'/api/archive/{source["source_sha256"]}/{table}?limit=2000').json()
                original=[dict(r) for r in old.execute(f'SELECT * FROM "{table}"')]
                assert result['total']==count
                assert sorted(map(str,result['records']))==sorted(map(str,original))
                assert not result['control_replayed']
    with app.state.service.Session() as session:
        assert session.scalar(select(func.count()).select_from(ArchiveRecord))==188
    assert client.get('/api/commands?device_id=MERGED').json()==[]

def test_archive_pagination_and_auth(integrated):
    _,client=integrated
    source=next(x for x in client.get('/api/archive').json() if x['source_name']=='cold_chain.db')
    url=f'/api/archive/{source["source_sha256"]}/telemetry'
    first=client.get(url+'?limit=50').json()
    second=client.get(url+'?limit=50&offset=50').json()
    assert first['total']==103 and len(first['records'])==50
    assert not {r['id'] for r in first['records']} & {r['id'] for r in second['records']}
    assert client.get(url,headers={'Authorization':'Bearer wrong'}).status_code==401

def test_old_database_rejected_without_modifying_it(tmp_path):
    original=(ROOT/'archive/databases/cold_chain.db').read_bytes()
    path=tmp_path/'old.db';path.write_bytes(original)
    with pytest.raises(RuntimeError,match='older project database'):
        database(f'sqlite:///{path}')
    assert path.read_bytes()==original
    with sqlite3.connect(path) as c:
        assert c.execute('select count(*) from telemetry').fetchone()[0]==103
        assert not c.execute("select name from sqlite_master where name='devices'").fetchone()

def test_reset_requires_fresh_safe_local_reset_evidence(integrated):
    _,client=integrated
    sim=Simulator('MERGED',scenario='overheat')
    t,_,_=sim.step()
    client.post('/api/telemetry',json=t.model_dump(mode='json')).raise_for_status()
    request={'boot_id':sim.boot_id,'reason':'Operator performed and reviewed a local manual reset'}
    path='/api/devices/MERGED/reconcile-reset'
    assert client.post(path,json=request).status_code==409
    # An independent local manual reset is simulated; API itself never resets the device.
    from backend.control import Controller
    sim.local=Controller();sim.scenario='normal';sim.heatsink=35;sim.chamber=6
    t,_,_=sim.step()
    result=client.post('/api/telemetry',json=t.model_dump(mode='json')).json()
    assert result['decision']['state']=='REROUTING'  # no silent cloud latch clearing
    assert client.post(path,json=request,headers={'Authorization':'Bearer wrong'}).status_code==401
    response=client.post(path,json=request)
    assert response.status_code==200,response.text
    assert response.json()['physical_command_sent'] is False
    t,_,_=sim.step()
    result=client.post('/api/telemetry',json=t.model_dump(mode='json')).json()
    assert result['decision']['state'] in ('NORMAL','WARNING')
