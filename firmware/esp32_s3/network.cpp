#include <WiFi.h>
#include "telemetry_net.h"
#include "config.h"
#include "cooling.h"
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include <atomic>
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif
struct Packet{char json[2048];};
static QueueHandle_t queue=nullptr;
static std::atomic<uint32_t> lastSuccess{0},dropped{0},sequence{0},riskAt{0};
static std::atomic<float> advisoryRisk{NAN};
static char bootID[33];
static bool beginRequest(HTTPClient& http,WiFiClient& plain,WiFiClientSecure& secure,const String& url){
  bool ready=false;
  if(url.startsWith("https://")){
    if(strlen(ROOT_CA)>0)secure.setCACert(ROOT_CA);
    else secure.setInsecure();
    ready=http.begin(secure,url);
  } else if(ALLOW_LAB_HTTP&&url.startsWith("http://"))ready=http.begin(plain,url);
  if(ready){
    http.setConnectTimeout(1500);http.setTimeout(1500);
    http.addHeader("Content-Type","application/json");http.addHeader("X-Device-Token",DEVICE_TOKEN);
  }
  return ready&&strlen(DEVICE_TOKEN)>0;
}
static void acknowledgeLocalDecision(){
  // Network task only. Never write GPIO or change the local controller here.
  String root=BACKEND_URL;int api=root.indexOf("/api/");if(api<0)return;root=root.substring(0,api);
  HTTPClient http;WiFiClient plain;WiFiClientSecure secure;
  String pending=root+"/api/v1/control/"+DEVICE_ID+"/pending";
  if(!beginRequest(http,plain,secure,pending)){http.end();return;}
  int code=http.GET();String response=code==200?http.getString():String();http.end();
  if(code!=200)return;
  JsonDocument result;if(deserializeJson(result,response)||!result["command_available"].as<bool>())return;
  JsonObject command=result["command"].as<JsonObject>();
  int id=command["id"]|0;const char* boot=command["boot_id"]|"";
  if(id<=0||strcmp(boot,bootID)!=0)return;
  bool primary=primaryObserved(),backup=backupObserved();
  bool matches=command["based_on_sequence"].as<uint32_t>()<=sequence&&
      command["primary_cooling"].as<bool>()==primary&&command["backup_cooling"].as<bool>()==backup;
  JsonDocument ack;ack["device_id"]=DEVICE_ID;ack["boot_id"]=bootID;ack["sequence"]=(uint32_t)sequence.load();
  ack["outcome"]=matches?"APPLIED":"REJECTED";ack["primary_cooling"]=primary;ack["backup_cooling"]=backup;
  ack["reason"]=matches?"Local safety loop agrees; GPIO command state reported":"Local safety loop disagrees; remote override inhibited";
  String body;serializeJson(ack,body);
  String target=root+"/api/v1/control/"+String(id)+"/acknowledge";
  if(beginRequest(http,plain,secure,target)){
    int status=http.POST(body);
    Serial.printf("{\"event\":\"command_ack\",\"id\":%d,\"http\":%d,\"local_match\":%s}\n",id,status,matches?"true":"false");
  }
  http.end();
}
static std::atomic<bool> clockSynchronized{false};

static void syncNTP() {
  Serial.println("[BOOT] NTP starting...");
  configTime(0, 0, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
  for (int attempt = 1; attempt <= 30; attempt++) {
    time_t now = time(nullptr);
    if (now > 1700000000) {
      clockSynchronized = true;
      Serial.println("[BOOT] NTP OK");
      return;
    }
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
  Serial.println("[BOOT] NTP timeout");
}

static void worker(void*){
  if (strlen(WIFI_SSID) == 0) {
    Serial.println("[BOOT] WiFi no SSID configured");
  } else {
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.persistent(false);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.println("[BOOT] WiFi connecting...");
  }
  
  uint32_t connectStartedAt = millis();
  uint32_t lastNtpRetry = 0;
  uint32_t retryMs = 1000;
  bool wasConnected = false;
  bool reportedConnecting = true;
  wl_status_t lastStatus = (wl_status_t)99;
  static Packet packet;
  bool holding = false;

  for(;;){
    wl_status_t status = WiFi.status();

    if (status != WL_CONNECTED) {
      wasConnected = false;
      uint32_t now = millis();

      if (strlen(WIFI_SSID) > 0) {
        if (status != lastStatus) {
          lastStatus = status;
          switch (status) {
            case WL_NO_SSID_AVAIL:
              Serial.println("[WiFi] no SSID");
              break;
            case WL_CONNECT_FAILED:
              Serial.println("[WiFi] auth/connect failed");
              break;
            case WL_IDLE_STATUS:
            case WL_DISCONNECTED:
            default:
              if (!reportedConnecting) {
                Serial.println("[WiFi] connecting...");
                reportedConnecting = true;
              }
              break;
          }
        }

        if (now - connectStartedAt >= 15000) {
          Serial.println("[WiFi] retry after timeout");
          WiFi.disconnect(false, false);
          vTaskDelay(pdMS_TO_TICKS(100));
          Serial.println("[WiFi] begin");
          WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
          Serial.println("[WiFi] connecting...");
          connectStartedAt = now;
          reportedConnecting = true;
          lastStatus = (wl_status_t)99;
        }
      }

      vTaskDelay(pdMS_TO_TICKS(500));
      continue;
    }

    if (!wasConnected) {
      wasConnected = true;
      reportedConnecting = false;
      lastStatus = WL_CONNECTED;
      connectStartedAt = millis();
      Serial.println("[WiFi] connected");
      Serial.printf("[WiFi] IP: %s\n", WiFi.localIP().toString().c_str());
      Serial.printf("[WiFi] RSSI: %d dBm\n", WiFi.RSSI());
      syncNTP();
      lastNtpRetry = millis();
    } else if (!clockSynchronized && (millis() - lastNtpRetry >= 30000)) {
      lastNtpRetry = millis();
      syncNTP();
    }

    if (!clockSynchronized) {
      vTaskDelay(pdMS_TO_TICKS(500));
      continue;
    }

    if (!holding) holding = xQueueReceive(queue, &packet, pdMS_TO_TICKS(100)) == pdTRUE;
    if (!holding) continue;

    HTTPClient http; WiFiClient plain; WiFiClientSecure secure;
    bool configured = false;
    if (strncmp(BACKEND_URL, "https://", 8) == 0) {
      if (strlen(ROOT_CA) > 0) secure.setCACert(ROOT_CA);
      else secure.setInsecure();
      configured = http.begin(secure, BACKEND_URL);
    } else if (ALLOW_LAB_HTTP && strncmp(BACKEND_URL, "http://", 7) == 0) {
      configured = http.begin(plain, BACKEND_URL);
    }
    int status_code = -1;
    if (configured && strlen(DEVICE_TOKEN)) {
      http.setConnectTimeout(2500); http.setTimeout(2500);
      http.addHeader("Content-Type", "application/json"); http.addHeader("X-Device-Token", DEVICE_TOKEN);
      Serial.printf("Sending telemetry to %s...\n", BACKEND_URL);
      status_code = http.POST(reinterpret_cast<uint8_t*>(packet.json), strlen(packet.json));
      Serial.printf("HTTP Response Code: %d\n", status_code);
      if (status_code >= 200 && status_code < 300) {
        JsonDocument response;
        if (!deserializeJson(response, http.getString()) && !response["archived"].as<bool>() &&
            !response["prediction"]["ensemble_probability"].isNull()) {
          float risk = response["prediction"]["ensemble_probability"].as<float>();
          if (isfinite(risk) && risk >= 0 && risk <= 1) { advisoryRisk = risk; riskAt = millis(); }
        }
      }
    }
    http.end();
    if (status_code >= 200 && status_code < 300) {
      lastSuccess = millis(); holding = false; retryMs = 1000; acknowledgeLocalDecision();
    } else if (status_code == 400 || status_code == 409 || status_code == 422) {
      dropped++; holding = false; Serial.printf("{\"event\":\"telemetry_rejected\",\"http\":%d,\"dropped\":%lu}\n", status_code, (unsigned long)dropped);
    } else {
      JsonDocument doc; deserializeJson(doc, packet.json); doc["buffered"] = true; serializeJson(doc, packet.json, sizeof(packet.json));
      Serial.printf("{\"event\":\"backend_retry\",\"http\":%d,\"queued\":%u}\n", status_code, uxQueueMessagesWaiting(queue));
      vTaskDelay(pdMS_TO_TICKS(retryMs)); retryMs = min(retryMs * 2, uint32_t(10000));
    }
  }
}
void networkBegin(){
  snprintf(bootID,sizeof(bootID),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
  queue=xQueueCreate(8,sizeof(Packet));
  if(queue){
    xTaskCreatePinnedToCore(worker,"telemetry",16384,nullptr,1,nullptr,0);
  }
}
void networkEnqueue(const SensorData& s,const coldchain::Output& o,uint32_t now,const char* injection){
  if(!queue)return;
  time_t nowTime=time(nullptr);
  if(nowTime<=1700000000){return;}
  struct tm utcTime;gmtime_r(&nowTime,&utcTime);char timestamp[32];strftime(timestamp,sizeof(timestamp),"%Y-%m-%dT%H:%M:%SZ",&utcTime);
  JsonDocument j;j["schema_version"]="1.0";j["device_id"]=DEVICE_ID;j["boot_id"]=bootID;j["sequence"]=(uint32_t)(++sequence);
  j["timestamp"]=timestamp;j["uptime_ms"]=now;j["mode"]="HARDWARE";
  auto number=[&](const char* key,float value,bool valid){if(valid&&isfinite(value))j[key]=value;else j[key]=nullptr;};
  number("chamber_temp_c",s.chamber,s.chamberOK);number("heatsink_temp_c",s.heatsink,s.heatsinkOK);
  number("sht31_temp_c",s.shtTemp,s.shtOK);number("humidity_pct",s.humidity,s.shtOK);number("primary_current_a",s.current,s.currentOK);
  if(s.doorOK)j["door_open"]=s.doorOpen;else j["door_open"]=nullptr;
  j["door_open_s"]=s.doorOK&&s.doorOpen?s.doorSeconds:0;
  auto gps=j["gps"].to<JsonObject>();gps["fix"]=s.gpsFix;gps["source"]=s.gpsFix?"GPS":"NONE";
  if(s.gpsFix){gps["latitude"]=s.latitude;gps["longitude"]=s.longitude;gps["age_s"]=s.gpsAge;
    if(isfinite(s.speed))gps["speed_kmph"]=s.speed;else gps["speed_kmph"]=nullptr;
  }else{gps["latitude"]=nullptr;gps["longitude"]=nullptr;gps["speed_kmph"]=nullptr;gps["age_s"]=nullptr;}
  gps["satellites"]=s.satellites;
  j["primary_cooling"]=primaryObserved();j["backup_cooling"]=backupObserved();j["system_state"]=coldchain::name(o.state);
  auto health=j["sensor_health"].to<JsonObject>();health["chamber"]=s.chamberOK;health["heatsink"]=s.heatsinkOK;
  health["sht31"]=s.shtOK;health["current"]=s.currentOK;health["door"]=s.doorOK;
  j["fault_injection"]=injection;j["buffered"]=WiFi.status()!=WL_CONNECTED;
  Packet packet;
  if(measureJson(j)>=sizeof(packet.json)){dropped++;return;}
  serializeJson(j,packet.json,sizeof(packet.json));
  if(xQueueSend(queue,&packet,0)!=pdTRUE){Packet old;xQueueReceive(queue,&old,0);dropped++;xQueueSend(queue,&packet,0);}

  char chStr[16], hsStr[16], shtStr[16], humStr[16], curStr[24], doorStr[24], gpsStr[16];
  if (s.chamberOK) snprintf(chStr, sizeof(chStr), "%.2f C", s.chamber); else snprintf(chStr, sizeof(chStr), "null");
  if (s.heatsinkOK) snprintf(hsStr, sizeof(hsStr), "%.2f C", s.heatsink); else snprintf(hsStr, sizeof(hsStr), "null");
  if (s.shtOK) {
    snprintf(shtStr, sizeof(shtStr), "%.2f C", s.shtTemp);
    snprintf(humStr, sizeof(humStr), "%.1f %%", s.humidity);
  } else {
    snprintf(shtStr, sizeof(shtStr), "null");
    snprintf(humStr, sizeof(humStr), "null");
  }
  if (s.currentOK) snprintf(curStr, sizeof(curStr), "%.2f A", s.current); else snprintf(curStr, sizeof(curStr), "UNCALIBRATED");
  if (s.doorOK) {
    if (s.doorOpen) snprintf(doorStr, sizeof(doorStr), "OPEN (%.1fs)", s.doorSeconds);
    else snprintf(doorStr, sizeof(doorStr), "CLOSED");
  } else {
    snprintf(doorStr, sizeof(doorStr), "UNKNOWN");
  }
  snprintf(gpsStr, sizeof(gpsStr), s.gpsFix ? "FIX" : "NO_FIX");

  Serial.printf("[SAMPLE] seq=%lu chamber=%s heatsink=%s sht31=%s humidity=%s door=%s vib=%s gps=%s sats=%lu current=%s\n",
                (unsigned long)sequence, chStr, hsStr, shtStr, humStr, doorStr,
                s.vibrationDetected ? "DETECTED" : "NORMAL", gpsStr, (unsigned long)s.satellites, curStr);
}
bool networkHealthy(){return lastSuccess>0&&millis()-lastSuccess<20000;}
float networkAdvisoryRisk(){return riskAt>0&&millis()-riskAt<20000?advisoryRisk.load():NAN;}
