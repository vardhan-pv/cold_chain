#include "config.h"
#include "cooling.h"
#include <atomic>

static std::atomic<bool> primary{false}, backup{false};
static uint32_t offAt = 0;

bool primaryCoolingConfigured() {
  if (!(COMMISSIONED && PIN_PRIMARY >= 0 && PIN_ONEWIRE >= 0 && CHAMBER_ROM[0] != 0)) {
    return false;
  }
  const int pins[] = {PIN_PRIMARY, PIN_BACKUP, PIN_ONEWIRE, PIN_CURRENT, PIN_REED, PIN_SDA, PIN_SCL,
                      PIN_FAN, PIN_VIBRATION, PIN_BUZZER, PIN_GPS_RX, PIN_GPS_TX,
                      PIN_GREEN, PIN_YELLOW, PIN_RED, PIN_INJECT_PRIMARY};
  for (unsigned i = 0; i < sizeof(pins) / sizeof(pins[0]); i++) {
    for (unsigned j = i + 1; j < sizeof(pins) / sizeof(pins[0]); j++) {
      if (pins[i] >= 0 && pins[i] == pins[j]) return false;
    }
  }
  return true;
}

bool backupCoolingConfigured() {
  // Backup Peltier is NOT commissioned yet
  return false;
}

bool coolingConfigured() {
  return primaryCoolingConfigured();
}

static void pinOff(int pin) {
  if (pin >= 0) {
    digitalWrite(pin, OUTPUT_INACTIVE);
    pinMode(pin, OUTPUT);
  }
}

void primaryCoolingOff() {
  if (PIN_PRIMARY >= 0) digitalWrite(PIN_PRIMARY, OUTPUT_INACTIVE);
  if (PIN_FAN >= 0) digitalWrite(PIN_FAN, OUTPUT_INACTIVE);
  if (primary) {
    primary = false;
    offAt = millis();
    Serial.println("{\"event\":\"cooling_output\",\"channel\":\"PRIMARY\",\"state\":\"OFF\"}");
  }
}

void primaryCoolingOn() {
  if (!primaryCoolingConfigured() || backup) return;
  if (millis() - offAt < 2000) return; // Anti-chatter deadband
  if (PIN_FAN >= 0) digitalWrite(PIN_FAN, OUTPUT_ACTIVE);
  if (PIN_PRIMARY >= 0) digitalWrite(PIN_PRIMARY, OUTPUT_ACTIVE);
  if (!primary) {
    primary = true;
    Serial.println("{\"event\":\"cooling_output\",\"channel\":\"PRIMARY\",\"state\":\"ON\"}");
  }
}

void setPrimaryCooling(bool on) {
  if (on) primaryCoolingOn();
  else primaryCoolingOff();
}

void coolingBegin() {
  pinOff(PIN_PRIMARY);
  pinOff(PIN_BACKUP);
  if (PIN_FAN >= 0) {
    pinOff(PIN_FAN);
    Serial.printf("[BOOT] Fan GPIO%d OFF\n", PIN_FAN);
  }
  primary = backup = false;
  offAt = millis();
  Serial.printf("[BOOT] Primary Peltier GPIO%d configured (defaults OFF, commissioned=%s)\n",
                PIN_PRIMARY, primaryCoolingConfigured() ? "true" : "false");
}

void coolingApply(coldchain::Output command, uint32_t now) {
  // Backup is not commissioned
  command.backup = false;

  if (!primaryCoolingConfigured() || (command.primary && command.backup)) {
    command.primary = false;
    command.backup = false;
  }

  if (primary && !command.primary) {
    primaryCoolingOff();
  }

  if (backup && !command.backup) {
    if (PIN_BACKUP >= 0) digitalWrite(PIN_BACKUP, OUTPUT_INACTIVE);
    backup = false;
    offAt = now;
  }

  if (command.primary && !backup && now - offAt >= 2000) {
    primaryCoolingOn();
  }
}

// These booleans confirm output register intent, not MOSFET conduction.
bool primaryObserved() { return primary; }
bool backupObserved() { return backup; }
