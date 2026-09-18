"""Replay identical sensor records through Python and host-compiled C++ rules."""
import json,subprocess,tempfile
from pathlib import Path
from simulator.engine import Simulator,SCENARIOS
from backend.control import Controller
from ml.feature_engineering import features_for

ROOT=Path(__file__).resolve().parents[2]

def main():
    with tempfile.TemporaryDirectory() as td:
        binary=Path(td)/'controller'
        subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',str(ROOT/'tests/firmware/native_controller_test.cpp'),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)
        lines=[];expected=[]
        for scenario,advisory in [(s,a) for s in SCENARIOS for a in (False,True)]:
            lines.append('RESET');sim=Simulator(scenario=scenario);controller=Controller()
            for step in range(100):
                t,_,_=sim.step();f=features_for(sim.history)
                rate=f['chamber_rate_c_min'] if f else 0
                risk=.9 if advisory and 10<=step<30 else .1
                d=controller.update(t,rate=rate,risk=risk)
                health=t.sensor_health
                values=[int(sim.elapsed*1000),t.chamber_temp_c or 0,t.heatsink_temp_c or 0,
                    t.primary_current_a or 0,rate,t.door_open_s,
                    int(health.chamber and health.heatsink and health.current),int(health.sht31),
                    int(health.door),int(t.door_open or False),int(t.primary_cooling),int(t.backup_cooling),risk]
                lines.append(' '.join(map(str,values)))
                expected.append((scenario+(' with ML advisory' if advisory else ''),step,f"{d['state']},{int(d['primary_cooling'])},{int(d['backup_cooling'])}"))
        result=subprocess.run([str(binary),'replay'],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True)
        actual=result.stdout.splitlines()
        assert len(actual)==len(expected)
        for got,(scenario,step,want) in zip(actual,expected):
            assert got==want,(scenario,step,got,want)
        report={'status':'PASS','scope':'HOST_COMPILED_CONTROLLER_ONLY','samples_compared':len(expected),
            'scenarios':SCENARIOS,'ml_advisory_variants':2,'target_build':'NOT_ASSERTED','hardware_verified':False}
        (ROOT/'docs/evidence/firmware-parity.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))

if __name__=='__main__':main()
