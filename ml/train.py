"""Reproducible simulation experiment with disjoint episode train/validation/test sets."""
import argparse, hashlib, json, platform
from datetime import datetime, timezone, timedelta
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import sklearn, xgboost
from simulator.engine import Simulator
from ml.feature_engineering import FEATURES, FEATURE_VERSION, features_for
from ml.train_xgboost import train as train_xgb
from ml.train_random_forest import train as train_rf
from ml.evaluate import metrics

MODEL_DIR = Path(__file__).resolve().parent / 'trained_models'

def dataset():
    rows = []
    scenarios = ['normal','primary_failure','temperature_rise','overcurrent','overheat',
                 'door_open','backup_failure','gps_unavailable','recovery','normal']
    epoch = datetime(2026,1,1,tzinfo=timezone.utc)
    for s, scenario in enumerate(scenarios):
        for episode in range(12):
            group = f'{s:02d}-{episode:02d}'
            split = 'train' if episode < 8 else 'validation' if episode < 10 else 'test'
            sim = Simulator(seed=42+s*100+episode, start=epoch+timedelta(days=s*12+episode), scenario=scenario)
            sim.chamber = sim.random.uniform(6, 10)
            onset = sim.random.randint(60,140)
            for _ in range(90):
                _, _, label = sim.step(activate_after=onset)
                f = features_for(sim.history)
                if f:
                    rows.append({**f,'label':label,'episode_id':group,'split':split,
                        'provenance':'SIMULATED_DATA','scenario':scenario})
    return pd.DataFrame(rows)

def fit_dataset(df, out, provenance='SIMULATED_DATA', evidence=None):
    if provenance not in ('SIMULATED_DATA','MEASURED_DATA'):
        raise ValueError('Unsupported dataset provenance')
    required=set(FEATURES)|{'label','episode_id','split','provenance'}
    if not required<=set(df.columns) or set(df.provenance)!={provenance}:
        raise ValueError('Dataset columns or provenance do not match the training contract')
    if set(df.split)!={'train','validation','test'} or not np.isfinite(df[FEATURES].to_numpy()).all():
        raise ValueError('Three valid splits and finite features are required')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    train, val, test = [df[df.split == s] for s in ('train','validation','test')]
    if set(train.episode_id)&(set(val.episode_id)|set(test.episode_id)) or set(val.episode_id)&set(test.episode_id):
        raise ValueError('An episode cannot appear in multiple splits')
    if any(set(part.label)!={0,1} for part in (train,val,test)):
        raise ValueError('Each split needs independently labelled normal and anomaly samples')
    a, b = train_xgb(train[FEATURES],train.label), train_rf(train[FEATURES],train.label)
    av,bv = a.predict_proba(val[FEATURES])[:,1], b.predict_proba(val[FEATURES])[:,1]
    fa,fb = metrics(val.label,av)['f1'], metrics(val.label,bv)['f1']
    weight = fa/(fa+fb) if fa+fb else .5
    scores = weight*av+(1-weight)*bv
    threshold = max(np.arange(.2,.81,.025),key=lambda t:metrics(val.label,scores,t)['f1'])
    at,bt = a.predict_proba(test[FEATURES])[:,1], b.predict_proba(test[FEATURES])[:,1]
    a.save_model(out/'xgboost_model.json')
    joblib.dump(b,out/'random_forest_model.joblib',compress=3)
    dataset_name='simulation_dataset.csv' if provenance=='SIMULATED_DATA' else 'measured_features.csv'
    df.to_csv(out/dataset_name,index=False)
    fingerprint = hashlib.sha256((out/dataset_name).read_bytes()).hexdigest()
    report = {'model_version':('simulation-v1-' if provenance=='SIMULATED_DATA' else 'measured-v1-')+fingerprint[:10], 'feature_version':FEATURE_VERSION,
        'features':FEATURES,'training_provenance':provenance,'dataset_file':dataset_name,
        'scope':'Present-condition anomaly classification; not validated failure forecasting',
        'hardware_validated':False,'scaling':'none; both estimators are tree-based',
        'created_at':datetime.now(timezone.utc).isoformat(),'seed':42,
        'xgboost_weight':float(weight),'threshold':float(threshold),
        'split_method':'Entire episodes partitioned before training; no episode shared between sets',
        'splits':{k:{'rows':len(df[df.split==k]),'episodes':sorted(df[df.split==k].episode_id.unique().tolist()),
            'positive_samples':int(df[df.split==k].label.sum())} for k in ('train','validation','test')},
        'validation':{'xgboost':metrics(val.label,av),'random_forest':metrics(val.label,bv),
            'ensemble':metrics(val.label,scores,threshold)},
        'test':{'xgboost':metrics(test.label,at),'random_forest':metrics(test.label,bt),
            'ensemble':metrics(test.label,weight*at+(1-weight)*bt,threshold)},
        'versions':{'python':platform.python_version(),'sklearn':sklearn.__version__,
            'xgboost':xgboost.__version__,'numpy':np.__version__},
        'dataset_sha256':fingerprint,
        'artifact_sha256':{f:hashlib.sha256((out/f).read_bytes()).hexdigest() for f in
            ('xgboost_model.json','random_forest_model.joblib')},
        'label_evidence':evidence,
        'limitations':(['Illustrative uncalibrated plant only','No measured hardware data',
            'No claim of cargo safety or field accuracy','Simulator assumptions can inflate scores'] if provenance=='SIMULATED_DATA' else
            ['Operator supplied records and labels; physical provenance not independently verified',
             'Held-out log evaluation is not field certification','No failure lead-time or cargo-safety claim'])}
    (out/'manifest.json').write_text(json.dumps(report,indent=2))
    (out/'feature_schema.json').write_text(json.dumps({'version':FEATURE_VERSION,'features':FEATURES},indent=2))
    print(json.dumps({'rows':len(df),'version':report['model_version'],'test':report['test']},indent=2))
    return report

def main(out=MODEL_DIR):
    return fit_dataset(dataset(),out)

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=MODEL_DIR)
    main(p.parse_args().output)
