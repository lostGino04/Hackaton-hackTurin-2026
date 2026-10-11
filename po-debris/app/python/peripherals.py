"""Nonblocking peripheral coordinator; MCU I/O stays behind RouterBridge.

One control thread owns all RPC calls. Camera and NCNN never wait for I/O.
One detection per continuous presence episode; no claim of tracking unique objects.
"""
import json
import math
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from queue import Empty,Full,Queue

CLASSES={'bottle','grass','branch','milk-box','plastic-bag','plastic-garbage','ball','leaf'}

def overlap(a,b):
    x=max(0,min(a[2],b[2])-max(a[0],b[0]));y=max(0,min(a[3],b[3])-max(a[1],b[1]))
    intersection=x*y
    return intersection/max(1,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection)

class Peripherals:
    def __init__(self,root,gate,bridge=None,clock=time.monotonic):
        self.root=Path(root);self.gate=gate;self.clock=clock;self.bridge=bridge
        self.config=json.loads((self.root/'config/peripherals.json').read_text())
        self.lock=threading.Lock();self.stopping=threading.Event()
        self.results=Queue(maxsize=1);self.commands=Queue(maxsize=8)
        self.state='IDLE';self.count=0;self.session=uuid.uuid4().hex[:12]
        self.previous=None;self.streak=0;self.presence=False;self.empty=0
        self.last_frame=-1;self.last_event=None;self.deadline=0
        self.last_cycle=-math.inf;self.started=self.clock();self.next_periodic=self.started
        self.pir=False;self.tof_near=False;self.tof_near_samples=0
        self.online=False;self.hardware={};self.error=None;self.last_trigger=None
        self.configured=False;self.next_poll=0;self.next_connect=0;self.last_poll=0
        self.action_started=0
        self.transitions=deque(maxlen=20);self.pending_event=None
        self.test_queue=deque();self.last_oled=None;self.oled_hold_until=0
        self.thread=threading.Thread(target=self.run,name='Peripherals.RouterBridge',daemon=True)
        self.events_file=self.root/'data/peripheral-events.jsonl'
        self.events_file.parent.mkdir(exist_ok=True)

    def start(self):self.thread.start()
    def stop(self):
        self.stopping.set();self.thread.join(timeout=3)

    def snapshot(self):
        with self.lock:
            return dict(state=self.state,count=self.count,bridge_online=self.online,
                hardware=dict(self.hardware),error=self.error,last_trigger=self.last_trigger,
                last_event=self.last_event,config=dict(self.config),transitions=list(self.transitions))

    def submit(self,found,frame,latency):
        item=(found,frame,latency,self.clock())
        try:self.results.put_nowait(item)
        except Full:
            try:self.results.get_nowait()
            except Empty:pass
            try:self.results.put_nowait(item)
            except Full:pass

    def test(self,values):
        action=values.get('action')
        if action not in ('trigger','oled','servo1','servo2','cycle','scan'):
            raise ValueError('Azione valida: trigger, oled, servo1, servo2, cycle, scan')
        if set(values)-{'action'}:raise ValueError('Parametri test sconosciuti')
        if action in ('servo1','servo2','cycle') and not self.config['servo_enabled']:
            raise ValueError('Servo disabilitati: verificare alimentazione e configurare servo_enabled')
        done=threading.Event();reply={}
        try:self.commands.put_nowait((action,done,reply))
        except Full:raise ValueError('Coda comandi piena')
        if not done.wait(2):raise ValueError('Comando non eseguito entro il timeout; verificare stato prima di riprovare')
        if 'error' in reply:raise ValueError(reply['error'])
        return reply

    def configure(self,values):
        allowed=set(self.config)
        if not values or set(values)-allowed:raise ValueError('Configurazione periferiche non valida')
        updated=dict(self.config,**values)
        for name in ('event_confidence','periodic_seconds','inference_window_seconds','cooldown_seconds','pir_warmup_seconds'):
            value=updated[name]
            if type(value) not in (float,int) or not math.isfinite(value):raise ValueError(name)
        if not 0<updated['event_confidence']<=1:raise ValueError('Confidence non valida')
        if not 2<=updated['periodic_seconds']<=60 or not 3<=updated['inference_window_seconds']<=30:raise ValueError('Intervalli non validi')
        if not 3<=updated['cooldown_seconds']<=120 or not 0<=updated['pir_warmup_seconds']<=120:raise ValueError('Cooldown/warmup non validi')
        for name,low,high in [('consecutive_detections',2,5),('rearm_empty_frames',2,10),('servo_hold_ms',250,1500),('tof_trigger_mm',50,1000),('tof_release_mm',100,1200)]:
            if type(updated[name]) is not int or not low<=updated[name]<=high:raise ValueError(name)
        if updated['tof_release_mm']<=updated['tof_trigger_mm']:raise ValueError('Isteresi ToF non valida')
        for name in ('servo_home_1','servo_active_1','servo_home_2','servo_active_2'):
            if type(updated[name]) is not int or not 20<=updated[name]<=160:raise ValueError(name)
        if any(abs(updated[f'servo_active_{i}']-updated[f'servo_home_{i}'])>20 for i in (1,2)):
            raise ValueError('Escursione massima della demo: 20 gradi')
        if type(updated['servo_enabled']) is not bool:raise ValueError('servo_enabled')
        if updated['oled_controller'] not in ('unknown','disabled','SSD1306','SSD1308','SSD1315','SH1106'):
            raise ValueError('Controller OLED non supportato: non selezionarlo senza identificazione')
        if type(updated['oled_bus']) is not int or updated['oled_bus'] not in (0,1):raise ValueError('oled_bus')
        if type(updated['oled_address']) is not int or updated['oled_address'] not in (0x3c,0x3d):raise ValueError('oled_address')
        # Apply in the same RPC owner thread; no hardware call from the HTTP thread.
        with self.lock:
            self.config=updated;self.configured=False
        path=self.root/'config/peripherals.json'
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(updated,indent=2));tmp.replace(path)
        return dict(ok=True,config=updated)

    def transition(self,state):
        if self.state!=state:
            self.state=state;self.transitions.append(dict(state=state,time=self.clock()))

    def trigger(self,reason):
        if self.state not in ('IDLE','INFERENCE'):return False
        self.last_trigger=reason;self.transition('TRIGGER')
        self.previous=None;self.streak=0
        self.deadline=self.clock()+self.config['inference_window_seconds']
        self.gate.set();self.transition('INFERENCE')
        return True

    def call(self,name,*args):
        result=self.bridge.call(name,*args,timeout=1)
        return json.loads(result) if isinstance(result,str) and result.startswith('{') else result

    def configure_hardware(self):
        c=self.config
        reply=self.call('po_servo_config',c['servo_home_1'],c['servo_active_1'],c['servo_home_2'],c['servo_active_2'],c['servo_hold_ms'],int(c['cooldown_seconds']*1000),c['servo_enabled'])
        if not reply.get('ok'):raise RuntimeError(reply.get('error','Configurazione servo non applicata'))
        reply=self.call('po_oled_config',c['oled_controller'],c['oled_bus'],c['oled_address'])
        if not reply.get('ok'):raise RuntimeError(reply.get('error','Configurazione OLED non applicata'))
        self.configured=True;self.last_oled=None

    def handle_result(self,item):
        found,frame,latency,stamp=item
        if frame<=self.last_frame:return
        self.last_frame=frame
        valid=[d for d in found if d['class'] in CLASSES and d['confidence']>=self.config['event_confidence']]
        if not valid:
            self.empty+=1;self.previous=None;self.streak=0
            if self.empty>=self.config['rearm_empty_frames']:self.presence=False
            return
        self.empty=0
        if self.state!='INFERENCE' or self.presence:return
        maximum_gap=max(2.5,latency/1000*3)
        coherent=[] if self.previous is None or stamp-self.previous[1]>maximum_gap else [
            d for d in valid if d['class']==self.previous[0]['class'] and overlap(d['xyxy'],self.previous[0]['xyxy'])>=.15]
        candidate=max(coherent or valid,key=lambda d:d['confidence'])
        self.streak=self.streak+1 if coherent else 1
        self.previous=(candidate,stamp)
        if self.streak<self.config['consecutive_detections']:return
        self.presence=True;self.count+=1;self.last_cycle=self.clock()
        self.last_event=dict(id=f'{self.session}-{self.count}',count=self.count,**candidate)
        with self.events_file.open('a',encoding='utf8') as stream:
            stream.write(json.dumps(dict(time=time.time(),**self.last_event))+'\n')
        self.pending_event=self.last_event
        self.transition('DETECTION');self.gate.clear()
        self.deadline=self.clock()+2

    def process_command(self,action):
        if action=='trigger':return dict(ok=self.trigger('manual'))
        if not self.online:raise RuntimeError('STM32/RouterBridge non disponibile')
        if action=='scan':return self.call('po_scan')
        if action=='oled':
            self.oled_hold_until=self.clock()+4
            return self.call('po_oled_test')
        if self.state not in ('IDLE','INFERENCE') or self.clock()-self.last_cycle<self.config['cooldown_seconds']:
            raise RuntimeError('Ciclo già attivo o cooldown in corso')
        number={'servo1':1,'servo2':2,'cycle':3}[action]
        reply=self.call('po_servo_test',number)
        if not reply.get('ok'):raise RuntimeError(reply.get('error','Servo non disponibile'))
        self.last_cycle=self.clock();self.transition('SERVO ACTION');self.gate.clear()
        self.action_started=self.clock()
        self.deadline=self.clock()+max(6,6*self.config['servo_hold_ms']/1000+1.5)
        return reply

    def step(self):
        now=self.clock()
        if now>=self.next_poll:
            self.next_poll=now+.20
            try:
                if self.bridge is None:
                    from arduino.app_utils import Bridge
                    self.bridge=Bridge
                hardware=self.call('po_status')
                if not isinstance(hardware,dict) or hardware.get('protocol')!=1:raise RuntimeError('Sketch PO-DEBRIS non disponibile')
                self.hardware=hardware;self.online=True;self.error=None;self.last_poll=now
                if not self.configured:self.configure_hardware()
                pir=bool(hardware.get('d2'))
                if pir and not self.pir and now-self.started>=self.config['pir_warmup_seconds']:self.trigger('D2')
                self.pir=pir
                mm=hardware.get('tof_mm',-1)
                if hardware.get('tof_valid') and 0<mm<=self.config['tof_trigger_mm']:
                    self.tof_near_samples+=1
                    if self.tof_near_samples>=2 and not self.tof_near:
                        self.tof_near=True;self.trigger('ToF')
                else:
                    self.tof_near_samples=0
                    if not hardware.get('tof_valid') or mm>self.config['tof_release_mm']:self.tof_near=False
            except Exception as exc:
                self.online=False;self.configured=False;self.error=str(exc)
                self.next_poll=self.clock()+3
        while True:
            try:action,done,reply=self.commands.get_nowait()
            except Empty:break
            try:reply.update(self.process_command(action))
            except Exception as exc:reply['error']=str(exc)
            finally:done.set()
        try:self.handle_result(self.results.get_nowait())
        except Empty:pass
        now=self.clock()
        if self.state=='IDLE' and now>=self.next_periodic:
            self.trigger('periodic');self.next_periodic=now+self.config['periodic_seconds']
        if self.state=='INFERENCE' and now>=self.deadline:
            self.gate.clear();self.transition('IDLE')
            self.next_periodic=max(self.next_periodic,now+1)
        if self.state=='DETECTION':
            if self.pending_event is not None and self.online:
                e=self.pending_event
                try:
                    reply=self.call('po_event',e['id'],e['class'],int(round(e['confidence']*100)),e['count'])
                    if reply.get('ok'):
                        self.pending_event=None;self.transition('SERVO ACTION')
                        self.deadline=now+max(6,6*self.config['servo_hold_ms']/1000+1.5)
                        self.action_started=self.clock()
                    else:
                        self.error=reply.get('error');self.pending_event=None;self.transition('COOLDOWN')
                except Exception as exc:self.error=str(exc)
            if self.state=='DETECTION' and now>=self.deadline:
                self.pending_event=None;self.transition('COOLDOWN')
        if self.state=='SERVO ACTION' and ((self.last_poll>self.action_started and not self.hardware.get('servo_busy',True)) or now>=self.deadline):
            self.transition('COOLDOWN')
        if self.state=='COOLDOWN' and now-self.last_cycle>=self.config['cooldown_seconds']:
            self.transition('IDLE');self.previous=None;self.streak=0
        if self.online and self.configured and now>=self.oled_hold_until:
            mode='WAITING' if self.state in ('IDLE','INFERENCE','TRIGGER') else 'DETECTION'
            e=self.last_event or {};values=(mode,e.get('class',''),int(round(e.get('confidence',0)*100)),self.count)
            if values!=self.last_oled:
                try:self.call('po_display',*values);self.last_oled=values
                except Exception as exc:self.error=str(exc)

    def run(self):
        while not self.stopping.is_set():
            try:
                with self.lock:self.step()
            except Exception as exc:
                with self.lock:self.error=str(exc)
            self.stopping.wait(.05)
