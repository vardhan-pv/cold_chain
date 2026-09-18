#include "display.h"
#include "config.h"
#include "cooling.h"
#include <WiFi.h>
#include <Adafruit_SSD1306.h>
static Adafruit_SSD1306 oled(128,64,&Wire,-1);
static bool oledReady=false;
static void set(int pin,bool on){if(pin>=0)digitalWrite(pin,on?HIGH:LOW);}
void displayBegin(){
  for(int p:{PIN_GREEN,PIN_YELLOW,PIN_RED,PIN_BUZZER})if(p>=0){digitalWrite(p,LOW);pinMode(p,OUTPUT);}
  if(OPTIONAL_OLED&&PIN_SDA>=0&&PIN_SCL>=0)oledReady=oled.begin(SSD1306_SWITCHCAPVCC,0x3C);
}
void displayTick(const SensorData& data,const coldchain::Output& output,bool backendOK,uint32_t now){
  set(PIN_GREEN,output.state==coldchain::State::NORMAL&&coolingConfigured());
  set(PIN_YELLOW,output.state!=coldchain::State::NORMAL&&!output.alarm);
  set(PIN_RED,output.alarm);set(PIN_BUZZER,output.alarm&&(now%1000<500));
  if(oledReady){oled.clearDisplay();oled.setTextSize(1);oled.setTextColor(SSD1306_WHITE);oled.setCursor(0,0);
    oled.printf("HARDWARE / PENDING\nT:%.1fC RH:%.0f%%\nP:%s B:%s\n%s\nWiFi:%s API:%s",data.chamber,data.humidity,
      output.primary?"ON":"OFF",output.backup?"ON":"OFF",coldchain::name(output.state),
      WiFi.status()==WL_CONNECTED?"OK":"OFF",backendOK?"OK":"OFF");oled.display();}
}
