#pragma once
#ifndef COLDCHAIN_SENSORS_H
#define COLDCHAIN_SENSORS_H
#include <Arduino.h>
#include "control_core.h"
struct SensorData {
  float chamber=NAN,heatsink=NAN,shtTemp=NAN,humidity=NAN,current=NAN;
  float doorSeconds=0,speed=NAN,latitude=NAN,longitude=NAN,gpsAge=NAN,rate=0;
  uint32_t satellites=0;
  uint32_t currentAdcMv=0;
  bool chamberOK=false,heatsinkOK=false,shtOK=false,currentOK=false,doorOK=false,doorOpen=false,gpsFix=false;
  bool vibrationOK=false,vibrationDetected=false;
};
void sensorsBegin();
void gpsBegin();
void sensorsTick(uint32_t now);
SensorData sensorSnapshot(uint32_t now);
bool getDiscoveredHeatsinkRom(uint8_t outRom[8]);
#endif
