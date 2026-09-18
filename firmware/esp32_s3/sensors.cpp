#include "sensors.h"
#include "config.h"
#include <Wire.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Adafruit_SHT31.h>
#include <TinyGPSPlus.h>
#include <sys/time.h>
static OneWire* bus=nullptr;
static DallasTemperature* probes=nullptr;
static Adafruit_SHT31 sht;
static TinyGPSPlus gps;
static HardwareSerial gpsSerial(1);
static SensorData data;
static bool shtReady=false,conversion=false,reedCandidate=false;
static uint32_t conversionAt=0,lastSensors=0,lastProbe=0,lastCurrent=0,reedAt=0,doorAt=0;
static float temps[61];static uint32_t times[61];static size_t count=0;
static bool validTemp(float x){return isfinite(x)&&x>=-55&&x<=125&&x!=-127&&x!=85;}

void sensorsBegin(){
  if(PIN_ONEWIRE>=0){
    bus=new OneWire(PIN_ONEWIRE);probes=new DallasTemperature(bus);probes->begin();
    probes->setResolution(12);probes->setWaitForConversion(false);
    DeviceAddress address;
    for(int i=0;i<probes->getDeviceCount();i++)if(probes->getAddress(address,i)){
      Serial.print("{\"event\":\"probe_rom\",\"rom\":\"");
      for(uint8_t b:address)Serial.printf("%02X",b);
      Serial.println("\"}");
    }
  }
  if(PIN_SDA>=0&&PIN_SCL>=0){Wire.begin(PIN_SDA,PIN_SCL);Wire.setTimeOut(40);shtReady=sht.begin(SHT31_ADDRESS);}
  if(PIN_REED>=0){pinMode(PIN_REED,INPUT_PULLUP);data.doorOK=true;reedCandidate=digitalRead(PIN_REED)==HIGH;data.doorOpen=reedCandidate;}
  if(PIN_CURRENT>=0){analogReadResolution(12);analogSetPinAttenuation(PIN_CURRENT,ADC_11db);}
  if(PIN_GPS_RX>=0&&PIN_GPS_TX>=0)gpsSerial.begin(9600,SERIAL_8N1,PIN_GPS_RX,PIN_GPS_TX);
}
void sensorsTick(uint32_t now){
  if(PIN_GPS_RX>=0){for(int n=0;n<128&&gpsSerial.available();n++)gps.encode(gpsSerial.read());}
  if(time(nullptr)<1704067200&&gps.date.isValid()&&gps.time.isValid()&&gps.date.age()<30000&&gps.time.age()<30000&&gps.date.year()>=2024){
    struct tm stamp={};stamp.tm_year=gps.date.year()-1900;stamp.tm_mon=gps.date.month()-1;stamp.tm_mday=gps.date.day();
    stamp.tm_hour=gps.time.hour();stamp.tm_min=gps.time.minute();stamp.tm_sec=gps.time.second();
    setenv("TZ","UTC0",1);tzset();timeval tv={mktime(&stamp),0};settimeofday(&tv,nullptr);
  }
  if(data.doorOK){
    bool raw=digitalRead(PIN_REED)==HIGH;
    if(raw!=reedCandidate){reedCandidate=raw;reedAt=now;}
    if(now-reedAt>=DOOR_DEBOUNCE_MS&&data.doorOpen!=raw){data.doorOpen=raw;doorAt=now;}
    data.doorSeconds=data.doorOpen?(now-doorAt)/1000.0f:0;
  }
  if(PIN_CURRENT>=0&&now-lastCurrent>=20){
    lastCurrent=now;uint32_t mv=analogReadMilliVolts(PIN_CURRENT);
    data.currentAdcMv=mv;
    // ADC rail values indicate bad conditioning or disconnection, never "zero current".
    data.currentOK=CURRENT_CALIBRATED&&CURRENT_MV_PER_AMP>0&&mv>20&&mv<3000;
    float amps=CURRENT_MV_PER_AMP>0?fabsf((float(mv)-CURRENT_ZERO_MV)/CURRENT_MV_PER_AMP):NAN;
    data.currentOK=data.currentOK&&isfinite(amps)&&amps<=20;
    if(data.currentOK)data.current=isfinite(data.current)?(.25f*amps+.75f*data.current):amps;
    else data.current=NAN;
  }
  if(probes&&conversion&&now-conversionAt>=800){
    data.chamber=probes->getTempC(CHAMBER_ROM);data.heatsink=probes->getTempC(HEATSINK_ROM);
    data.chamberOK=validTemp(data.chamber);data.heatsinkOK=validTemp(data.heatsink);
    if(!data.chamberOK)data.chamber=NAN;if(!data.heatsinkOK)data.heatsink=NAN;
    lastProbe=now;conversion=false;
    if(data.chamberOK){
      if(count==61){for(size_t i=1;i<count;i++){temps[i-1]=temps[i];times[i-1]=times[i];}count--;}
      temps[count]=data.chamber;times[count]=now;count++;
      while(count>1&&now-times[0]>60000){for(size_t i=1;i<count;i++){temps[i-1]=temps[i];times[i-1]=times[i];}count--;}
      data.rate=count>1&&now!=times[0]?(data.chamber-temps[0])*60000.0f/(now-times[0]):0;
    }
  }
  if(now-lastSensors>=SENSOR_MS){
    lastSensors=now;
    if(probes&&!conversion){probes->requestTemperatures();conversion=true;conversionAt=now;}
    if(shtReady){data.shtTemp=sht.readTemperature();data.humidity=sht.readHumidity();
      data.shtOK=isfinite(data.shtTemp)&&data.shtTemp>=-40&&data.shtTemp<=125&&isfinite(data.humidity)&&data.humidity>=0&&data.humidity<=100;
      if(!data.shtOK){data.shtTemp=NAN;data.humidity=NAN;}}
  }
}
SensorData sensorSnapshot(uint32_t now){
  SensorData result=data;
  if(now-lastProbe>SENSOR_TIMEOUT_MS){result.chamberOK=false;result.heatsinkOK=false;result.chamber=NAN;result.heatsink=NAN;}
  if(now-lastCurrent>500){result.currentOK=false;result.current=NAN;}
  result.gpsFix=gps.location.isValid()&&gps.location.age()<=GPS_MAX_AGE_MS;
  if(result.gpsFix){result.latitude=gps.location.lat();result.longitude=gps.location.lng();
    result.speed=gps.speed.isValid()&&gps.speed.age()<GPS_MAX_AGE_MS?gps.speed.kmph():NAN;
    result.gpsAge=gps.location.age()/1000.0f;result.satellites=gps.satellites.isValid()?gps.satellites.value():0;}
  return result;
}
