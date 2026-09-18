"""Local launcher. Run from any directory: python run.py [--no-browser]."""
import argparse, json, os, secrets, shutil, threading, webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8000)
    p.add_argument('--no-browser',action='store_true');p.add_argument('--no-simulator',action='store_true')
    args=p.parse_args()
    runtime=ROOT/'runtime';runtime.mkdir(exist_ok=True)
    secrets_path=runtime/'operator.json'
    if os.getenv('CC_ADMIN_TOKEN'):
        token=os.environ['CC_ADMIN_TOKEN']
    elif secrets_path.exists():
        token=json.loads(secrets_path.read_text())['operator_token']
    else:
        token=secrets.token_urlsafe(32)
        secrets_path.write_text(json.dumps({'operator_token':token}))
        try:secrets_path.chmod(0o600)
        except OSError:pass
    for f in (ROOT/'dashboard/src').iterdir():
        dest=ROOT/'dashboard/dist';dest.mkdir(exist_ok=True)
        shutil.copy2(f,dest/f.name)
    from backend.main import create_app
    import uvicorn
    app=create_app(admin_token=token,run_simulation=not args.no_simulator)
    url=f'http://127.0.0.1:{args.port}/#token={token}'
    print(f'\nCold Chain prototype: http://127.0.0.1:{args.port}\nOperator token: {token}\nHardware status: PENDING_HARDWARE\n')
    if not args.no_browser:
        threading.Timer(1.5,lambda:webbrowser.open(url)).start()
    uvicorn.run(app,host=args.host,port=args.port,workers=1)

if __name__=='__main__':main()
