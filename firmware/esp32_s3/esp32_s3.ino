// Hardware adapter is intentionally uncommissioned until the purchased board and interfaces are checked.
#include "config.h"
#include "sensors.h"
#include "cooling.h"
#include "network.h"
#include "display.h"
#include <Preferences.h>
#include <esp_task_wdt.h>
#include <esp_arduino_version.h>
static coldchain::Controller controller;
static Preferences prefs;
static uint32_t lastSafety=0,lastTelemetry=0,lastDisplay=0;
static bool savedLatch=false,injectPrimary=false,injectBackup=false;
static String command;

void setup(){
  coolingBegin(); // Always set inactive levels before starting sensors/network.
  Serial.begin(115200);
  prefs.begin("coldchain",false);savedLatch=prefs.getBool("fault",false);if(savedLatch)controller.latch();
  sensorsBegin();displayBegin();networkBegin();
  if(OPTIONAL_FAULT_BUTTONS){if(PIN_INJECT_PRIMARY>=0)pinMode(PIN_INJECT_PRIMARY,INPUT_PULLUP);if(PIN_INJECT_BACKUP>=0)pinMode(PIN_INJECT_BACKUP,INPUT_PULLUP);}
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t config={.timeout_ms=5000,.idle_core_mask=0,.trigger_panic=true};
  esp_task_wdt_reconfigure(&config);
#else
  esp_task_wdt_init(5,true);
#endif
  esp_task_wdt_add(nullptr);
  Serial.printf("{\"event\":\"boot\",\"hardware_verified\":false,\"commissioned\":%s}\n",coolingConfigured()?"true":"false");
}
void loop(){
  const uint32_t now=millis();sensorsTick(now);SensorData s=sensorSnapshot(now);
  while(Serial.available()){
    char c=Serial.read();
    if(c=='\n'){
      command.trim();
      if(command=="ADC")Serial.printf("{\"event\":\"calibration_adc_mv\",\"value\":%lu}\n",(unsigned long)s.currentAdcMv);
      if(command=="INJECT PRIMARY"){injectPrimary=true;Serial.println("{\"event\":\"FAULT_INJECTION\",\"target\":\"PRIMARY\"}");}
      if(command=="INJECT BACKUP"){injectBackup=true;Serial.println("{\"event\":\"FAULT_INJECTION\",\"target\":\"BACKUP\"}");}
      if(command=="CLEAR INJECTION"){injectPrimary=injectBackup=false;}
      if(command=="RESET CONFIRMED"&&coolingConfigured()&&s.chamberOK&&s.heatsinkOK&&s.currentOK&&
          s.heatsink<50&&s.current<.3&&s.chamber<18&&!primaryObserved()&&!backupObserved()){
        controller.reset();prefs.putBool("fault",false);savedLatch=false;injectPrimary=injectBackup=false;
        Serial.println("{\"event\":\"manual_fault_reset\"}");
      }
      command="";
    }else if(command.length()<64)command+=c;
  }
  if(OPTIONAL_FAULT_BUTTONS){
    if(PIN_INJECT_PRIMARY>=0&&digitalRead(PIN_INJECT_PRIMARY)==LOW)injectPrimary=true;
    if(PIN_INJECT_BACKUP>=0&&digitalRead(PIN_INJECT_BACKUP)==LOW)injectBackup=true;
  }
  if(now-lastSafety>=SAFETY_MS){
    lastSafety=now;
    if(coolingConfigured()&&(now>10000||(s.chamberOK&&s.heatsinkOK&&s.currentOK))){
      coldchain::Reading r;
      r.chamber=s.chamber;r.heatsink=s.heatsink;r.current=s.current;r.rate=s.rate;r.doorSeconds=s.doorSeconds;
      r.criticalValid=s.chamberOK&&s.heatsinkOK&&s.currentOK;r.secondaryValid=s.shtOK;r.doorValid=s.doorOK;r.doorOpen=s.doorOpen;
      r.primaryObserved=primaryObserved();r.backupObserved=backupObserved();r.injectPrimary=injectPrimary;r.injectBackup=injectBackup;
      r.advisoryRisk=networkAdvisoryRisk(); // Fresh cloud inference may warn; never overrides local protection.
      auto old=controller.output.state;controller.update(r,now);
      if(old!=controller.output.state)Serial.printf("{\"event\":\"state_transition\",\"state\":\"%s\",\"reason\":\"%s\"}\n",coldchain::name(controller.output.state),controller.reason);
      if((controller.output.alarm||controller.output.state==coldchain::State::PRIMARY_FAULT)&&!savedLatch){prefs.putBool("fault",true);savedLatch=true;}
    }
    coolingApply(controller.output,now);
  }
  if(now-lastTelemetry>=TELEMETRY_MS){lastTelemetry=now;networkEnqueue(s,controller.output,now,injectBackup?"BACKUP_FAILURE":injectPrimary?"PRIMARY_FAILURE":"NONE");}
  if(now-lastDisplay>=500){lastDisplay=now;displayTick(s,controller.output,networkHealthy(),now);}
  esp_task_wdt_reset();delay(1); // Yield to RTOS. No network operation runs in this safety loop.
}
