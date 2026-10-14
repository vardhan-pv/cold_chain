#pragma once
#include <Arduino.h>

#if __has_include("commissioning.h")
#include "commissioning.h"
#else
constexpr bool COMMISSIONED = false;
constexpr int PIN_ONEWIRE = -1, PIN_SDA = -1, PIN_SCL = -1, PIN_CURRENT = -1, PIN_REED = -1, PIN_COOLING_CONFIRM = -1;
constexpr int PIN_GPS_RX = -1, PIN_GPS_TX = -1, PIN_PRIMARY = -1, PIN_BACKUP = -1;
constexpr int PIN_GREEN = -1, PIN_YELLOW = -1, PIN_RED = -1, PIN_BUZZER = -1;
constexpr bool BUZZER_ACTIVE_LOW = false;
constexpr uint8_t BUZZER_ACTIVE = BUZZER_ACTIVE_LOW ? LOW : HIGH;
constexpr uint8_t BUZZER_INACTIVE = BUZZER_ACTIVE_LOW ? HIGH : LOW;
constexpr bool CURRENT_CALIBRATED = false;
constexpr bool ENABLE_EMULATED_CURRENT = false;
constexpr float EMULATED_PRIMARY_CURRENT_A = 3.5f;
constexpr float CURRENT_ZERO_MV = 0, CURRENT_MV_PER_AMP = 0;
constexpr uint8_t CHAMBER_ROM[8] = {0}, HEATSINK_ROM[8] = {0};
constexpr bool OPTIONAL_OLED = false;
constexpr bool ENABLE_LCD_16X2 = false;
constexpr uint8_t LCD_I2C_ADDRESS = 0x27;
constexpr uint32_t LCD_PAGE_INTERVAL_MS = 2000;
constexpr bool OPTIONAL_FAULT_BUTTONS = false;
constexpr int PIN_INJECT_PRIMARY = -1, PIN_INJECT_BACKUP = -1;
constexpr int PIN_FAN = -1, PIN_VIBRATION = -1;
#endif

constexpr float HIGH_TEMP_WARNING = 10.0f;

constexpr uint32_t TELEMETRY_MS = 5000, SENSOR_MS = 1000, SAFETY_MS = 50, DOOR_DEBOUNCE_MS = 40;
constexpr uint32_t SENSOR_TIMEOUT_MS = 3500, GPS_MAX_AGE_MS = 30000;
constexpr uint8_t OUTPUT_ACTIVE = HIGH, OUTPUT_INACTIVE = LOW;
constexpr uint8_t SHT31_ADDRESS = 0x44;
