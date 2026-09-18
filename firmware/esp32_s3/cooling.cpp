#include "config.h"
#include "cooling.h"
#include <atomic>

static std::atomic<bool> primary{false}, backup{false};
static uint32_t offAt = 0;

bool coolingConfigured() {
  if (!(COMMISSIONED && CURRENT_CALIBRATED && PIN_PRIMARY >= 0 && PIN_BACKUP >= 0 && PIN_ONEWIRE >= 0 && PIN_CURRENT >= 0 && PIN_REED >= 0 &&
        CURRENT_MV_PER_AMP > 0 && CHAMBER_ROM[0] != 0 && HEATSINK_ROM[0] != 0)) {
    return false;
  }
  const int pins[] = {PIN_PRIMARY, PIN_BACKUP, PIN_ONEWIRE, PIN_CURRENT, PIN_REED, PIN_SDA, PIN_SCL, PIN_GPS_RX, PIN_GPS_TX,
                      PIN_GREEN, PIN_YELLOW, PIN_RED, PIN_BUZZER};
  for (unsigned i = 0; i < sizeof(pins) / sizeof(pins[0]); i++) {
    for (unsigned j = i + 1; j < sizeof(pins) / sizeof(pins[0]); j++) {
      if (pins[i] >= 0 && pins[i] == pins[j]) return false;
    }
  }
  bool different = false;
  for (unsigned i = 0; i < 8; i++) {
    if (CHAMBER_ROM[i] != HEATSINK_ROM[i]) different = true;
  }
  return different;
}

static void pinOff(int pin) {
  if (pin >= 0) {
    digitalWrite(pin, OUTPUT_INACTIVE);
    pinMode(pin, OUTPUT);
  }
}

void coolingBegin() {
  pinOff(PIN_PRIMARY);
  pinOff(PIN_BACKUP);
  if (PIN_FAN >= 0) {
    pinOff(PIN_FAN);
  }
  primary = backup = false;
  offAt = millis();
}

void coolingApply(coldchain::Output command, uint32_t now) {
  if (!coolingConfigured() || (command.primary && command.backup)) {
    command.primary = false;
    command.backup = false;
  }
  bool switching = (primary && command.backup) || (backup && command.primary);
  if (primary && !command.primary) {
    digitalWrite(PIN_PRIMARY, OUTPUT_INACTIVE);
    primary = false;
    offAt = now;
  }
  if (backup && !command.backup) {
    digitalWrite(PIN_BACKUP, OUTPUT_INACTIVE);
    backup = false;
    offAt = now;
  }
  if (switching) return;
  if (command.primary && !backup && now - offAt >= 2000) {
    digitalWrite(PIN_PRIMARY, OUTPUT_ACTIVE);
    primary = true;
  }
  if (command.backup && !primary && now - offAt >= 2000) {
    digitalWrite(PIN_BACKUP, OUTPUT_ACTIVE);
    backup = true;
  }
}

// These booleans confirm output register intent, not MOSFET conduction. ACS712 is independent primary evidence.
bool primaryObserved() { return primary; }
bool backupObserved() { return backup; }
