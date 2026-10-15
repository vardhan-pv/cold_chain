#pragma once
#ifndef COLDCHAIN_TELEMETRY_NET_H
#define COLDCHAIN_TELEMETRY_NET_H

#include "sensors.h"
#include "control_core.h"

enum class WifiState : uint8_t {
  CONNECTING,       // Connecting to saved Wi-Fi at boot
  CONNECTED_POPUP,  // Connected banner (2 seconds)
  CONNECTED_NORMAL, // Connected and operating normally
  SETUP_AP,         // ColdChain-Setup Access Point mode active
  DISCONNECTED      // Runtime disconnected, background reconnecting
};

void networkBegin();
void networkEnqueue(const SensorData& data, const coldchain::Output& output, uint32_t now, const char* injection);
bool networkHealthy();
float networkAdvisoryRisk();

// Wi-Fi Provisioning & Status
WifiState networkWifiState();
const char* networkCurrentSsid();
void wifiResetCredentials();
void wifiPrintStatus();

#endif
