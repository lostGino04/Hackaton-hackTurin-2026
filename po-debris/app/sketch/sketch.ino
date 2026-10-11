// PO-DEBRIS peripheral application. Does not change the Zephyr base or bootloader.
// RPC callbacks exchange cached values only; all I2C stays in a separate thread.
#include <Arduino_RouterBridge.h>
#include <Arduino_Modulino.h>
#include <Wire.h>
#include <Servo.h>
#include <U8g2lib.h>
#include <zephyr/kernel.h>
#include <zephyr/drivers/counter.h>
#include <math.h>

K_MUTEX_DEFINE(stateMutex);
K_THREAD_STACK_DEFINE(i2cStack, 8192);
struct k_thread i2cThread;
ModulinoDistance distanceSensor;
Servo servo1, servo2;
U8G2_SSD1306_128X64_NONAME_F_HW_I2C ssd(U8G2_R0,U8X8_PIN_NONE);
U8G2_SH1106_128X64_NONAME_F_HW_I2C sh1106(U8G2_R0,U8X8_PIN_NONE);
U8G2* oled=nullptr;
TwoWire* oledWire=&Wire;

bool servoEnabled=false, servoBusy=false, requestCycle=false;
int home1=90,active1=95,home2=90,active2=95,holdMs=450;
uint32_t cooldownMs=10000,lastCycle=0,servoDeadline=0;
int requestedServo=3,servoPhase=0,cycleSelection=3;
String lastEvent="",displayMode="WAITING",displayLabel="",oledKind="unknown";
int displayConfidence=0,displayCount=0,oledBus=0,oledAddress=0x3c;
bool displayDirty=true,oledReconfigure=true,scanRequested=true,oledOnline=false;
bool tofOnline=false,tofValid=false;
int tofMm=-1,tofBus=-1,tofModelId=-1;
uint32_t tofUpdated=0,i2cHeartbeat=0,d2High=0,d2Low=0,d2Edges=0;
uint32_t tofSampled=0;
uint8_t tofInitAttempts=0;
bool d2Value=false;
String scanResult="{}",tofModel="not identified",oledError="controller not identified";

String ok(){return "{\"ok\":true}";}
String fail(const char* message){return String("{\"ok\":false,\"error\":\"")+message+"\"}";}
void lockState(){k_mutex_lock(&stateMutex,K_FOREVER);}
void unlockState(){k_mutex_unlock(&stateMutex);}

bool ping(TwoWire& wire,int address){wire.beginTransmission(address);return wire.endTransmission()==0;}
bool readRegister(TwoWire& wire,uint16_t reg,uint8_t* buffer,int length){
  wire.beginTransmission(0x29);wire.write(uint8_t(reg>>8));wire.write(uint8_t(reg));
  if(wire.endTransmission(false)!=0)return false;
  if(wire.requestFrom(uint8_t(0x29),size_t(length))!=size_t(length))return false;
  for(int i=0;i<length;i++)buffer[i]=wire.read();
  return true;
}

uint8_t oledByte(u8x8_t* screen,uint8_t msg,uint8_t count,void* data){
  switch(msg){
    case U8X8_MSG_BYTE_INIT:return 1;
    case U8X8_MSG_BYTE_START_TRANSFER:oledWire->beginTransmission(u8x8_GetI2CAddress(screen)>>1);return 1;
    case U8X8_MSG_BYTE_SEND:return oledWire->write((uint8_t*)data,count)==count;
    case U8X8_MSG_BYTE_END_TRANSFER:return oledWire->endTransmission()==0;
    case U8X8_MSG_BYTE_SET_DC:return 1;
  }
  return 0;
}

String poStatus(){
  lockState();
  bool fresh=(millis()-i2cHeartbeat)<2000;
  String result="{\"protocol\":1,\"d2\":"+String(d2Value?1:0)+
    ",\"d2_high_samples\":"+String(d2High)+",\"d2_low_samples\":"+String(d2Low)+
    ",\"d2_rising_edges\":"+String(d2Edges)+",\"tof_online\":"+String(tofOnline&&fresh?"true":"false")+
    ",\"tof_valid\":"+String(tofValid&&fresh&&(millis()-tofUpdated)<1500?"true":"false")+
    ",\"tof_mm\":"+String(tofMm)+",\"tof_bus\":"+String(tofBus)+
    ",\"tof_model_id\":"+String(tofModelId)+",\"tof_model\":\""+tofModel+
    "\",\"i2c_worker_ok\":"+String(fresh?"true":"false")+
    ",\"oled_online\":"+String(oledOnline&&fresh?"true":"false")+
    ",\"oled_controller\":\""+oledKind+"\",\"oled_error\":\""+oledError+
    "\",\"servo_enabled\":"+String(servoEnabled?"true":"false")+
    ",\"servo_busy\":"+String(servoBusy||requestCycle?"true":"false")+
    ",\"count\":"+String(displayCount)+",\"scan\":"+scanResult+"}";
  unlockState();return result;
}

String poScan(){lockState();scanRequested=true;String result=String("{\"ok\":true,\"scan\":")+scanResult+"}";unlockState();return result;}
String poDisplay(String mode,String label,int confidence,int count){
  if(label.length()>24 || confidence<0 || confidence>100 || count<0)return fail("invalid display values");
  lockState();
  if(mode!=displayMode||label!=displayLabel||confidence!=displayConfidence||count!=displayCount){
    displayMode=mode;displayLabel=label;displayConfidence=confidence;displayCount=count;displayDirty=true;
  }
  unlockState();return ok();
}
String poOledTest(){return poDisplay("TEST","OLED TEST OK",100,displayCount);}
String poOledConfig(String kind,int bus,int address){
  if((bus!=0&&bus!=1)||(address!=0x3c&&address!=0x3d))return fail("invalid OLED bus/address");
  if(kind!="unknown"&&kind!="disabled"&&kind!="SSD1306"&&kind!="SSD1308"&&kind!="SSD1315"&&kind!="SH1106")return fail("unsupported OLED controller");
  lockState();oledKind=kind;oledBus=bus;oledAddress=address;oledReconfigure=true;unlockState();return ok();
}
String poServoConfig(int h1,int a1,int h2,int a2,int hold,int cooldown,bool enabled){
  if(h1<20||h1>160||h2<20||h2>160||a1<20||a1>160||a2<20||a2>160||abs(h1-a1)>20||abs(h2-a2)>20||hold<250||hold>1500||cooldown<3000||cooldown>120000)return fail("unsafe servo parameters");
  lockState();
  if(servoBusy||requestCycle){unlockState();return fail("servo cycle active");}
  home1=h1;active1=a1;home2=h2;active2=a2;holdMs=hold;cooldownMs=cooldown;servoEnabled=enabled;
  unlockState();return ok();
}
String queueServo(int selection){
  lockState();
  if(!servoEnabled){unlockState();return fail("servo disabled");}
  if(servoBusy||requestCycle){unlockState();return fail("servo busy");}
  if(lastCycle!=0&&millis()-lastCycle<cooldownMs){unlockState();return fail("cooldown");}
  requestedServo=selection;requestCycle=true;unlockState();return ok();
}
String poServoTest(int selection){if(selection<1||selection>3)return fail("select servo 1, 2 or sequential cycle 3");return queueServo(selection);}
String poEvent(String id,String label,int confidence,int count){
  if(id.length()>48||label.length()>24||count<1||confidence<0||confidence>100)return fail("invalid event");
  lockState();
  if(id==lastEvent){unlockState();return ok();} // Idempotent even after a lost RPC response.
  if(servoBusy||requestCycle||(lastCycle!=0&&millis()-lastCycle<cooldownMs)){unlockState();return fail("busy or cooldown");}
  lastEvent=id;displayMode="DETECTION";displayLabel=label;displayConfidence=confidence;displayCount=count;displayDirty=true;
  if(servoEnabled){requestedServo=3;requestCycle=true;}
  unlockState();return ok();
}

void scanBuses(){
  String result="{\"Wire\":[";
  for(int bus=0;bus<2;bus++){
    TwoWire& wire=bus==0?Wire:Wire1;bool first=true;
    for(int address=8;address<120;address++)if(ping(wire,address)){
      if(!first)result+=",";result+=String(address);first=false;
    }
    result+=(bus==0?"],\"Wire1\":[":"]}");
  }
  lockState();scanResult=result;unlockState();
}

void identifyTof(){
  if(tofInitAttempts>=4)return;
  for(int bus=1;bus>=0;bus--){
    TwoWire& wire=bus==0?Wire:Wire1;
    if(!ping(wire,0x29))continue;
    uint8_t bytes[2];
    if(!readRegister(wire,0x010f,bytes,2))continue;
    int model=(int(bytes[0])<<8)|bytes[1];
    lockState();tofBus=bus;tofModelId=model;unlockState();
    if(model!=0xebaa){
      lockState();tofModel="unknown ToF: driver disabled";unlockState();continue;
    }
    lockState();tofModel="VL53L4CD/ED: Arduino_Modulino";unlockState();
    tofInitAttempts++;
    Modulino.begin(wire);
    bool ready=distanceSensor.begin();
    tofSampled=millis();
    lockState();tofOnline=ready;unlockState();
    if(ready)return;
  }
}

void configureOled(){
  lockState();String kind=oledKind;int bus=oledBus,address=oledAddress;oledOnline=false;unlockState();
  if(kind=="unknown"||kind=="disabled"){
    lockState();oledError="controller not identified: disabled";unlockState();oled=nullptr;return;
  }
  oledWire=bus==0?&Wire:&Wire1;
  if(!ping(*oledWire,address)){
    lockState();oledError="I2C display not responding";unlockState();oled=nullptr;return;
  }
  oled=kind=="SH1106"?(U8G2*)&sh1106:(U8G2*)&ssd;
  oled->getU8x8()->byte_cb=oledByte;
  oled->setI2CAddress(address<<1);oled->begin();oled->setFont(u8g2_font_6x10_tf);
  lockState();oledOnline=true;oledError="";displayDirty=true;unlockState();
}

void refreshOled(){
  lockState();String mode=displayMode,label=displayLabel;int confidence=displayConfidence,count=displayCount;unlockState();
  if(oled==nullptr)return;
  if(!ping(*oledWire,oledAddress)){
    lockState();oledOnline=false;oledError="display disconnected";unlockState();return;
  }
  oled->clearBuffer();
  if(mode=="DETECTION"){
    label.toUpperCase();char line[24];oled->drawStr(0,12,"DEBRIS DETECTED");oled->drawStr(0,27,label.c_str());
    snprintf(line,sizeof(line),"CONF: %d%%",confidence);oled->drawStr(0,42,line);
    snprintf(line,sizeof(line),"COUNT: %03d",count);oled->drawStr(0,57,line);
  }else if(mode=="TEST"){
    oled->drawStr(0,14,"PO-DEBRIS AI");oled->drawStr(0,32,"OLED TEST OK");oled->drawStr(0,50,"SYSTEM READY");
  }else{
    oled->drawStr(0,14,"PO-DEBRIS AI");oled->drawStr(0,32,"SYSTEM READY");oled->drawStr(0,50,"WAITING...");
  }
  oled->sendBuffer();
}

void i2cLoop(void*,void*,void*){
  Wire.begin();Wire.setClock(100000);Wire1.begin();Wire1.setClock(100000);
  scanBuses();identifyTof();
  uint32_t lastRetry=millis();
  while(true){
    lockState();i2cHeartbeat=millis();bool scan=scanRequested,configure=oledReconfigure,dirty=displayDirty;
    scanRequested=false;oledReconfigure=false;displayDirty=false;bool online=tofOnline;int bus=tofBus;unlockState();
    if(scan)scanBuses();
    if(configure)configureOled();
    if(online){
      TwoWire& wire=bus==0?Wire:Wire1;uint8_t mux=0,status=0;
      bool ready=readRegister(wire,0x0030,&mux,1)&&readRegister(wire,0x0031,&status,1)&&
        ((status&1)==((mux&0x10)?0:1));
      if(ready){
        bool valid=distanceSensor.available();
        float value=distanceSensor.get();
        lockState();tofValid=valid&&isfinite(value)&&value>0&&value<=1200;tofMm=tofValid?int(value):-1;tofUpdated=millis();unlockState();
        tofSampled=millis();
      }
      if(millis()-tofSampled>3000){lockState();tofOnline=false;tofValid=false;unlockState();}
    }
    if(dirty)refreshOled();
    if(millis()-lastRetry>5000){
      lastRetry=millis();
      lockState();bool retry=!oledOnline&&oledKind!="unknown"&&oledKind!="disabled";unlockState();
      if(retry)configureOled();
      lockState();bool tofRetry=!tofOnline;unlockState();
      if(tofRetry)identifyTof();
    }
    k_msleep(50);
  }
}

void servoLoop(){
  lockState();
  if(requestCycle&&!servoBusy){
    requestCycle=false;servoBusy=true;cycleSelection=requestedServo;lastCycle=millis();
    servoPhase=cycleSelection==2?4:1;servoDeadline=millis();
  }
  if(!servoBusy||int32_t(millis()-servoDeadline)<0){unlockState();return;}
  switch(servoPhase){
    case 1:servo1.attach(9,1000,2000);servo1.write(home1);counter_start(DEVICE_DT_GET(DT_NODELABEL(counter_servo)));servoPhase=2;servoDeadline=millis()+holdMs;break;
    case 2:servo1.write(active1);servoPhase=3;servoDeadline=millis()+holdMs;break;
    case 3:servo1.write(home1);servoPhase=7;servoDeadline=millis()+holdMs;break;
    case 7:servo1.detach();counter_stop(DEVICE_DT_GET(DT_NODELABEL(counter_servo)));digitalWrite(9,LOW);servoPhase=cycleSelection==1?8:4;servoDeadline=millis()+200;break;
    case 4:servo2.attach(10,1000,2000);servo2.write(home2);counter_start(DEVICE_DT_GET(DT_NODELABEL(counter_servo)));servoPhase=5;servoDeadline=millis()+holdMs;break;
    case 5:servo2.write(active2);servoPhase=6;servoDeadline=millis()+holdMs;break;
    case 6:servo2.write(home2);servoPhase=9;servoDeadline=millis()+holdMs;break;
    case 9:servo2.detach();counter_stop(DEVICE_DT_GET(DT_NODELABEL(counter_servo)));digitalWrite(10,LOW);servoPhase=8;servoDeadline=millis()+200;break;
    case 8:servoBusy=false;servoPhase=0;break;
  }
  unlockState();
}

void setup(){
  // The official Servo library starts its counter in global constructors.
  // Keep that timer stopped in standby and between the two separate movements.
  counter_stop(DEVICE_DT_GET(DT_NODELABEL(counter_servo)));
  pinMode(2,INPUT);pinMode(9,OUTPUT);pinMode(10,OUTPUT);digitalWrite(9,LOW);digitalWrite(10,LOW);
  Bridge.begin();
  Bridge.provide("po_status",poStatus);Bridge.provide("po_scan",poScan);
  Bridge.provide("po_display",poDisplay);Bridge.provide("po_oled_test",poOledTest);
  Bridge.provide("po_oled_config",poOledConfig);Bridge.provide("po_servo_config",poServoConfig);
  Bridge.provide("po_servo_test",poServoTest);Bridge.provide("po_event",poEvent);
  k_thread_create(&i2cThread,i2cStack,K_THREAD_STACK_SIZEOF(i2cStack),i2cLoop,nullptr,nullptr,nullptr,8,0,K_NO_WAIT);
}

void loop(){
  bool value=digitalRead(2)==HIGH;
  lockState();if(value)d2High++;else d2Low++;if(value&&!d2Value)d2Edges++;d2Value=value;unlockState();
  servoLoop();k_msleep(10); // Yield the MCU; no long delays and no camera work here.
}
