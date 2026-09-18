"""Start a real Uvicorn server; drive its HTTP endpoints and optionally the dashboard DOM."""
import json,os,secrets,socket,subprocess,threading,time,tempfile
from pathlib import Path
import httpx,uvicorn
from backend.main import create_app
from simulator.engine import Simulator,SCENARIOS
from simulator.client import exchange

ROOT=Path(__file__).resolve().parents[1]

def main():
    token=secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory() as td:
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
        app=create_app(f'sqlite:///{Path(td)/"live.db"}',admin_token=token,run_simulation=True)
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning'))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        base=f'http://127.0.0.1:{port}'
        try:
            with httpx.Client(base_url=base,trust_env=False,timeout=10,
                              headers={'Authorization':'Bearer '+token}) as client:
                for _ in range(100):
                    if server.started:break
                    time.sleep(.05)
                assert client.get('/health').status_code==200
                assert client.get('/').status_code==200
                for asset in ('app.js','styles.css','icon.svg'):
                    assert client.get('/assets/'+asset).status_code==200
                reports=[]
                for i,scenario in enumerate(SCENARIOS):
                    device=f'HTTP-{i:02d}'
                    r=client.post('/api/devices',json={'device_id':device,'name':scenario,'mode':'SIMULATION'})
                    assert r.status_code==201,r.text
                    device_token=r.json()['device_token'];sim=Simulator(device,scenario=scenario)
                    states=set();acknowledgements=0;outage_samples=0
                    for sample in range(80):
                        if scenario in ('wifi_failure','backend_failure'):
                            sim.scenario=scenario if 20<=sample<40 else 'normal'
                        t,_,_=sim.step()
                        client.headers['X-Device-Token']=device_token
                        try:
                            result=exchange(client,sim,t)
                        except httpx.ConnectError:
                            sim.enqueue(t);outage_samples+=1
                            continue
                        states.add(result['decision']['state'])
                        acknowledgements+=int('acknowledgement' in result)
                        assert not(result['decision']['primary_cooling'] and result['decision']['backup_cooling'])
                    latest=client.get('/api/latest',params={'device_id':device}).json()
                    history=client.get('/api/history',params={'device_id':device}).json()
                    assert len(history)==80
                    assert sum(x['archived'] for x in history)==outage_samples
                    commands=client.get(f'/api/v1/control/{device}/history').json()['commands']
                    routes=client.get(f'/api/v1/rerouting/{device}/history').json()['events']
                    if routes:assert len(routes)==1
                    if scenario=='primary_failure':
                        assert any(c['command_type']=='ACTIVATE_BACKUP_COOLING' and c['status']=='CONFIRMED' for c in commands)
                    reports.append({'scenario':scenario,'samples':80,'states':sorted(states),'status':'PASS',
                        'command_acknowledgements':acknowledgements,'buffered_and_recovered':outage_samples,
                        'confirmed_commands':sum(c['status']=='CONFIRMED' for c in commands),
                        'rerouting_incidents':len(routes),
                        'rerouting_status':latest['rerouting']['status'] if latest['rerouting'] else None})
                backup=next(r for r in reports if r['scenario']=='backup_failure')
                assert {'PRIMARY_FAULT','BACKUP_ACTIVE','CRITICAL_FAILURE','REROUTING'}<=set(backup['states'])
                assert backup['rerouting_status']=='SELECTED'
                if os.getenv('CC_JSDOM_PATH'):
                    env={**os.environ,'CC_TEST_URL':base,'CC_TEST_TOKEN':token}
                    node=os.environ.get('CODEX_PRIMARY_RUNTIME_NODE','node')
                    subprocess.run([node,str(ROOT/'tests/dashboard_dom.cjs')],env=env,check=True)
                report={'status':'PASS','transport':'REAL_LOCAL_HTTP','total_samples':960,
                    'archive_sources':len(client.get('/api/archive').json()),
                    'hardware_verified':False,'scenarios':reports}
                (ROOT/'docs/evidence/live-integration.json').write_text(json.dumps(report,indent=2))
                print(json.dumps(report,indent=2))
        finally:
            server.should_exit=True;thread.join(timeout=10)
            assert not thread.is_alive(),'Server failed to stop cleanly'

if __name__=='__main__':main()
