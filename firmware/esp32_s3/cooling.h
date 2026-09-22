#pragma once
#include "control_core.h"
void coolingBegin();
bool coolingConfigured();
bool primaryCoolingConfigured();
bool backupCoolingConfigured();
void primaryCoolingOn();
void primaryCoolingOff();
void setPrimaryCooling(bool on);
void coolingApply(coldchain::Output command,uint32_t now);
bool primaryObserved();
bool backupObserved();
