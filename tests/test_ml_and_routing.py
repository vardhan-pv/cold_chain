import json
from pathlib import Path
import pytest
from backend.routing import reroute,DEMO_WAREHOUSES,distance_km
from simulator.engine import Simulator
from ml.feature_engineering import features_for,FEATURES
from ml.predictor import Predictor

def test_real_models_and_schema():
    predictor=Predictor();assert predictor.ready,predictor.error
    sim=Simulator()
    for _ in range(4):sim.step()
    f=features_for(sim.history)
    p=predictor.predict(f)
    assert p['status']=='INFERENCE_COMPLETE'
    assert all(0<=p[k]<=1 for k in ('xgboost_probability','random_forest_probability','ensemble_probability'))
    assert p['inference_ms']>0
    with pytest.raises(ValueError):predictor.predict(dict(reversed(list(f.items()))))

def test_missing_artifacts_have_no_fake_prediction(tmp_path):
    p=Predictor(tmp_path)
    assert not p.ready
    assert p.predict(None)['ensemble_probability'] is None

def test_feature_causality_and_device_separation():
    sim=Simulator()
    for _ in range(8):sim.step()
    baseline=features_for(sim.history)
    future,_,_=sim.step()
    future=future.model_copy(update={'timestamp':future.timestamp,'chamber_temp_c':100})
    assert features_for([future,*sim.history[:-1]])==baseline
    assert list(baseline)==FEATURES
    other=future.model_copy(update={'device_id':'OTHER'})
    assert features_for([other,*sim.history[:-1]])==baseline

def test_train_validation_test_episode_separation():
    m=Predictor().manifest
    groups=[set(v['episodes']) for v in m['splits'].values()]
    assert all(not groups[i]&groups[j] for i in range(3) for j in range(i+1,3))
    assert m['training_provenance']=='SIMULATED_DATA' and not m['hardware_validated']

def test_facility_filtering_and_no_fix():
    t,_,_=Simulator().step()
    r=reroute(t,DEMO_WAREHOUSES)
    assert r['selected']['warehouse_id']=='SIM-WH-001'
    assert {w['warehouse_id'] for w in r['candidates']}=={'SIM-WH-001','SIM-WH-002'}
    nofix,_,_=Simulator(scenario='gps_unavailable').step()
    assert reroute(nofix,DEMO_WAREHOUSES)['status']=='NO_GPS_FIX'
    assert reroute(t,[])['status']=='NO_COMPATIBLE_FACILITY'
    hw=t.model_copy(update={'mode':'HARDWARE','gps':t.gps.model_copy(update={'source':'GPS'})})
    assert reroute(hw,DEMO_WAREHOUSES)['selected'] is None
    assert distance_km(12,77,12,77)==0
