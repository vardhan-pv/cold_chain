#include "display.h"
#include "config.h"
#include "cooling.h"
#include <WiFi.h>
#include <Adafruit_SSD1306.h>

static Adafruit_SSD1306* oled = nullptr;
static bool oledReady = false;

static void set(int pin, bool on) {
  if (pin >= 0) digitalWrite(pin, on ? HIGH : LOW);
}

void displayBegin() {
  Serial.printf("[BOOT] LED GPIO%d\n", PIN_GREEN);
  Serial.printf("[BOOT] Buzzer GPIO%d\n", PIN_BUZZER);
  for (int p : {PIN_GREEN, PIN_YELLOW, PIN_RED, PIN_BUZZER}) {
    if (p >= 0) {
      digitalWrite(p, LOW);
      pinMode(p, OUTPUT);
    }
  }

  // Brief 200 ms status test at boot
  if (PIN_GREEN >= 0) digitalWrite(PIN_GREEN, HIGH);
  if (PIN_BUZZER >= 0) digitalWrite(PIN_BUZZER, HIGH);
  delay(200);
  if (PIN_BUZZER >= 0) digitalWrite(PIN_BUZZER, LOW);

  if (OPTIONAL_OLED && PIN_SDA >= 0 && PIN_SCL >= 0) {
    oled = new Adafruit_SSD1306(128, 64, &Wire, -1);
    oledReady = oled ? oled->begin(SSD1306_SWITCHCAPVCC, 0x3C) : false;
    Serial.printf("[BOOT] OLED ready=%s\n", oledReady ? "true" : "false");
  }
}

void displayTick(const SensorData& data, const coldchain::Output& output, bool backendOK, uint32_t now) {
  bool isAlarm = output.alarm || output.state == coldchain::State::PRIMARY_FAULT || output.state == coldchain::State::CRITICAL_FAILURE;
  bool isWarning = output.state == coldchain::State::WARNING || (data.doorOK && data.doorOpen);

  if (isAlarm) {
    set(PIN_GREEN, true);
    set(PIN_YELLOW, false);
    set(PIN_RED, true);
    set(PIN_BUZZER, (now % 500 < 250)); // Warning alarm tone
  } else if (isWarning) {
    set(PIN_GREEN, (now % 1000 < 500)); // Blinking status LED on warning/door open
    set(PIN_YELLOW, true);
    set(PIN_RED, false);
    set(PIN_BUZZER, (data.doorOK && data.doorOpen) && (now % 2000 < 100)); // Soft periodic door chime
  } else {
    // Normal operation: Status LED solid ON, Buzzer OFF
    set(PIN_GREEN, true);
    set(PIN_YELLOW, false);
    set(PIN_RED, false);
    set(PIN_BUZZER, false);
  }

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
