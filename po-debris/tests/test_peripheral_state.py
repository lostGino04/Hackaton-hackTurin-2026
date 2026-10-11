"""Actuation safeguards, presence suppression and sensor-failure fallback."""
import json,sys,tempfile,threading,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app/python'))
from peripherals import Peripherals

class Bridge:
    def __init__(self):self.calls=[];self.online=True;self.busy=False
    def call(self,name,*args,timeout=1):
        self.calls.append((name,args))
        if not self.online:raise TimeoutError('sensor bridge offline')
        if name=='po_status':return json.dumps(dict(protocol=1,d2=0,tof_valid=False,tof_mm=-1,servo_busy=self.busy))
        if name=='po_event':self.busy=True
        return '{"ok":true}'

class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'config').mkdir()
        (self.root/'config/peripherals.json').write_bytes((ROOT/'app/config/peripherals.json').read_bytes())
        self.time=100;self.bridge=Bridge();self.gate=threading.Event()
        self.p=Peripherals(self.root,self.gate,self.bridge,clock=lambda:self.time)
        self.p.step()
    def tearDown(self):self.temp.cleanup()
    def detection(self,frame,confidence=.8,x=10):
        self.p.handle_result(([dict(class_='unused',**{'class':'bottle','confidence':confidence,'xyxy':[x,10,x+40,60]})],frame,400,self.time))
        self.time+=.5
    def test_two_coherent_frames_required(self):
        self.detection(1);self.assertEqual(self.p.count,0)
        self.detection(2);self.assertEqual(self.p.count,1)
        self.p.step();self.assertEqual(self.p.state,'SERVO ACTION')
        events=[x for x in self.bridge.calls if x[0]=='po_event'];self.assertEqual(len(events),1)
    def test_duplicate_frame_low_confidence_and_moved_box(self):
        self.detection(1,.54);self.assertEqual(self.p.count,0)
        self.detection(2);self.detection(2);self.assertEqual(self.p.count,0)
        self.detection(3,x=200);self.assertEqual(self.p.count,0)
        self.detection(4,x=202);self.assertEqual(self.p.count,1)
    def test_presence_latch_requires_absence_before_rearming(self):
        self.detection(1);self.detection(2);self.p.step()
        self.time+=12;self.bridge.busy=False;self.p.step();self.p.step()
        self.p.trigger('manual');self.detection(3);self.detection(4)
        self.assertEqual(self.p.count,1)
        for frame in (5,6,7):self.p.handle_result(([],frame,400,self.time))
        self.detection(8);self.detection(9);self.assertEqual(self.p.count,2)
    def test_manual_cycles_disabled_until_power_verified(self):
        with self.assertRaises(ValueError):self.p.test({'action':'cycle'})
        with self.assertRaises(ValueError):self.p.configure({'servo_active_1':150})
    def test_bridge_failure_and_out_of_range_do_not_block_periodic_ai(self):
        self.bridge.online=False;self.time+=9;self.p.step();self.time+=1.1;self.p.step()
        self.assertFalse(self.p.online);self.assertTrue(self.gate.is_set())
        self.assertEqual(self.p.last_trigger,'periodic')
    def test_cooldown_rejects_manual_repeat(self):
        self.p.config['servo_enabled']=True
        self.p.last_cycle=self.time
        with self.assertRaises(RuntimeError):self.p.process_command('servo1')

if __name__=='__main__':unittest.main()
