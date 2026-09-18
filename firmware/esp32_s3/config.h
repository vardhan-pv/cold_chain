#pragma once
#include <Arduino.h>

#if __has_include("commissioning.h")
#include "commissioning.h"
#else
constexpr bool COMMISSIONED = false;
constexpr int PIN_ONEWIRE = -1, PIN_SDA = -1, PIN_SCL = -1, PIN_CURRENT = -1, PIN_REED = -1;
constexpr int PIN_GPS_RX = -1, PIN_GPS_TX = -1, PIN_PRIMARY = -1, PIN_BACKUP = -1;
constexpr int PIN_GREEN = -1, PIN_YELLOW = -1, PIN_RED = -1, PIN_BUZZER = -1;
constexpr bool CURRENT_CALIBRATED = false;
constexpr float CURRENT_ZERO_MV = 0, CURRENT_MV_PER_AMP = 0;
constexpr uint8_t CHAMBER_ROM[8] = {0}, HEATSINK_ROM[8] = {0};
constexpr bool OPTIONAL_OLED = false;
constexpr bool OPTIONAL_FAULT_BUTTONS = false;
constexpr int PIN_INJECT_PRIMARY = -1, PIN_INJECT_BACKUP = -1;
constexpr int PIN_FAN = -1;
#endif

constexpr uint32_t TELEMETRY_MS = 5000, SENSOR_MS = 1000, SAFETY_MS = 50, DOOR_DEBOUNCE_MS = 40;
constexpr uint32_t SENSOR_TIMEOUT_MS = 3500, GPS_MAX_AGE_MS = 30000;
constexpr uint8_t OUTPUT_ACTIVE = HIGH, OUTPUT_INACTIVE = LOW;
constexpr uint8_t SHT31_ADDRESS = 0x44;
