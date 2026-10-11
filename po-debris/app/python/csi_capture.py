"""CSI API with explicit RGB caps to fit the UNO Q DMA memory budget.

The stock CSICamera selects ABGR8888 on App Lab 0.12.0. Its extra channel
causes DMA allocation failure on the tested board. Keep Arduino discovery and
lifecycle, but select RGB explicitly before converting to inference BGR.
"""
import cv2
from arduino.app_peripherals.camera import CSICamera

class IMX219Camera(CSICamera):
    def _open_camera(self):
        self._close_camera()
        width, height = self.resolution
        pipeline = (f'{self._backend.gstreamer_source(self._camera_id)} ! '
                    f'video/x-raw,format=RGB,width={width},height={height} ! '
                    'videoconvert ! video/x-raw,format=BGR ! '
                    'appsink drop=true max-buffers=1 sync=false')
        self._cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self._cap.isOpened():
            self._close_camera()
            raise RuntimeError('IMX219 RGB: apertura CSI fallita (camera occupata o DMA)')
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._close_camera()
            raise RuntimeError('IMX219: nessun frame reale')
        h, w = frame.shape[:2]
        self.resolution = (w, h)
        self._set_status('connected', {'camera_name': self.name, 'camera_path': self.csi_path})
