#include "sensors.h"
#include "config.h"
#include <Wire.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Adafruit_SHT31.h>
#include <TinyGPSPlus.h>
#include <sys/time.h>

static OneWire* bus = nullptr;
static DallasTemperature* probes = nullptr;
static Adafruit_SHT31 sht;
static TinyGPSPlus gps;
static HardwareSerial gpsSerial(1);
static SensorData data;

static uint8_t activeChamberRom[8] = {0};
static uint8_t activeHeatsinkRom[8] = {0};
static bool heatsinkRomDiscovered = false;

static bool shtReady = false, conversion = false, reedCandidate = false;
static uint32_t conversionAt = 0, lastSensors = 0, lastProbe = 0, lastCurrent = 0, reedAt = 0, doorAt = 0;
static float temps[61];
static uint32_t times[61];
static size_t count = 0;

static bool validTemp(float x) {
  return isfinite(x) && x >= -55.0f && x <= 125.0f && fabsf(x - (-127.0f)) > 0.1f && fabsf(x - 85.0f) > 0.01f;
}

static void formatRom(const uint8_t rom[8], char out[24]) {
  snprintf(out, 24, "%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X",
           rom[0], rom[1], rom[2], rom[3], rom[4], rom[5], rom[6], rom[7]);
}

bool getDiscoveredHeatsinkRom(uint8_t outRom[8]) {
  if (heatsinkRomDiscovered) {
    memcpy(outRom, activeHeatsinkRom, 8);
    return true;
  }
  return false;
}

void sensorsBegin() {
  memcpy(activeChamberRom, CHAMBER_ROM, 8);

  bool configuredHeatsink = false;
  for (int i = 0; i < 8; i++) {
    if (HEATSINK_ROM[i] != 0) configuredHeatsink = true;
  }
  if (configuredHeatsink) {
    memcpy(activeHeatsinkRom, HEATSINK_ROM, 8);
    heatsinkRomDiscovered = true;
  }

  Serial.printf("[BOOT] OneWire GPIO%d\n", PIN_ONEWIRE);
  if (PIN_ONEWIRE >= 0) {
    bus = new OneWire(PIN_ONEWIRE);
    probes = new DallasTemperature(bus);
    probes->begin();
    probes->setResolution(12);
    probes->setWaitForConversion(false);

    int devCount = probes->getDeviceCount();
    Serial.printf("[DS18B20] count=%d\n", devCount);

    DeviceAddress address;
    for (int i = 0; i < devCount; i++) {
      if (probes->getAddress(address, i)) {
        char romStr[24];
        formatRom(address, romStr);
        Serial.printf("[DS18B20] ROM=%s\n", romStr);

        // Recognize confirmed chamber ROM
        if (memcmp(address, CHAMBER_ROM, 8) == 0) {
          // Confirmed chamber probe
        } else if (!heatsinkRomDiscovered && address[0] == 0x28) {
          // Auto-identify other family 0x28 probe as heatsink
          memcpy(activeHeatsinkRom, address, 8);
          heatsinkRomDiscovered = true;
        }
      }
    }

    char chRomStr[24];
    formatRom(activeChamberRom, chRomStr);
    Serial.printf("[BOOT] chamber ROM=%s\n", chRomStr);

    if (heatsinkRomDiscovered) {
      char hsRomStr[24];
      formatRom(activeHeatsinkRom, hsRomStr);
      Serial.printf("[BOOT] heatsink ROM=%s\n", hsRomStr);
    } else {
      Serial.println("[BOOT] heatsink ROM=PENDING (waiting for second probe)");
    }
  } else {
    Serial.println("[BOOT] OneWire SKIPPED (pin=-1)");
  }

  Serial.printf("[BOOT] SHT31 SDA=%d SCL=%d addr=0x%02X\n", PIN_SDA, PIN_SCL, SHT31_ADDRESS);
  if (PIN_SDA >= 0 && PIN_SCL >= 0) {
    Wire.begin(PIN_SDA, PIN_SCL);
    Wire.setTimeOut(40);
    delay(50); // Stabilization delay
    shtReady = sht.begin(SHT31_ADDRESS);
    if (shtReady) {
      Serial.printf("[BOOT] SHT31 SDA=%d SCL=%d addr=0x%02X OK\n", PIN_SDA, PIN_SCL, SHT31_ADDRESS);
    } else {
      Serial.printf("[BOOT] SHT31 SDA=%d SCL=%d addr=0x%02X NOT DETECTED\n", PIN_SDA, PIN_SCL, SHT31_ADDRESS);
    }
  } else {
    Serial.println("[BOOT] I2C SKIPPED (pins disabled)");
  }

  if (PIN_CURRENT >= 0) {
    analogReadResolution(12);
    analogSetPinAttenuation(PIN_CURRENT, ADC_11db);
    Serial.printf("[BOOT] ACS712 GPIO%d %s\n", PIN_CURRENT, CURRENT_CALIBRATED ? "CALIBRATED" : "UNCALIBRATED");
  } else {
    Serial.println("[BOOT] Current SKIPPED (pin=-1)");
  }

  if (PIN_REED >= 0) {
    pinMode(PIN_REED, INPUT_PULLUP);
    data.doorOK = true;
    reedCandidate = (digitalRead(PIN_REED) == HIGH);
    data.doorOpen = reedCandidate;
    Serial.printf("[BOOT] Reed GPIO%d OK\n", PIN_REED);
  } else {
    Serial.println("[BOOT] Reed SKIPPED (pin=-1)");
  }

  if (PIN_VIBRATION >= 0) {
    pinMode(PIN_VIBRATION, INPUT_PULLUP);
    data.vibrationOK = true;
    data.vibrationDetected = (digitalRead(PIN_VIBRATION) == LOW);
    Serial.printf("[BOOT] Vibration GPIO%d OK\n", PIN_VIBRATION);
  } else {
    Serial.println("[BOOT] Vibration SKIPPED (pin=-1)");
  }
}

void gpsBegin() {
  if (PIN_GPS_RX >= 0 && PIN_GPS_TX >= 0) {
    gpsSerial.begin(9600, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);
    Serial.printf("[BOOT] GPS RX=%d TX=%d baud=9600\n", PIN_GPS_RX, PIN_GPS_TX);
  } else {
    Serial.println("[BOOT] GPS SKIPPED (pins disabled)");
  }
}

void sensorsTick(uint32_t now) {
  if (PIN_GPS_RX >= 0 && PIN_GPS_TX >= 0) {
    for (int n = 0; n < 128 && gpsSerial.available(); n++) {
      gps.encode(gpsSerial.read());
    }
  }

  if (time(nullptr) < 1704067200 && gps.date.isValid() && gps.time.isValid() &&
      gps.date.age() < 30000 && gps.time.age() < 30000 && gps.date.year() >= 2024) {
    struct tm stamp = {};
    stamp.tm_year = gps.date.year() - 1900;
    stamp.tm_mon = gps.date.month() - 1;
    stamp.tm_mday = gps.date.day();
    stamp.tm_hour = gps.time.hour();
    stamp.tm_min = gps.time.minute();
    stamp.tm_sec = gps.time.second();
    setenv("TZ", "UTC0", 1);
    tzset();
    timeval tv = {mktime(&stamp), 0};
    settimeofday(&tv, nullptr);
  }

  if (data.doorOK && PIN_REED >= 0) {
    bool raw = (digitalRead(PIN_REED) == HIGH);
    if (raw != reedCandidate) {
      reedCandidate = raw;
      reedAt = now;
    }
    if (now - reedAt >= DOOR_DEBOUNCE_MS && data.doorOpen != raw) {
      data.doorOpen = raw;
      doorAt = now;
    }
    data.doorSeconds = data.doorOpen ? (now - doorAt) / 1000.0f : 0;
  }

  if (data.vibrationOK && PIN_VIBRATION >= 0) {
    bool rawVib = (digitalRead(PIN_VIBRATION) == LOW);
    if (rawVib != data.vibrationDetected) {
      data.vibrationDetected = rawVib;
      Serial.printf("vibration=%s\n", rawVib ? "DETECTED" : "NORMAL");
    }
  }

  if (PIN_CURRENT >= 0 && now - lastCurrent >= 50) {
    lastCurrent = now;
    uint32_t mv = analogReadMilliVolts(PIN_CURRENT);
    data.currentAdcMv = mv;
    data.currentOK = CURRENT_CALIBRATED && CURRENT_MV_PER_AMP > 0 && mv > 20 && mv < 3000;
    float amps = CURRENT_MV_PER_AMP > 0 ? fabsf((float(mv) - CURRENT_ZERO_MV) / CURRENT_MV_PER_AMP) : NAN;
    data.currentOK = data.currentOK && isfinite(amps) && amps <= 20;
    if (data.currentOK) {
      data.current = isfinite(data.current) ? (.25f * amps + .75f * data.current) : amps;
    } else {
      data.current = NAN;
    }
  }

  if (probes && conversion && now - conversionAt >= 800) {
    float rawChamber = probes->getTempC(activeChamberRom);
    float rawHeatsink = heatsinkRomDiscovered ? probes->getTempC(activeHeatsinkRom) : NAN;

    data.chamberOK = validTemp(rawChamber);
    data.heatsinkOK = heatsinkRomDiscovered && validTemp(rawHeatsink);

    data.chamber = data.chamberOK ? rawChamber : NAN;
    data.heatsink = data.heatsinkOK ? rawHeatsink : NAN;

    lastProbe = now;
    conversion = false;

    if (data.chamberOK) {
      if (count == 61) {
        for (size_t i = 1; i < count; i++) {
          temps[i - 1] = temps[i];
          times[i - 1] = times[i];
        }
        count--;
      }
      temps[count] = data.chamber;
      times[count] = now;
      count++;
      while (count > 1 && now - times[0] > 60000) {
        for (size_t i = 1; i < count; i++) {
          temps[i - 1] = temps[i];
          times[i - 1] = times[i];
        }
        count--;
      }
      data.rate = count > 1 && now != times[0] ? (data.chamber - temps[0]) * 60000.0f / (now - times[0]) : 0;
    }
  }

  if (now - lastSensors >= SENSOR_MS) {
    lastSensors = now;
    if (probes && !conversion) {
      probes->requestTemperatures();
      conversion = true;
      conversionAt = now;
    }
    if (shtReady) {
      float t = sht.readTemperature();
      float h = sht.readHumidity();
      data.shtOK = isfinite(t) && t >= -40 && t <= 125 && isfinite(h) && h >= 0 && h <= 100;
      if (data.shtOK) {
        data.shtTemp = t;
        data.humidity = h;
      } else {
        data.shtTemp = NAN;
        data.humidity = NAN;
      }
    }
  }
}

SensorData sensorSnapshot(uint32_t now) {
  SensorData result = data;
  if (now - lastProbe > SENSOR_TIMEOUT_MS) {
    result.chamberOK = false;
    result.heatsinkOK = false;
    result.chamber = NAN;
    result.heatsink = NAN;
  }
  if (now - lastCurrent > 500) {
    result.currentOK = false;
    result.current = NAN;
  }
  result.gpsFix = gps.location.isValid() && gps.location.age() <= GPS_MAX_AGE_MS;
  if (result.gpsFix) {
    result.latitude = gps.location.lat();
    result.longitude = gps.location.lng();
    result.speed = gps.speed.isValid() && gps.speed.age() < GPS_MAX_AGE_MS ? gps.speed.kmph() : NAN;
    result.gpsAge = gps.location.age() / 1000.0f;
    result.satellites = gps.satellites.isValid() ? gps.satellites.value() : 0;
  } else {
    result.latitude = NAN;
    result.longitude = NAN;
    result.speed = NAN;
    result.gpsAge = NAN;
    result.satellites = gps.satellites.isValid() ? gps.satellites.value() : 0;
  }
  return result;
}
