"""Run the delivered launcher and original simulator CLI in an isolated project copy."""
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory() as temporary:
        project=Path(temporary)/'cold_chain_project'
        shutil.copytree(ROOT,project,ignore=shutil.ignore_patterns('runtime','__pycache__','.pytest_cache','.pio','.venv','node_modules'))
        token=secrets.token_urlsafe(32)
        env={**os.environ,'CC_ADMIN_TOKEN':token}
        env.pop('CC_DEVICE_TOKEN',None);env.pop('CC_DATABASE_URL',None);env.pop('CC_MODEL_DIR',None)
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
        base=f'http://127.0.0.1:{port}'
        with (Path(temporary)/'server.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'run.py','--no-browser','--port',str(port)],
                cwd=project,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                with httpx.Client(base_url=base,trust_env=False,timeout=5,
                        headers={'Authorization':'Bearer '+token}) as client:
                    for _ in range(200):
                        if process.poll() is not None:raise AssertionError('Launcher exited before readiness')
                        try:
                            if client.get('/health').status_code==200:break
                        except httpx.TransportError:pass
                        time.sleep(.05)
                    else:raise AssertionError('Launcher did not become ready')
                    assert client.get('/').status_code==200
                    result=subprocess.run([sys.executable,'simulator/simulator.py','--register',
                        '--url',base,'--device-id','LAUNCH-SMOKE','--scenario','primary_fault',
                        '--samples','3','--interval','.05'],cwd=project,env=env,
                        capture_output=True,text=True,timeout=30)
                    assert result.returncode==0,result.stderr
                    history=client.get('/api/history?device_id=LAUNCH-SMOKE').json()
                    assert len(history)==3
                    assert 'primary_failure' in result.stdout
                    assert len(client.get('/api/archive').json())==3
                    assert len(client.get('/api/history/export?device_id=LAUNCH-SMOKE').json())==3
                    assert (project/'runtime/simulator_devices.json').exists()
                    assert client.get('/api/system-status').json()['ml_ready']
                    report={'status':'PASS','scope':'Linux launch and CLI in isolated delivery copy',
                        'launcher':'run.py','legacy_entry_point':'simulator/simulator.py',
                        'scenario_alias':'primary_fault -> primary_failure','readings':3,
                        'registration':'Operator credential exchanged for scoped simulator token',
                        'archive_sources':3,'model_inference':'READY','windows_execution':'NOT_TESTED'}
                    (ROOT/'docs/evidence/launcher-smoke.json').write_text(json.dumps(report,indent=2)+'\n')
                    print(json.dumps(report,indent=2))
            finally:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)

if __name__=='__main__':main()
