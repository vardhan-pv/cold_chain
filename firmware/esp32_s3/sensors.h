#pragma once
#include <Arduino.h>
#include "control_core.h"
struct SensorData {
  float chamber=NAN,heatsink=NAN,shtTemp=NAN,humidity=NAN,current=NAN;
  float doorSeconds=0,speed=NAN,latitude=NAN,longitude=NAN,gpsAge=NAN,rate=0;
  uint32_t satellites=0;
  uint32_t currentAdcMv=0;
  bool chamberOK=false,heatsinkOK=false,shtOK=false,currentOK=false,doorOK=false,doorOpen=false,gpsFix=false;
};
void sensorsBegin();
void sensorsTick(uint32_t now);
SensorData sensorSnapshot(uint32_t now);
