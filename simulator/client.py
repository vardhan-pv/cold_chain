"""Authenticated simulator client, command polling and retry-safe acknowledgements."""
import argparse
import json
import os
import time
from pathlib import Path
import httpx
from simulator.engine import Simulator, SCENARIOS

ROOT = Path(__file__).resolve().parents[1]
ALIASES = {'primary_fault': 'primary_failure', 'critical_fault': 'backup_failure'}

def exchange(client, sim, telemetry):
    """One network cycle. Local control has already run, even if this fails."""
    if not sim.network_available():
        raise httpx.ConnectError('Injected link loss')
    while sim.queue:
        response = client.post('/api/telemetry', json=sim.queue[0].model_dump(mode='json'))
        response.raise_for_status()
        sim.queue.pop(0)
    response = client.post('/api/telemetry', json=telemetry.model_dump(mode='json'))
    response.raise_for_status()
    result = response.json()
    if result.get('prediction'):
        sim.last_prediction = result['prediction']
    command_response = client.get(f'/api/v1/control/{sim.device_id}/pending')
    command_response.raise_for_status()
    command = command_response.json()['command']
    if command:
        ack = client.post(f"/api/v1/control/{command['id']}/acknowledge", json=sim.acknowledgement(command))
        ack.raise_for_status()
        result['acknowledgement'] = ack.json()
    return result

def credentials(args):
    if os.getenv('CC_DEVICE_TOKEN'):
        return os.environ['CC_DEVICE_TOKEN']
    runtime = ROOT/'runtime'
    path = runtime/'simulator_devices.json'
    stored = json.loads(path.read_text()) if path.exists() else {}
    key = args.url.rstrip('/') + '/' + args.device_id
    if key in stored:
        return stored[key]
    if not args.register:
        raise SystemExit('Set CC_DEVICE_TOKEN or use --register with the running local server.')
    operator = os.getenv('CC_ADMIN_TOKEN')
    if not operator and (runtime/'operator.json').exists():
        operator = json.loads((runtime/'operator.json').read_text())['operator_token']
    if not operator:
        raise SystemExit('Start python run.py first, or set CC_ADMIN_TOKEN to register the simulator.')
    with httpx.Client(base_url=args.url, timeout=10, trust_env=False) as client:
        response = client.post('/api/devices', headers={'Authorization': 'Bearer '+operator},
            json={'device_id': args.device_id, 'name': 'Standalone simulator', 'mode': 'SIMULATION'})
        if response.status_code == 409:
            raise SystemExit('Device already registered. Supply its CC_DEVICE_TOKEN or choose a new --device-id.')
        response.raise_for_status()
    stored[key] = response.json()['device_token']
    runtime.mkdir(exist_ok=True)
    path.write_text(json.dumps(stored, indent=2))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return stored[key]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--device-id', default='CCU-001')
    parser.add_argument('--scenario', choices=SCENARIOS+list(ALIASES), default='normal')
    parser.add_argument('--samples', type=int, default=0, help='0 runs until Ctrl+C')
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--register', action='store_true', help='Register once using operator credentials')
    args = parser.parse_args()
    if args.interval <= 0 or args.samples < 0:
        parser.error('interval must be positive; samples must be non-negative')
    token = credentials(args)
    scenario = ALIASES.get(args.scenario, args.scenario)
    sim = Simulator(args.device_id, scenario=scenario)
    print(f'SIMULATION · {args.device_id} · {scenario} · Ctrl+C to stop')
    try:
        with httpx.Client(base_url=args.url.rstrip('/'), timeout=3, trust_env=False,
                headers={'X-Device-Token': token}) as client:
            while not args.samples or sim.sequence < args.samples:
                began = time.monotonic()
                t, decision, _ = sim.step(dt=args.interval)
                try:
                    result = exchange(client, sim, t)
                    ack = result.get('acknowledgement', {}).get('status', 'NONE')
                    print(f'{t.sequence}: {decision["state"]} | stored={result["stored"]} | ACK={ack}')
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in (401, 403):
                        raise SystemExit('Authentication failed. Check the server and device token.') from exc
                    if exc.response.status_code >= 500:
                        sim.enqueue(t)
                    print(f'HTTP {exc.response.status_code}; local state={decision["state"]}')
                except httpx.TransportError:
                    sim.enqueue(t)
                    print(f'Buffered {t.sequence}; local state={decision["state"]}')
                time.sleep(max(0, args.interval-(time.monotonic()-began)))
    except KeyboardInterrupt:
        print('\nSimulator stopped; no physical hardware was controlled.')

if __name__ == '__main__':
    main()
