import pytest
from backend.control import Controller
from simulator.engine import Simulator
from ml.feature_engineering import features_for

@pytest.mark.parametrize('scenario,expected',[
    ('normal','NORMAL'),('primary_failure','BACKUP_ACTIVE'),('temperature_rise','PRIMARY_FAULT'),
    ('overcurrent','CRITICAL_FAILURE'),('overheat','CRITICAL_FAILURE'),
    ('door_open','WARNING'),('sensor_failure','CRITICAL_FAILURE'),
    ('wifi_failure','NORMAL'),('backend_failure','NORMAL'),
    ('backup_failure','REROUTING'),('gps_unavailable','NORMAL'),('recovery','RECOVERY')])
def test_scenario(scenario,expected):
    sim=Simulator(scenario=scenario);states=set()
    for _ in range(100):
        t,d,_=sim.step();states.add(d['state'])
        assert not(d['primary_cooling'] and d['backup_cooling'])
        if d['state'] in ('CRITICAL_FAILURE','REROUTING','PRIMARY_FAULT'):
            assert not d['primary_cooling'] and not d['backup_cooling']
    assert expected in states,(scenario,states)

def test_door_is_not_equipment_failure():
    sim=Simulator(scenario='door_open')
    for _ in range(18):
        _,d,_=sim.step()
        assert d['state'] not in ('PRIMARY_FAULT','BACKUP_ACTIVE')

def test_no_backup_when_primary_current_remains_on():
    sim=Simulator();c=Controller()
    t,_,_=sim.step()
    t=t.model_copy(update={'primary_cooling':False,'primary_current_a':4.8})
    d=c.update(t)
    assert d['state']=='CRITICAL_FAILURE' and not d['backup_cooling']

def test_fault_is_latched_on_good_sensor_recovery():
    sim=Simulator(scenario='sensor_failure')
    sim.step();sim.scenario='normal'
    for _ in range(4):
        _,d,_=sim.step()
        assert d['state']=='REROUTING'
        assert not d['primary_cooling'] and not d['backup_cooling']

def test_link_loss_local_control_and_bounded_queue():
    sim=Simulator(scenario='wifi_failure')
    for _ in range(140):
        t,d,_=sim.step();sim.enqueue(t)
    assert sim.local.last_time is not None and len(sim.queue)==120 and sim.dropped==20
    assert all(t.buffered for t in sim.queue)
    sim.scenario='normal';assert sim.network_available()

def test_break_before_make():
    sim=Simulator(scenario='primary_failure');off_samples=0;seen_fault=False
    for _ in range(30):
        t,d,_=sim.step()
        if d['state']=='PRIMARY_FAULT':seen_fault=True
        if seen_fault and not t.primary_cooling:off_samples+=1
        if d['backup_cooling']:
            assert off_samples>=2
            return
    pytest.fail('Backup did not activate')

def test_initial_ambient_cooldown_is_allowed_but_not_indefinitely():
    sim=Simulator();c=Controller()
    t,_,_=sim.step();t=t.model_copy(update={'chamber_temp_c':28.0})
    d=c.update(t)
    assert d['primary_cooling'] and d['state']=='WARNING'
    from datetime import timedelta
    t=t.model_copy(update={'timestamp':t.timestamp+timedelta(seconds=601)})
    d=c.update(t)
    assert d['state']=='CRITICAL_FAILURE' and not d['primary_cooling']

def test_current_filter_settles_after_intentional_switch_off():
    from datetime import timedelta
    sim=Simulator();c=Controller();t,_,_=sim.step()
    t=t.model_copy(update={'primary_cooling':True,'primary_current_a':5.0})
    c.update(t)
    t=t.model_copy(update={'timestamp':t.timestamp+timedelta(milliseconds=50),
        'primary_cooling':False,'primary_current_a':2.0})
    assert c.update(t)['state']!='CRITICAL_FAILURE'
    t=t.model_copy(update={'timestamp':t.timestamp+timedelta(milliseconds=600)})
    assert c.update(t)['state']=='CRITICAL_FAILURE'
