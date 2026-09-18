#include "network.h"
#include "config.h"
#include "cooling.h"
#include <WiFi.h>
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
  if(url.startsWith("https://")&&strlen(ROOT_CA)>0){secure.setCACert(ROOT_CA);ready=http.begin(secure,url);}
  else if(ALLOW_LAB_HTTP&&url.startsWith("http://"))ready=http.begin(plain,url);
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
static void worker(void*){
  WiFi.mode(WIFI_STA);
  if(strlen(WIFI_SSID))WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  configTime(0,0,"pool.ntp.org","time.nist.gov");
  uint32_t reconnectAt=0,retryMs=1000;
  Packet packet;bool holding=false;
  for(;;){
    if(WiFi.status()!=WL_CONNECTED){
      if(millis()-reconnectAt>=10000){reconnectAt=millis();if(strlen(WIFI_SSID))WiFi.reconnect();}
      vTaskDelay(pdMS_TO_TICKS(100));continue;
    }
    if(!holding)holding=xQueueReceive(queue,&packet,pdMS_TO_TICKS(100))==pdTRUE;
    if(!holding)continue;
    HTTPClient http;WiFiClient plain;WiFiClientSecure secure;
    bool configured=false;
    if(strncmp(BACKEND_URL,"https://",8)==0&&strlen(ROOT_CA)>0){secure.setCACert(ROOT_CA);configured=http.begin(secure,BACKEND_URL);}
    else if(ALLOW_LAB_HTTP&&strncmp(BACKEND_URL,"http://",7)==0)configured=http.begin(plain,BACKEND_URL);
    int status=-1;
    if(configured&&strlen(DEVICE_TOKEN)){
      http.setConnectTimeout(1500);http.setTimeout(1500);
      http.addHeader("Content-Type","application/json");http.addHeader("X-Device-Token",DEVICE_TOKEN);
      status=http.POST(reinterpret_cast<uint8_t*>(packet.json),strlen(packet.json));
      if(status>=200&&status<300){
        JsonDocument response;
        if(!deserializeJson(response,http.getString())&&!response["archived"].as<bool>()&&
            !response["prediction"]["ensemble_probability"].isNull()){
          float risk=response["prediction"]["ensemble_probability"].as<float>();
          if(isfinite(risk)&&risk>=0&&risk<=1){advisoryRisk=risk;riskAt=millis();}
        }
      }
    }
    http.end();
    if(status>=200&&status<300){lastSuccess=millis();holding=false;retryMs=1000;acknowledgeLocalDecision();}
    else if(status==400||status==409||status==422){
      // Invalid samples cannot head-of-line block all later telemetry.
      dropped++;holding=false;Serial.printf("{\"event\":\"telemetry_rejected\",\"http\":%d,\"dropped\":%lu}\n",status,(unsigned long)dropped);
    } else {
      JsonDocument doc;deserializeJson(doc,packet.json);doc["buffered"]=true;serializeJson(doc,packet.json,sizeof(packet.json));
      Serial.printf("{\"event\":\"backend_retry\",\"http\":%d,\"queued\":%u}\n",status,uxQueueMessagesWaiting(queue));
      vTaskDelay(pdMS_TO_TICKS(retryMs));retryMs=min(retryMs*2,uint32_t(10000));
    }
  }
}
void networkBegin(){
  snprintf(bootID,sizeof(bootID),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
  queue=xQueueCreate(24,sizeof(Packet));
  if(queue)xTaskCreatePinnedToCore(worker,"telemetry",8192,nullptr,1,nullptr,0);
}
void networkEnqueue(const SensorData& s,const coldchain::Output& o,uint32_t now,const char* injection){
  if(!queue)return;
  time_t nowTime=time(nullptr);
  if(nowTime<1704067200){Serial.println("{\"event\":\"clock_unsynchronized\",\"telemetry\":\"not_sent\"}");return;}
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
  Serial.printf("{\"event\":\"sample\",\"sequence\":%lu,\"state\":\"%s\",\"dropped\":%lu}\n",
      (unsigned long)sequence,coldchain::name(o.state),(unsigned long)dropped);
}
bool networkHealthy(){return lastSuccess>0&&millis()-lastSuccess<20000;}
float networkAdvisoryRisk(){return riskAt>0&&millis()-riskAt<20000?advisoryRisk.load():NAN;}
