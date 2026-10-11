"""Class-specific single-pass YOLO detection + CSV log + annotated video.
Works on PC (.pt weights) and UNO Q (NCNN exported model directory).
Each row is a per-frame detection; NOT a count of unique debris crossing bridge.
"""
import argparse,csv,time
from pathlib import Path
import os
os.environ.setdefault('YOLO_CONFIG_DIR',str(Path(__file__).resolve().parents[1]/'.runtime'))
import cv2
P=Path(__file__).resolve().parents[1]
GROUPS={'branch':'organic','leaf':'organic','grass':'organic'}

def iou(a,b):
    x1=max(a[0],b[0]);y1=max(a[1],b[1]);x2=min(a[2],b[2]);y2=min(a[3],b[3])
    inter=max(0,x2-x1)*max(0,y2-y1)
    ua=(a[2]-a[0])*(a[3]-a[1]);ub=(b[2]-b[0])*(b[3]-b[1]);return inter/(ua+ub-inter+1e-8)

def suppress(dets,threshold=0.50):
    result=[]
    for d in sorted(dets,key=lambda v:v['confidence'],reverse=True):
        if all(d['class']!=other['class'] or iou(d['xyxy'],other['xyxy'])<threshold for other in result):result.append(d)
    return result

def detect(model,frame,imgsz=416,conf=.35,nms_iou=.50):
    """Exactly one model call, then class-aware NMS in original coordinates."""
    if hasattr(model,'detections'):
        found=model.detections(frame,conf)
        for d in found:d['xyxy']=[round(v) for v in d['xyxy']]
        return suppress(found,nms_iou)
    result=model.predict(frame,imgsz=imgsz,conf=conf,iou=nms_iou,verbose=False)[0]
    found=[]
    if result.boxes is not None:
        for box in result.boxes:
            name=str(model.names[int(box.cls.item())])
            found.append({'class':name,'group':GROUPS.get(name,'artificial'),'confidence':float(box.conf.item()),'xyxy':[round(v) for v in box.xyxy[0].cpu().tolist()]})
    return suppress(found,nms_iou)

