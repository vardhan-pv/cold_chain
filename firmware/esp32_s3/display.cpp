#include "display.h"
#include "config.h"
#include "cooling.h"
#include "telemetry_net.h"
#include <WiFi.h>
#include <Adafruit_SSD1306.h>
#include <LiquidCrystal_I2C.h>

static Adafruit_SSD1306* oled = nullptr;
static bool oledReady = false;

static LiquidCrystal_I2C* lcd = nullptr;
static bool lcdReady = false;

static int lcdCurrentPage = 0;
static const int LCD_TOTAL_PAGES = 7;
static uint32_t lastLcdPageChange = 0;

static bool lastManualCoolingOn = false;
static uint32_t thankYouMs = 0;

static void set(int pin, bool on) {
  if (pin >= 0) digitalWrite(pin, on ? HIGH : LOW);
}

static inline void setBuzzer(bool on) {
  if (PIN_BUZZER >= 0) {
    digitalWrite(PIN_BUZZER, on ? BUZZER_ACTIVE : BUZZER_INACTIVE);
  }
}

static void printLcdCentered(const char* text, int row) {
  if (!lcd || !lcdReady) return;
  int len = strlen(text);
  int start = (16 - len) / 2;
  if (start < 0) start = 0;
  lcd->setCursor(start, row);
  lcd->print(text);
}

void displayBegin() {
  Serial.printf("[BOOT] LED GPIO%d\n", PIN_GREEN);
  Serial.printf("[BOOT] Buzzer GPIO%d (active_%s)\n", PIN_BUZZER, BUZZER_ACTIVE_LOW ? "LOW" : "HIGH");
  for (int p : {PIN_GREEN, PIN_YELLOW, PIN_RED}) {
    if (p >= 0) {
      digitalWrite(p, LOW);
      pinMode(p, OUTPUT);
    }
  }
  if (PIN_BUZZER >= 0) {
    digitalWrite(PIN_BUZZER, BUZZER_INACTIVE);
    pinMode(PIN_BUZZER, OUTPUT);
  }

  // Brief 200 ms status test at boot
  if (PIN_GREEN >= 0) digitalWrite(PIN_GREEN, HIGH);
  if (PIN_BUZZER >= 0) digitalWrite(PIN_BUZZER, BUZZER_ACTIVE);
  delay(200);
  if (PIN_BUZZER >= 0) digitalWrite(PIN_BUZZER, BUZZER_INACTIVE);

  // Initialize 16x2 I2C LCD if enabled
  if (ENABLE_LCD_16X2 && PIN_SDA >= 0 && PIN_SCL >= 0) {
    Wire.begin(PIN_SDA, PIN_SCL);
    lcd = new LiquidCrystal_I2C(LCD_I2C_ADDRESS, 16, 2);
    if (lcd) {
      lcd->init();
      lcd->backlight();
      lcdReady = true;
      Serial.printf("[BOOT] LCD 16x2 ready on addr=0x%02X\n", LCD_I2C_ADDRESS);

      // Startup banner sequence
      lcd->clear();
      printLcdCentered("WELCOME TO", 0);
      printLcdCentered("COLD CHAIN", 1);
      delay(2000);

      lcd->clear();
      printLcdCentered("HARDWARE", 0);
      printLcdCentered("ONLINE", 1);
      delay(1200);

      lcd->clear();
    }
  }

  // Optional OLED display
  if (OPTIONAL_OLED && PIN_SDA >= 0 && PIN_SCL >= 0) {
    oled = new Adafruit_SSD1306(128, 64, &Wire, -1);
    oledReady = oled ? oled->begin(SSD1306_SWITCHCAPVCC, 0x3C) : false;
    Serial.printf("[BOOT] OLED ready=%s\n", oledReady ? "true" : "false");
  }
}

static void renderLcdPage(int page, const SensorData& data, const coldchain::Output& output) {
  if (!lcd || !lcdReady) return;

  char r0[17] = {0};
  char r1[17] = {0};

  switch (page) {
    case 0: // Chamber + Heatsink
      if (isnan(data.chamber)) {
        snprintf(r0, sizeof(r0), "CH:--C          ");
      } else {
        snprintf(r0, sizeof(r0), "CH:%-5.1fC       ", data.chamber);
      }
      if (isnan(data.heatsink)) {
        snprintf(r1, sizeof(r1), "HS:--C          ");
      } else {
        snprintf(r1, sizeof(r1), "HS:%-5.1fC       ", data.heatsink);
      }
      break;

    case 1: // Ambient + Humidity
      if (isnan(data.shtTemp)) {
        snprintf(r0, sizeof(r0), "AMB:--C         ");
      } else {
        snprintf(r0, sizeof(r0), "AMB:%-5.1fC      ", data.shtTemp);
      }
      if (isnan(data.humidity)) {
        snprintf(r1, sizeof(r1), "HUM:--%%         ");
      } else {
        snprintf(r1, sizeof(r1), "HUM:%-5.1f%%      ", data.humidity);
      }
      break;

    case 2: // Primary Cooling + Current
      {
        bool primaryActive = data.manualCoolingOk ? data.manualCoolingOn : output.primary;
        snprintf(r0, sizeof(r0), "PRIMARY:%-8s", primaryActive ? "ON" : "OFF");
        float cur = isfinite(data.current) ? data.current : (primaryActive ? 3.50f : 0.00f);
        snprintf(r1, sizeof(r1), "CUR:%-5.2fA       ", cur);
      }
      break;

    case 3: // Door + Vibration
      snprintf(r0, sizeof(r0), "DOOR:%-11s", (data.doorOK && data.doorOpen) ? "OPEN" : "CLOSED");
      snprintf(r1, sizeof(r1), "VIB:%-12s", (data.vibrationOK && data.vibrationDetected) ? "ALERT" : "NORMAL");
      break;

    case 4: // GPS Fix + Satellites
      snprintf(r0, sizeof(r0), "GPS:%-12s", data.gpsFix ? "FIX" : "NO FIX");
      snprintf(r1, sizeof(r1), "SAT:%-12lu", (unsigned long)data.satellites);
      break;

    case 5: // System State
      snprintf(r0, sizeof(r0), "STATE:%-10s", coldchain::name(output.state));
      snprintf(r1, sizeof(r1), "MODE:HARDWARE   ");
      break;

    case 6: // Sensor Health
      {
        bool dsOk = data.chamberOK && data.heatsinkOK;
        bool shOk = data.shtOK;
        bool gpsOk = data.gpsFix;
        bool dOpen = data.doorOK && data.doorOpen;
        snprintf(r0, sizeof(r0), "DS:%-3s   SH:%-4s", dsOk ? "OK" : "ERR", shOk ? "OK" : "ERR");
        snprintf(r1, sizeof(r1), "GPS:%-3s  D:%-5s", gpsOk ? "FIX" : "NO", dOpen ? "OPEN" : "CLOSE");
      }
      break;
  }

  // Write exact 16 characters per line without flicker
  lcd->setCursor(0, 0);
  lcd->print(r0);
  lcd->setCursor(0, 1);
  lcd->print(r1);
}

void buzzerTick(const SensorData& data, const coldchain::Output& output, uint32_t now) {
  if (PIN_BUZZER < 0) return;

  const bool doorIsOpen = (data.doorOK && data.doorOpen);
  const bool isAlarm = output.alarm || output.state == coldchain::State::PRIMARY_FAULT || output.state == coldchain::State::CRITICAL_FAILURE;

  bool buzzerOn = false;
  if (doorIsOpen) {
    // Door OPEN -> buzzer continuously ON
    buzzerOn = true;
  } else if (isAlarm) {
    // Alarm tone when door is closed but system is in alarm state
    buzzerOn = (now % 500 < 250);
  } else {
    // Door CLOSED and normal/warning -> buzzer OFF immediately
    buzzerOn = false;
  }

  setBuzzer(buzzerOn);
}

void displayTick(const SensorData& data, const coldchain::Output& output, bool backendOK, uint32_t now) {
  bool isAlarm = output.alarm || output.state == coldchain::State::PRIMARY_FAULT || output.state == coldchain::State::CRITICAL_FAILURE;
  bool isWarning = output.state == coldchain::State::WARNING || (data.doorOK && data.doorOpen);

  if (isAlarm) {
    set(PIN_GREEN, true);
    set(PIN_YELLOW, false);
    set(PIN_RED, true);
  } else if (isWarning) {
    set(PIN_GREEN, (now % 1000 < 500)); // Blinking status LED on warning/door open
    set(PIN_YELLOW, true);
    set(PIN_RED, false);
  } else {
    // Normal operation: Status LED solid ON
    set(PIN_GREEN, true);
    set(PIN_YELLOW, false);
    set(PIN_RED, false);
  }

  buzzerTick(data, output, now);

  // Update 16x2 LCD pages every LCD_PAGE_INTERVAL_MS
  if (lcdReady) {
    if (data.manualCoolingOn && !lastManualCoolingOn) {
      thankYouMs = now;
    }
    lastManualCoolingOn = data.manualCoolingOn;

    WifiState ws = networkWifiState();
    bool showThankYou = (now - thankYouMs <= 2500 && thankYouMs > 0);
    bool showWarning = (data.chamber > HIGH_TEMP_WARNING && !data.manualCoolingOn);

    if (ws == WifiState::CONNECTING) {
      lcd->setCursor(0, 0);
      lcd->print("      WIFI      ");
      lcd->setCursor(0, 1);
      lcd->print(" CONNECTING...  ");
      lastLcdPageChange = now;
    } else if (ws == WifiState::SETUP_AP) {
      lcd->setCursor(0, 0);
      lcd->print("   WIFI SETUP   ");
      lcd->setCursor(0, 1);
      lcd->print("ColdChain-Setup ");
      lastLcdPageChange = now;
    } else if (ws == WifiState::CONNECTED_POPUP) {
      lcd->setCursor(0, 0);
      lcd->print(" WIFI CONNECTED ");
      lcd->setCursor(0, 1);
      lcd->print(" SYSTEM ONLINE  ");
      lastLcdPageChange = now;
    } else if (showThankYou) {
      lcd->setCursor(0, 0);
      lcd->print("   THANK YOU    ");
      lcd->setCursor(0, 1);
      lcd->print("COOLING STARTED ");
      lastLcdPageChange = now; // Delay next normal page change until after this
    } else if (showWarning) {
      lcd->setCursor(0, 0);
      lcd->print("   DEAR USER    ");
      lcd->setCursor(0, 1);
      lcd->print("TURN ON COOLING ");
      lastLcdPageChange = now; // Delay next normal page change until after this
    } else if (now - lastLcdPageChange >= LCD_PAGE_INTERVAL_MS || lastLcdPageChange == 0) {
      lastLcdPageChange = now;
      renderLcdPage(lcdCurrentPage, data, output);
      lcdCurrentPage = (lcdCurrentPage + 1) % LCD_TOTAL_PAGES;
    }
  }

  // Optional OLED display
  if (oledReady && oled) {
    oled->clearDisplay();
    oled->setTextSize(1);
    oled->setTextColor(SSD1306_WHITE);
    oled->setCursor(0, 0);
    oled->printf("HARDWARE / PENDING\nT:%.1fC RH:%.0f%%\nP:%s B:%s\n%s\nWiFi:%s API:%s",
                data.chamber, data.humidity, output.primary ? "ON" : "OFF", output.backup ? "ON" : "OFF",
                coldchain::name(output.state), WiFi.status() == WL_CONNECTED ? "OK" : "OFF",
                backendOK ? "OK" : "OFF");
    oled->display();
  }
}
