#pragma once
#ifndef COLDCHAIN_CONTROL_CORE_H
#define COLDCHAIN_CONTROL_CORE_H
#include <stdint.h>
#include <math.h>

namespace coldchain {
enum class State { NORMAL, WARNING, PRIMARY_FAULT, BACKUP_ACTIVE, RECOVERY, CRITICAL_FAILURE, REROUTING };
inline const char* name(State s) {
  switch(s) {
    case State::NORMAL:return "NORMAL"; case State::WARNING:return "WARNING";
    case State::PRIMARY_FAULT:return "PRIMARY_FAULT"; case State::BACKUP_ACTIVE:return "BACKUP_ACTIVE";
    case State::RECOVERY:return "RECOVERY"; case State::CRITICAL_FAILURE:return "CRITICAL_FAILURE";
    default:return "REROUTING";
  }
}
struct Reading {
  float chamber=NAN, heatsink=NAN, current=NAN, rate=0, doorSeconds=0, advisoryRisk=NAN;
  bool criticalValid=false, secondaryValid=false, doorValid=false, doorOpen=false;
  bool primaryObserved=false, backupObserved=false;
  bool injectPrimary=false, injectBackup=false;
  bool currentCalibrated=true;
};
struct Output { bool primary=false, backup=false, alarm=false; State state=State::NORMAL; };
class Controller {
 public:
  Output output;
  const char* reason="Safe startup; outputs OFF";
  void latch() { output={false,false,true,State::CRITICAL_FAILURE};reason="Persistent fault latch"; }
  void reset() { *this=Controller(); }
  Output update(const Reading& r,uint32_t ms) {
    if(!started){started=true;startAt=ms;}
    if(r.criticalValid&&r.chamber<=8)cooledOnce=true;
    if(previousPrimary&&!r.primaryObserved){offSettling=true;offTransition=ms;}
    previousPrimary=r.primaryObserved;
    const bool unexpectedCurrent=r.currentCalibrated&&!r.primaryObserved&&r.current>.5&&(!offSettling||elapsed(ms,offTransition)>=500);
    const bool currentFault=r.currentCalibrated&&(!isfinite(r.current)||r.current>=7||unexpectedCurrent);
    const bool chamberCritical=r.currentCalibrated&&r.chamber>=18&&(cooledOnce||elapsed(ms,startAt)>=600000);
    const bool activeFault=(!r.criticalValid || !isfinite(r.chamber) || !isfinite(r.heatsink) || currentFault ||
                            r.heatsink>=65 || chamberCritical || (r.primaryObserved&&r.backupObserved) ||
                            r.injectPrimary || r.injectBackup);
    const bool latched=output.state==State::CRITICAL_FAILURE || output.state==State::REROUTING;
    if (activeFault && !latched) {
      change(State::CRITICAL_FAILURE,ms,"Critical sensor or electrical/thermal safety fault");
    } else if(output.state==State::CRITICAL_FAILURE) {
      change(State::REROUTING,ms,"Cooling latched OFF; logistics assistance required");
    } else if(output.state==State::REROUTING) {
      if(!activeFault) {
        const bool warmChamber=r.currentCalibrated&&r.chamber>10;
        const bool warning=warmChamber||(r.doorValid&&r.doorOpen&&r.doorSeconds>=30)||
                           !r.secondaryValid||!r.doorValid||
                           (isfinite(r.advisoryRisk)&&r.advisoryRisk>=.65);
        if(warning) {
          change(State::WARNING,ms,"Active fault cleared; warning conditions present");
        } else {
          change(State::NORMAL,ms,"Active fault cleared; thermal and sensor conditions recovered");
        }
      }
    } else {
      if(r.primaryObserved) { if(!onTracking) {onTracking=true;onAt=ms;} } else onTracking=false;
      bool bad=(r.currentCalibrated&&r.primaryObserved&&onTracking&&elapsed(ms,onAt)>=10000&&r.current<.3) ||
        (r.primaryObserved&&r.doorValid&&!r.doorOpen&&r.chamber>10&&r.rate>.15) || r.injectPrimary;
      if(bad) { if(!badTracking) {badTracking=true;badAt=ms;} } else badTracking=false;
      switch(output.state) {
        case State::NORMAL: case State::WARNING:
          if(bad&&elapsed(ms,badAt)>=10000) {
            change(State::PRIMARY_FAULT,ms,"Sustained primary fault confirmed");offTracking=false;
          } else if(bad||(r.currentCalibrated&&r.chamber>10)||r.doorSeconds>=30||!r.secondaryValid||!r.doorValid||
                    (isfinite(r.advisoryRisk)&&r.advisoryRisk>=.65)) {
            if(output.state!=State::WARNING)change(State::WARNING,ms,"Observe sensor evidence");
          } else if(output.state!=State::NORMAL)change(State::NORMAL,ms,"Warning cleared");
          break;
        case State::PRIMARY_FAULT:
          if(!r.primaryObserved&&(!r.currentCalibrated||r.current<=.5)) {
            if(!offTracking) {offTracking=true;offAt=ms;}
            if(elapsed(ms,offAt)>=2000) {
              change(State::BACKUP_ACTIVE,ms,"Primary OFF evidence and dead time satisfied");
              backupAt=ms;goodTracking=false;
            }
          } else offTracking=false;
          if(output.state==State::PRIMARY_FAULT&&elapsed(ms,entered)>20000)
            change(State::CRITICAL_FAILURE,ms,"Primary OFF confirmation timed out");
          break;
        case State::BACKUP_ACTIVE: case State::RECOVERY:
          if(r.injectBackup)change(State::CRITICAL_FAILURE,ms,"FAULT INJECTION: backup failure");
          else if(r.chamber<=8&&r.rate<=.05) {
            if(!goodTracking) {goodTracking=true;goodAt=ms;}
            if(elapsed(ms,goodAt)>=30000&&output.state!=State::RECOVERY)
              change(State::RECOVERY,ms,"Backup temperature stabilized; maintenance required");
          } else {
            goodTracking=false;
            if(output.state==State::RECOVERY) {
              change(State::BACKUP_ACTIVE,ms,"Recovery lost");backupAt=ms;
            } else if(elapsed(ms,backupAt)>=120000)
              change(State::CRITICAL_FAILURE,ms,"Backup recovery timed out");
          }
          break;
        default:break;
      }
    }
    const bool backupMode=output.state==State::BACKUP_ACTIVE||output.state==State::RECOVERY;
    const bool off=output.state==State::PRIMARY_FAULT||output.state==State::CRITICAL_FAILURE||output.state==State::REROUTING;
    bool wants=backupMode?output.backup:output.primary;
    if(r.chamber>=8)wants=true;else if(r.chamber<=5)wants=false;
    output.primary=!off&&!backupMode&&wants;
    output.backup=!off&&backupMode&&wants;
    output.alarm=output.state==State::CRITICAL_FAILURE||output.state==State::REROUTING;
    return output;
  }
 private:
  uint32_t entered=0,onAt=0,badAt=0,offAt=0,backupAt=0,goodAt=0;
  bool onTracking=false,badTracking=false,offTracking=false,goodTracking=false;
  bool started=false,cooledOnce=false;uint32_t startAt=0;
  bool previousPrimary=false,offSettling=false;uint32_t offTransition=0;
  static uint32_t elapsed(uint32_t now,uint32_t then){return now-then;}
  void change(State state,uint32_t ms,const char* why){output.state=state;entered=ms;reason=why;}
};
}
#endif
