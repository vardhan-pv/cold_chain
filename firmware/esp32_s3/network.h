#pragma once
#include "sensors.h"
#include "control_core.h"
void networkBegin();
void networkEnqueue(const SensorData& data,const coldchain::Output& output,uint32_t now,const char* injection);
bool networkHealthy();
float networkAdvisoryRisk();
