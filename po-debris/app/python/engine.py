"""App Lab single-pass worker: latest-frame buffer and independent live preview."""
import csv
import json
import math
import multiprocessing as mp
from multiprocessing import shared_memory
from queue import Empty, Full
import numpy as np
import platform
import threading
import time
import traceback
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
import cv2
from arduino.app_utils import brick
from csi_capture import IMX219Camera
from detect import detect
from ncnn_backend import NCNNDetector

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ['bottle', 'grass', 'branch', 'milk-box', 'plastic-bag', 'plastic-garbage', 'ball', 'leaf']
MODEL_DIRS = {320: 'ncnn-320', 416: 'ncnn-416', 640: 'live-ncnn'}
DEFAULTS = dict(conf=.55, iou=.5, imgsz=416)


def rate(times):
    return (len(times)-1)/(times[-1]-times[0]) if len(times)>1 and times[-1]>times[0] else 0.0


def infer_worker(memory_name, frame_lock, frame_id, settings, stopping, results, analysis_gate):
    """One NCNN process, one shared frame slot, no concurrent model calls."""
    memory=shared_memory.SharedMemory(name=memory_name)
    image=np.ndarray((720,1280,3),dtype=np.uint8,buffer=memory.buf)
    models={}
    previous=-1
    try:
        # Keep the graph loaded during standby; the camera never restarts on a trigger.
        initial_size=int(settings[2])
        models[initial_size]=NCNNDetector(ROOT/'model'/MODEL_DIRS[initial_size],initial_size,threads=2)
        if list(models[initial_size].names.values())!=CLASSES:
            raise ValueError('Mapping diverso dalle otto classi RFT')
        while not stopping.is_set():
            if not analysis_gate.wait(.05):continue
            if stopping.is_set():break
            with frame_lock:
                current=frame_id.value
                frame=image.copy() if current and current!=previous else None
            if frame is None:
                stopping.wait(.003)
                continue
            previous=current
            with settings.get_lock():
                confidence,nms_iou,size=settings[:]
            size=int(size)
            if size not in models:
                models[size]=NCNNDetector(ROOT/'model'/MODEL_DIRS[size],size,threads=2)
                if list(models[size].names.values())!=CLASSES:
                    raise ValueError('Mapping diverso dalle otto classi RFT')
            start=time.perf_counter()
            found=detect(models[size],frame,size,confidence,nms_iou)
            result=dict(frame=current,imgsz=size,found=found,inference_ms=(time.perf_counter()-start)*1000,
                        timestamp=datetime.now(timezone.utc).isoformat())
            try:
                results.put_nowait(result)
            except Full:
                try:results.get_nowait()
                except Empty:pass
                try:results.put_nowait(result)
                except Full:pass
    except Exception as exc:
        traceback.print_exc()
        try:results.put(dict(error=str(exc)),timeout=1)
        except Full:pass
    finally:
        memory.close()


@brick
class Engine:
    def __init__(self):
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.latest = None
        self.latest_id = 0
        self.jpeg = None
        self.camera = None
        self.predictions = []
        self.prediction_time = 0
        self.history = deque(maxlen=180)
        self.camera_times = deque(maxlen=60)
        self.ai_times = deque(maxlen=30)
        self.preview_times = deque(maxlen=30)
        self.supported = sorted(s for s, p in MODEL_DIRS.items() if (ROOT/'model'/p/'metadata.yaml').exists())
        self.config = dict(DEFAULTS)
        self.settings_path = ROOT / 'data/settings.json'
        self.directory = ROOT / 'data' / datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.directory/'detections.csv'
        self.status = dict(state='initializing', camera='not opened', model='not loaded',
                           counts=dict(artificial=0,organic=0), detections=[], frame=0,
                           camera_fps=0, ai_fps=0, preview_fps=0, fps=0, inference_ms=None,
                           error=None, quality='YOLO11n pretrained · RFT test mAP50 74.6% · 101 epoche',
                           mode='CSI live · Linux ARM64 · NCNN · inferenza singola', architecture=platform.machine(),
                           resolution=[1280,720], preview_resolution=[640,360], supported_sizes=self.supported,
                           tracking=False, video_recording=False, batch=1)
        with self.csv_path.open('w',newline='') as f:
            csv.writer(f).writerow(['timestamp_utc','camera_frame','class','group','confidence','x1','y1','x2','y2','input_size','inference_ms'])
        if self.settings_path.exists():
            try:
                old=json.loads(self.settings_path.read_text())
                self.configure({k:v for k,v in old.items() if k in DEFAULTS})
            except Exception as exc:
                print('Impostazioni non valide, uso default:',exc,flush=True)

    def snapshot(self):
        with self.lock:
            result=dict(self.status, config=dict(self.config), history=list(self.history))
        if hasattr(self,'peripherals'):result['peripherals']=self.peripherals.snapshot()
        return result

    def configure(self, values):
        if not values or set(values)-set(DEFAULTS):
            raise ValueError('Impostazioni sconosciute o vuote')
        for key,value in values.items():
            if key=='imgsz':
                if type(value) is not int or value not in self.supported:
                    raise ValueError('Risoluzione NCNN non supportata')
            elif type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=1:
                raise ValueError('Confidence/IoU devono essere fra 0 e 1')
        with self.lock:
            updated=dict(self.config,**values)
            temp=self.settings_path.with_suffix('.tmp')
            temp.write_text(json.dumps(updated,indent=2),encoding='utf8')
            temp.replace(self.settings_path)
            if updated['imgsz']!=self.config['imgsz']:
                self.predictions=[]
                self.ai_times.clear()
            self.config=updated
            if hasattr(self,'shared_settings'):
                with self.shared_settings.get_lock():
                    self.shared_settings[:]=[updated['conf'],updated['iou'],updated['imgsz']]
        return dict(ok=True,config=updated)

    def start(self):
        if platform.machine() not in ('aarch64','arm64'):
            raise RuntimeError('Eseguire da App Lab sulla UNO Q ARM64')
        if not any('GStreamer:' in line and 'YES' in line for line in cv2.getBuildInformation().splitlines()):
            raise RuntimeError('OpenCV App Lab deve supportare GStreamer')
        context=mp.get_context('spawn')
        self.memory=shared_memory.SharedMemory(create=True,size=720*1280*3)
        self.shared_image=np.ndarray((720,1280,3),dtype=np.uint8,buffer=self.memory.buf)
        self.frame_lock=context.Lock()
        self.shared_id=context.Value('Q',0)
        self.shared_settings=context.Array('d',[self.config['conf'],self.config['iou'],self.config['imgsz']])
        self.worker_stopping=context.Event()
        self.analysis_gate=context.Event()
        self.results=context.Queue(maxsize=1)
        self.worker=context.Process(target=infer_worker,args=(self.memory.name,self.frame_lock,self.shared_id,
                                    self.shared_settings,self.worker_stopping,self.results,self.analysis_gate),name='NCNN.single')
        self.worker.start()
        self.capture_thread=threading.Thread(target=self.capture_loop,name='IMX219.latest',daemon=True)
        self.preview_thread=threading.Thread(target=self.preview_loop,name='Preview.latest',daemon=True)
        self.capture_thread.start()
        self.preview_thread.start()
        from peripherals import Peripherals
        self.peripherals=Peripherals(ROOT,self.analysis_gate)
        self.peripherals.start()

    def stop(self):
        self.stopping.set()
        if hasattr(self,'peripherals'):self.peripherals.stop()
        self.worker_stopping.set()
        for thread in (self.capture_thread,self.preview_thread):
            thread.join(timeout=3)
        self.worker.join(timeout=3)
        if self.worker.is_alive():
            self.worker.terminate()
            self.worker.join(timeout=1)
        self.memory.close()
        self.memory.unlink()

    def capture_loop(self):
        while not self.stopping.is_set():
            camera=None
            try:
                camera=IMX219Camera(0,resolution=(1280,720),fps=30,auto_reconnect=False)
                self.camera=camera
                camera.start()
                while not self.stopping.is_set():
                    frame=camera.capture()
                    if frame is None:
                        raise RuntimeError('IMX219: acquisizione interrotta')
                    h,w=frame.shape[:2]
                    if (w,h)!=(1280,720):
                        raise RuntimeError(f'Camera ha negoziato {w}x{h}, attesi 1280x720')
                    now=time.perf_counter()
                    with self.frame_lock:
                        np.copyto(self.shared_image,frame)
                        self.shared_id.value=self.latest_id+1
                    with self.lock:
                        self.latest=frame
                        self.latest_id+=1
                        self.camera_times.append(now)
                        self.status.update(camera='IMX219 · libcamerasrc · container',camera_fps=round(rate(self.camera_times),2),
                                           camera_frame=self.latest_id, resolution=[w,h])
            except Exception as exc:
                traceback.print_exc()
                with self.lock:
                    self.latest=None
                    self.jpeg=None
                    self.predictions=[]
                    self.camera_times.clear()
                    self.status.update(state='error',camera='disconnected',camera_fps=0,ai_fps=0,preview_fps=0,error=str(exc))
                self.stopping.wait(5)
            finally:
                if camera is not None:
                    camera.stop()
                self.camera=None

    def preview_loop(self):
        previous_id=-1
        while not self.stopping.wait(1/30):
            with self.lock:
                frame,frame_id=self.latest,self.latest_id
                found=list(self.predictions) if time.perf_counter()-self.prediction_time<2 else []
            if frame is None or frame_id==previous_id:
                continue
            previous_id=frame_id
            preview=cv2.resize(frame,(640,360))
            h,w=frame.shape[:2]
            for d in found:
                x1,y1,x2,y2=d['xyxy']
                a,b,c,e=round(x1*640/w),round(y1*360/h),round(x2*640/w),round(y2*360/h)
                color=(90,205,85) if d['group']=='organic' else (0,175,255)
                cv2.rectangle(preview,(a,b),(c,e),color,2)
                cv2.putText(preview,f"{d['class']} {d['confidence']:.2f}",(a,max(18,b-5)),cv2.FONT_HERSHEY_SIMPLEX,.45,color,1)
            ok,encoded=cv2.imencode('.jpg',preview,[cv2.IMWRITE_JPEG_QUALITY,75])
            if ok:
                with self.lock:
                    self.jpeg=encoded.tobytes()
                    self.preview_times.append(time.perf_counter())
                    self.status['preview_fps']=round(rate(self.preview_times),2)

    def execute(self):
        try:
            with self.csv_path.open('a',newline='',encoding='utf8') as f:
                output=csv.writer(f)
                while not self.stopping.is_set():
                    try:
                        result=self.results.get(timeout=.5)
                    except Empty:
                        if not self.worker.is_alive():
                            raise RuntimeError('Processo NCNN terminato senza risultato')
                        if not self.analysis_gate.is_set():
                            with self.lock:self.status.update(ai_fps=0,fps=0)
                        continue
                    if 'error' in result:
                        raise RuntimeError(result['error'])
                    with self.lock:
                        if result['imgsz']!=self.config['imgsz']:
                            continue
                    found,latency=result['found'],result['inference_ms']
                    frame_id,size,timestamp=result['frame'],result['imgsz'],result['timestamp']
                    self.peripherals.submit(found,frame_id,latency)
                    counts=Counter(artificial=0,organic=0)
                    for d in found:
                        counts[d['group']]+=1
                        output.writerow([timestamp,frame_id,d['class'],d['group'],d['confidence'],*d['xyxy'],size,latency])
                    f.flush()
                    with self.lock:
                        self.predictions=found
                        self.prediction_time=time.perf_counter()
                        self.ai_times.append(self.prediction_time)
                        ai_fps=round(rate(self.ai_times),2)
                        self.status.update(state='running' if self.latest is not None else 'error',
                                           error=None if self.latest is not None else self.status['error'],
                                           model=f'YOLO11n · NCNN FP32 · {size} px · batch 1',
                                           frame=frame_id,detections=found,counts=dict(counts),ai_fps=ai_fps,fps=ai_fps,
                                           inference_ms=round(latency,2),timestamp=timestamp)
                        self.history.append(dict(time=timestamp,artificial=counts['artificial'],organic=counts['organic'],visible=len(found),inference_ms=latency))
        except Exception as exc:
            traceback.print_exc()
            with self.lock:
                self.status.update(state='error',error=str(exc))
        finally:
            (self.directory/'session.json').write_text(json.dumps(self.snapshot(),indent=2),encoding='utf8')
