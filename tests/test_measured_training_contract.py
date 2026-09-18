"""Software fixtures only: these are NOT measured hardware evidence."""
import json
from datetime import datetime, timezone, timedelta
import pandas as pd
import pytest
from simulator.engine import Simulator
from ml.train_measured import prepare
from ml.train import fit_dataset
from ml.predictor import Predictor
from ml.feature_engineering import FEATURES

def records():
    result=[]
    for i,split in enumerate(('train','validation','test')):
        sim=Simulator(start=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=i))
        for j in range(8):
            t,_,_=sim.step()
            payload=t.model_dump(mode='json')
            # Exercise input validation, not physical acquisition. This fixture
            # never becomes a delivered model or hardware-validation result.
            payload['mode']='HARDWARE';payload['gps']['source']='GPS'
            payload['chamber_temp_c']=6 if j%2==0 else 12
            result.append({'split':split,'label':j%2,
                'evidence':'SOFTWARE FIXTURE ONLY - no physical measurement','telemetry':payload})
    return result

def save(tmp_path, data):
    p=tmp_path/'test-fixture.jsonl'
    p.write_text('\n'.join(json.dumps(x) for x in data))
    return p

def test_prepare_and_real_estimators_from_labelled_input(tmp_path):
    frame,evidence=prepare(save(tmp_path,records()))
    assert len(frame)==24 and set(frame.provenance)=={'MEASURED_DATA'}
    assert set(frame[FEATURES].columns)==set(FEATURES)
    report=fit_dataset(frame,tmp_path/'temporary-fixture-model',provenance='MEASURED_DATA',evidence=evidence)
    assert report['hardware_validated'] is False
    assert report['test']['ensemble']['samples']==8
    predictor=Predictor(tmp_path/'temporary-fixture-model')
    assert predictor.ready
    assert predictor.predict(frame.iloc[0][FEATURES].to_dict())['status']=='INFERENCE_COMPLETE'

@pytest.mark.parametrize('problem',['simulation','duplicate','split_leak','chronology','bad_label','missing_evidence'])
def test_invalid_measured_inputs_rejected(tmp_path,problem):
    rows=records()
    if problem=='simulation':
        rows[0]['telemetry']['mode']='SIMULATION';rows[0]['telemetry']['gps']['source']='SIMULATED'
    elif problem=='duplicate':rows.append(rows[0])
    elif problem=='split_leak':rows[0]['split']='test'
    elif problem=='chronology':
        for row in rows:
            if row['split']=='train':row['telemetry']['timestamp']=row['telemetry']['timestamp'].replace('2026-01-01','2026-01-05')
    elif problem=='bad_label':rows[0]['label']=.5
    else:rows[0]['evidence']=''
    with pytest.raises(ValueError):prepare(save(tmp_path,rows))
