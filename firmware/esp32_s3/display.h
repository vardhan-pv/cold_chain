#pragma once
#include "sensors.h"
#include "control_core.h"
void displayBegin();
void displayTick(const SensorData& data,const coldchain::Output& output,bool backendOK,uint32_t now);
