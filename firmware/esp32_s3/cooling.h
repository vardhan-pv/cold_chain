#pragma once
#include "control_core.h"
void coolingBegin();
bool coolingConfigured();
void coolingApply(coldchain::Output command,uint32_t now);
bool primaryObserved();
bool backupObserved();
