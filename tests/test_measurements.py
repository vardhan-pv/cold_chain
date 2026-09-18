import pytest
from scripts.analyze_hardware_run import analyze
from simulator.engine import Simulator

def test_measurement_report_refuses_simulation():
    t,_,_=Simulator().step()
    with pytest.raises(ValueError):analyze([t.model_dump(mode='json')])

def test_measurement_calculation_fixture_is_not_evidence():
    # Unit-test data only; no produced file is labelled an actual hardware result.
    sim=Simulator();rows=[]
    for _ in range(20):
        t,_,_=sim.step();row=t.model_dump(mode='json');row['mode']='HARDWARE';rows.append(row)
    report=analyze(rows,expected_samples=25)
    m={r['metric']:r for r in report['metrics']}
    assert m['telemetry_success_pct']['value']==80
    assert m['backup_current_a']['value'] is None
    assert m['primary_detection_s']['value'] is None
    assert report['hardware_verification']=='OPERATOR_REVIEW_REQUIRED'
