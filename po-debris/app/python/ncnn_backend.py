"""YOLO11 detect NCNN backend without Torch, for ARM64 CPU deployments.

Supports decoded xywh + class scores output (4+nc,anchors), FP32 export.
Export parity must be verified for each model/exporter version.
"""
from pathlib import Path
import cv2
import numpy as np
import yaml
from detect import GROUPS


class NCNNDetector:
    def __init__(self,directory,imgsz=640,threads=4):
        import ncnn
        self.ncnn,self.imgsz=ncnn,imgsz
        directory=Path(directory)
        metadata=yaml.safe_load((directory/'metadata.yaml').read_text(encoding='utf8'))
        exported_size=metadata.get('imgsz',[640,640])
        if isinstance(exported_size,int):exported_size=[exported_size,exported_size]
        if exported_size!=[imgsz,imgsz]:raise ValueError(f'NCNN input must match export size {exported_size}; re-export to change --imgsz')
        names=metadata['names']
        self.names=dict(enumerate(names)) if isinstance(names,list) else {int(k):v for k,v in names.items()}
        self.net=ncnn.Net();self.net.opt.num_threads=threads
        self.net.opt.use_vulkan_compute=False
        self.net.opt.use_fp16_packed=False;self.net.opt.use_fp16_storage=False;self.net.opt.use_fp16_arithmetic=False
        params=list(directory.glob('*.param'));weights=list(directory.glob('*.bin'))
        if len(params)!=1 or len(weights)!=1:raise ValueError('Expected one NCNN .param and .bin')
        if self.net.load_param(str(params[0])) or self.net.load_model(str(weights[0])):
            raise RuntimeError('Cannot load NCNN model')
        self.input_name=self.net.input_names()[0];self.output_name=self.net.output_names()[0]

    def detections(self,frame,confidence):
        h,w=frame.shape[:2];size=self.imgsz
        scale=min(size/h,size/w);rw,rh=round(w*scale),round(h*scale)
        left,top=(size-rw)//2,(size-rh)//2
        image=np.full((size,size,3),114,dtype=np.uint8)
        image[top:top+rh,left:left+rw]=cv2.resize(frame,(rw,rh))
        mat=self.ncnn.Mat.from_pixels(image,self.ncnn.Mat.PixelType.PIXEL_BGR2RGB,size,size)
        mat.substract_mean_normalize([0,0,0],[1/255]*3)
        ex=self.net.create_extractor();ex.input(self.input_name,mat)
        code,out=ex.extract(self.output_name)
        if code:raise RuntimeError(f'NCNN extract returned {code}')
        predictions=np.array(out).squeeze()
        features=4+len(self.names)
        if predictions.ndim!=2:raise ValueError(f'Unsupported NCNN output shape {predictions.shape}')
        if predictions.shape[0]==features:predictions=predictions.T
        if predictions.shape[1]!=features:raise ValueError(f'Expected decoded YOLO11 output with {features} features, got {predictions.shape}')
        classes=predictions[:,4:].argmax(axis=1)
        scores=predictions[np.arange(len(predictions)),classes+4]
        detections=[]
        for i in np.flatnonzero(scores>=confidence):
            x,y,bw,bh=predictions[i,:4]
            box=[float(np.clip((x-bw/2-left)/scale,0,w)),float(np.clip((y-bh/2-top)/scale,0,h)),
                 float(np.clip((x+bw/2-left)/scale,0,w)),float(np.clip((y+bh/2-top)/scale,0,h))]
            if box[2]<=box[0] or box[3]<=box[1]:continue
            name=self.names[int(classes[i])]
            detections.append(dict(xyxy=box,confidence=float(scores[i]),**{'class':name,'group':GROUPS.get(name,'artificial')}))
        return detections
