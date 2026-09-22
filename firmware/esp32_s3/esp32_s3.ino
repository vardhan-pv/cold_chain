#include <WiFi.h>
#include "config.h"
#include "sensors.h"
#include "cooling.h"
#include "telemetry_net.h"
#include "display.h"
#include <Preferences.h>
#include <esp_task_wdt.h>
#include <esp_arduino_version.h>
#include <esp_system.h>

static coldchain::Controller controller;
static Preferences prefs;
static uint32_t lastSafety=0,lastTelemetry=0,lastDisplay=0;
static bool savedLatch=false,injectPrimary=false,injectBackup=false;
static bool testModeActive=false,autonomousEnabled=false;
static uint32_t testEndMs=0;
static String command;

static const char* resetReasonName(esp_reset_reason_t r) {
  switch(r) {
    case ESP_RST_POWERON:   return "POWERON";
    case ESP_RST_SW:        return "SOFTWARE";
    case ESP_RST_PANIC:     return "PANIC";
    case ESP_RST_INT_WDT:   return "INT_WDT";
    case ESP_RST_TASK_WDT:  return "TASK_WDT";
    case ESP_RST_WDT:       return "WDT";
    case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
    case ESP_RST_BROWNOUT:  return "BROWNOUT";
    case ESP_RST_SDIO:      return "SDIO";
    default:                return "UNKNOWN";
  }
}

void setup(){
  Serial.begin(115200);
  delay(200); // Allow USB-CDC serial to stabilize on ESP32-S3

  Serial.println("\n[BOOT] Cold Chain Physical Hardware");

  esp_reset_reason_t reason = esp_reset_reason();
  Serial.printf("[BOOT] Reset reason: %d (%s)\n", (int)reason, resetReasonName(reason));
  Serial.printf("[BOOT] Free heap: %lu bytes\n", (unsigned long)ESP.getFreeHeap());

  prefs.begin("coldchain",false);
  savedLatch=prefs.getBool("fault",false);
  if(savedLatch)controller.latch();

  if(OPTIONAL_FAULT_BUTTONS){
    if(PIN_INJECT_PRIMARY>=0)pinMode(PIN_INJECT_PRIMARY,INPUT_PULLUP);
    if(PIN_INJECT_BACKUP>=0)pinMode(PIN_INJECT_BACKUP,INPUT_PULLUP);
  }

  sensorsBegin();
  gpsBegin();
  coolingBegin(); // Always set inactive levels before starting network
  displayBegin();
  networkBegin();

  Serial.printf("{\"event\":\"boot\",\"hardware_verified\":false,\"commissioned\":%s,\"primary_pin\":%d,\"backup_pin\":%d}\n",
                coolingConfigured()?"true":"false", PIN_PRIMARY, PIN_BACKUP);
  Serial.println("[BOOT] Ready (Primary cooling defaults SAFE OFF; test mode available)");
}

void loop(){
  const uint32_t now=millis();
  sensorsTick(now);
  SensorData s=sensorSnapshot(now);

  while(Serial.available()){
    char c=Serial.read();
    if(c=='\n'){
      command.trim();
      if(command=="ADC"){
        Serial.printf("{\"event\":\"calibration_adc_mv\",\"value\":%lu}\n",(unsigned long)s.currentAdcMv);
      } else if(command=="INJECT PRIMARY"){
        injectPrimary=true;Serial.println("{\"event\":\"FAULT_INJECTION\",\"target\":\"PRIMARY\"}");
      } else if(command=="INJECT BACKUP"){
        injectBackup=true;Serial.println("{\"event\":\"FAULT_INJECTION\",\"target\":\"BACKUP\"}");
      } else if(command=="CLEAR INJECTION"){
        injectPrimary=injectBackup=false;Serial.println("{\"event\":\"FAULT_INJECTION\",\"target\":\"CLEARED\"}");
      } else if(command=="STATUS"){
        Serial.printf("{\"event\":\"status\",\"commissioned\":%s,\"primary\":%s,\"backup\":%s,\"auto\":%s,\"test\":%s,\"chamber\":%.2f,\"heatsink\":%.2f,\"state\":\"%s\"}\n",
                      coolingConfigured()?"true":"false", primaryObserved()?"true":"false", backupObserved()?"true":"false",
                      autonomousEnabled?"true":"false", testModeActive?"true":"false", s.chamber, s.heatsink, coldchain::name(controller.output.state));
      } else if(command.startsWith("TEST PRIMARY")){
        // Extract optional duration in seconds (default 5, max 15)
        int durationSec = 5;
        if(command.length() > 12){
          int parsed = command.substring(12).toInt();
          if(parsed > 0 && parsed <= 15) durationSec = parsed;
        }
        if(!coolingConfigured()){
          Serial.println("{\"event\":\"test_rejected\",\"reason\":\"Cooling not commissioned\"}");
        } else if(!s.chamberOK || !s.heatsinkOK || !isfinite(s.heatsink) || s.heatsink >= 50.0f){
          Serial.printf("{\"event\":\"test_rejected\",\"reason\":\"Thermal safety conditions not met\",\"heatsink\":%.2f}\n", s.heatsink);
        } else if(controller.output.state == coldchain::State::CRITICAL_FAILURE || controller.output.state == coldchain::State::PRIMARY_FAULT){
          Serial.println("{\"event\":\"test_rejected\",\"reason\":\"System in latched fault state\"}");
        } else {
          testModeActive = true;
          testEndMs = now + (uint32_t)durationSec * 1000;
          primaryCoolingOn();
          Serial.printf("{\"event\":\"primary_test_start\",\"duration_s\":%d,\"chamber\":%.2f,\"heatsink\":%.2f}\n",
                        durationSec, s.chamber, s.heatsink);
        }
      } else if(command=="COOLING OFF" || command=="STOP"){
        testModeActive = false;
        autonomousEnabled = false;
        primaryCoolingOff();
        Serial.println("{\"event\":\"cooling_stopped\",\"source\":\"manual_command\"}");
      } else if(command=="ENABLE AUTO"){
        if(!coolingConfigured()){
          Serial.println("{\"event\":\"auto_rejected\",\"reason\":\"Cooling not commissioned\"}");
        } else if(!s.chamberOK || !s.heatsinkOK || s.heatsink >= 50.0f){
          Serial.println("{\"event\":\"auto_rejected\",\"reason\":\"Thermal safety conditions not met\"}");
        } else {
          autonomousEnabled = true;
          testModeActive = false;
          Serial.println("{\"event\":\"auto_cooling_enabled\"}");
        }
      } else if(command=="DISABLE AUTO"){
        autonomousEnabled = false;
        primaryCoolingOff();
        Serial.println("{\"event\":\"auto_cooling_disabled\"}");
      } else if(command=="RESET CONFIRMED"&&coolingConfigured()&&s.chamberOK&&s.heatsinkOK&&
                (!CURRENT_CALIBRATED || (s.currentOK && s.current < .3))&&
                s.heatsink<50&&s.chamber<18&&!primaryObserved()&&!backupObserved()){
        controller.reset();
        prefs.putBool("fault",false);
        savedLatch=false;
        injectPrimary=injectBackup=false;
        testModeActive=false;
        autonomousEnabled=false;
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

    // Hard hardware thermal protection check
    const bool thermalSafe = s.chamberOK && s.heatsinkOK && isfinite(s.chamber) && isfinite(s.heatsink) && (s.heatsink < 50.0f);
    if(!thermalSafe){
      if(primaryObserved()){
        primaryCoolingOff();
        Serial.printf("{\"event\":\"thermal_cutoff\",\"chamber_ok\":%s,\"heatsink_ok\":%s,\"heatsink\":%.2f}\n",
                      s.chamberOK?"true":"false", s.heatsinkOK?"true":"false", s.heatsink);
      }
      if(testModeActive) testModeActive = false;
    }

    // Auto-timeout for controlled test mode
    if(testModeActive && now >= testEndMs){
      testModeActive = false;
      primaryCoolingOff();
      Serial.println("{\"event\":\"primary_test_complete\"}");
    }

    // Edge safety state machine
    if(coolingConfigured()&&(now>10000||(s.chamberOK&&s.heatsinkOK))){
      coldchain::Reading r;
      r.chamber=s.chamber;
      r.heatsink=s.heatsink;
      r.current=s.current;
      r.rate=s.rate;
      r.doorSeconds=s.doorSeconds;
      r.criticalValid=s.chamberOK&&s.heatsinkOK&&(!CURRENT_CALIBRATED||s.currentOK);
      r.secondaryValid=s.shtOK;
      r.doorValid=s.doorOK;
      r.doorOpen=s.doorOpen;
      r.primaryObserved=primaryObserved();
      r.backupObserved=backupObserved();
      r.injectPrimary=injectPrimary;
      r.injectBackup=injectBackup;
      r.currentCalibrated=CURRENT_CALIBRATED;
      r.advisoryRisk=networkAdvisoryRisk(); // Fresh cloud inference may warn; never overrides local protection.

      auto old=controller.output.state;
      controller.update(r,now);
      if(old!=controller.output.state){
        Serial.printf("{\"event\":\"state_transition\",\"state\":\"%s\",\"reason\":\"%s\"}\n",
                      coldchain::name(controller.output.state),controller.reason);
      }
      if((controller.output.alarm||controller.output.state==coldchain::State::PRIMARY_FAULT)&&!savedLatch){
        prefs.putBool("fault",true);
        savedLatch=true;
        testModeActive=false;
        autonomousEnabled=false;
        primaryCoolingOff();
      }
    }

    // Actuate cooling output based on operating mode and safety state
    if(!thermalSafe || controller.output.state==coldchain::State::CRITICAL_FAILURE ||
       controller.output.state==coldchain::State::PRIMARY_FAULT ||
       controller.output.state==coldchain::State::REROUTING){
      primaryCoolingOff();
    } else if(testModeActive){
      // Test mode is active: primary cooling stays ON until testEndMs or safety cutoff
    } else if(autonomousEnabled){
      coolingApply(controller.output,now);
    } else {
      // Safe default: primary cooling remains OFF unless explicitly commanded in test or auto
      primaryCoolingOff();
    }
  }

  if(now-lastTelemetry>=TELEMETRY_MS){
    lastTelemetry=now;
    networkEnqueue(s,controller.output,now,injectBackup?"BACKUP_FAILURE":injectPrimary?"PRIMARY_FAILURE":"NONE");
  }

  if(now-lastDisplay>=500){
    lastDisplay=now;
    displayTick(s,controller.output,networkHealthy(),now);
  }

  delay(1); // Yield to RTOS. No network operation runs in this safety loop.
}
