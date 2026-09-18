"""Compute available physical measurements from a HARDWARE-only telemetry export.

Missing quantities remain pending. Simulation input is rejected explicitly.
"""
import argparse,csv,json,statistics
from datetime import datetime
from pathlib import Path

def analyze(rows,target=8.0,expected_samples=None):
    samples=[r.get('payload',r) for r in rows]
    if not samples or any(r['mode']!='HARDWARE' for r in samples):
        raise ValueError('Only a nonempty HARDWARE-only export may produce a hardware report')
    if len({(r['device_id'],r['boot_id']) for r in samples})!=1:
        raise ValueError('Analyze one device and one boot session at a time')
    unique={(r['boot_id'],r['sequence']):r for r in samples}
    samples=sorted(unique.values(),key=lambda r:datetime.fromisoformat(r['timestamp']))
    temps=[r for r in samples if r.get('chamber_temp_c') is not None]
    start=datetime.fromisoformat(samples[0]['timestamp'])
    cold=next((r for r in temps if r['chamber_temp_c']<=target),None)
    steady=[r['chamber_temp_c'] for r in temps[-12:]]
    def avg(key):
        values=[r[key] for r in samples if r.get(key) is not None]
        return statistics.mean(values) if values else None
    if expected_samples is not None and expected_samples<len(samples):
        raise ValueError('Expected generated samples cannot be smaller than received unique samples')
    values={'starting_temperature_c':temps[0]['chamber_temp_c'] if temps else None,
        'target_temperature_c':target,'minimum_temperature_c':min((r['chamber_temp_c'] for r in temps),default=None),
        'cooldown_s':(datetime.fromisoformat(cold['timestamp'])-start).total_seconds() if cold else None,
        'steady_state_temperature_c':statistics.mean(steady) if len(steady)==12 and max(steady)-min(steady)<=.5 and max(steady)<=target else None,
        'humidity_pct':avg('humidity_pct'),'primary_current_a':avg('primary_current_a'),
        'heatsink_temperature_c':avg('heatsink_temp_c'),'backup_current_a':None,
        'primary_detection_s':None,'backup_activation_s':None,'recovery_s':None,'rerouting_s':None,
        'telemetry_success_pct':100*len(samples)/expected_samples if expected_samples else None,
        'ml_inference_ms':None,'xgboost_f1':None,'random_forest_f1':None,'ensemble_f1':None}
    return {'provenance':'MEASURED_DATA','hardware_verification':'OPERATOR_REVIEW_REQUIRED',
        'device_id':samples[0]['device_id'],'boot_id':samples[0]['boot_id'],'unique_samples':len(samples),
        'notes':['Mode is a source declaration, not independent proof of physical origin.',
            'Target temperature is configured, not measured.',
            'Primary current is the mean over the supplied run, including OFF intervals.',
            'Steady state requires 12 final valid samples spanning at most 0.5 C and below target.',
            'Detection/recovery timing needs a separately recorded fault onset and physical output evidence.',
            'Backup current requires an external meter; there is no backup-current sensor in the BOM.'],
        'metrics':[{'metric':k,'value':v,'status':'CONFIGURED' if k=='target_temperature_c' else
            'CALCULATED_FROM_HARDWARE_TELEMETRY' if v is not None else 'PENDING_HARDWARE'} for k,v in values.items()]}

def main():
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('--output',type=Path,default=Path('runtime/hardware-report'))
    p.add_argument('--target',type=float,default=8);p.add_argument('--expected-samples',type=int)
    a=p.parse_args();report=analyze(json.loads(a.input.read_text()),a.target,a.expected_samples)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.with_suffix('.json').write_text(json.dumps(report,indent=2))
    with a.output.with_suffix('.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['metric','value','status']);w.writeheader();w.writerows(report['metrics'])
    print(a.output.with_suffix('.json'))

if __name__=='__main__':main()
