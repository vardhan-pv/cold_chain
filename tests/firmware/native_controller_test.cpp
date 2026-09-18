#include "../../firmware/esp32_s3/control_core.h"
#include <cassert>
#include <iostream>
#include <sstream>
#include <string>
using namespace coldchain;
int main(int argc,char**){
  if(argc>1){
    std::string line;Controller c;
    while(std::getline(std::cin,line)){
      if(line=="RESET"){c.reset();continue;}
      Reading r;uint32_t ms;int valid,secondary,doorValid,door,p,b;
      std::istringstream s(line);
      s>>ms>>r.chamber>>r.heatsink>>r.current>>r.rate>>r.doorSeconds>>valid>>secondary>>doorValid>>door>>p>>b;
      s>>r.advisoryRisk;
      r.criticalValid=valid;r.secondaryValid=secondary;r.doorValid=doorValid;r.doorOpen=door;r.primaryObserved=p;r.backupObserved=b;
      auto o=c.update(r,ms);assert(!(o.primary&&o.backup));
      std::cout<<name(o.state)<<","<<o.primary<<","<<o.backup<<"\n";
    }
    return 0;
  }
  Reading r;r.chamber=9;r.heatsink=35;r.current=0;r.criticalValid=true;r.secondaryValid=true;r.doorValid=true;
  Controller c;auto o=c.update(r,1000);assert(o.primary&&!o.backup);
  r.heatsink=70;o=c.update(r,1050);assert(o.alarm&&!o.primary&&!o.backup);
  r.heatsink=35;o=c.update(r,1100);assert(o.state==State::REROUTING&&!o.primary&&!o.backup);
  c.reset();r.current=4;r.primaryObserved=false;o=c.update(r,1200);assert(o.alarm&&!o.backup);
  c.reset();r.current=0;r.chamber=9;r.primaryObserved=true;
  for(uint32_t ms=0;ms<=25000;ms+=1000)o=c.update(r,ms);
  assert(o.state==State::PRIMARY_FAULT&&!o.primary&&!o.backup);
  r.primaryObserved=false;c.update(r,26000);o=c.update(r,27000);assert(!o.backup);
  o=c.update(r,28000);assert(o.backup&&!o.primary);
  // Unsigned subtraction protects timing across millis() rollover.
  c.reset();r.primaryObserved=true;
  for(uint32_t n=0;n<=25;n++)o=c.update(r,0xfffff000u+n*1000u);
  assert(o.state==State::PRIMARY_FAULT);
  c.reset();r.primaryObserved=false;r.current=0;r.advisoryRisk=.95f;
  o=c.update(r,1000);assert(o.state==State::WARNING&&o.primary&&!o.backup);
  r.advisoryRisk=NAN;o=c.update(r,2000);assert(o.state==State::NORMAL);
  std::cout<<"Native controller assertions passed, including timer rollover.\n";
}
