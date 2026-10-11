"""Native App Lab entry point: WebUI and CSI/NCNN run entirely on UNO Q."""
import time
import importlib.util
import platform
import subprocess
import sys
from pathlib import Path

# The base image supplies a custom OpenCV with GStreamer. Installing NCNN's
# PyPI dependency opencv-python would overwrite it with a build without CSI.
# Install the unmodified official NCNN wheel offline without replacing OpenCV.
if platform.machine() not in ('aarch64', 'arm64'):
    raise RuntimeError('Avviare questa app da App Lab sulla UNO Q ARM64')
if importlib.util.find_spec('ncnn') is None:
    wheels = list((Path(__file__).resolve().parents[1] / 'vendor').glob('*manylinux*aarch64.whl'))
    if len(wheels) != 1:
        raise RuntimeError('Wheel ufficiale NCNN ARM64 assente o ambigua')
    subprocess.run(['uv', 'pip', 'install', '--python', sys.executable, '--no-index', '--no-deps', str(wheels[0])], check=True)
from fastapi import HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI
from engine import Engine, ROOT

def main():
    engine = Engine()
    ui = WebUI(assets_dir_path=str(ROOT / 'assets'))
    ui.expose_api('GET', '/api/status', engine.snapshot)

    def peripheral_status():
        if not hasattr(engine,'peripherals'):
            return {'state':'initializing','bridge_online':False}
        return engine.peripherals.snapshot()

    def peripheral_command(values: dict):
        if not hasattr(engine,'peripherals'):
            raise HTTPException(status_code=503,detail='Periferiche in inizializzazione')
        try:return engine.peripherals.test(values)
        except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc

    def peripheral_config(values: dict):
        if not hasattr(engine,'peripherals'):
            raise HTTPException(status_code=503,detail='Periferiche in inizializzazione')
        try:
            result=engine.peripherals.configure(values)
            if 'event_confidence' in values:engine.configure({'conf':values['event_confidence']})
            return result
        except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc

    ui.expose_api('GET','/api/peripherals/status',peripheral_status)
    ui.expose_api('POST','/api/peripherals/test',peripheral_command)
    ui.expose_api('POST','/api/peripherals/config',peripheral_config)
    
    def configure(values: dict):
        try:
            result=engine.configure(values)
            if 'conf' in values and hasattr(engine,'peripherals'):
                engine.peripherals.configure({'event_confidence':values['conf']})
            return result
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    def frame():
        with engine.lock:
            jpeg = engine.jpeg
        return Response(jpeg or b'Camera non disponibile', status_code=200 if jpeg else 503,
                        media_type='image/jpeg' if jpeg else 'text/plain', headers={'Cache-Control': 'no-store'})
    
    def stream():
        def frames():
            previous = None
            while not engine.stopping.is_set():
                with engine.lock:
                    jpeg = engine.jpeg
                if jpeg is not None and jpeg is not previous:
                    yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n'
                    previous = jpeg
                time.sleep(.02)
        return StreamingResponse(frames(), media_type='multipart/x-mixed-replace; boundary=frame')
    
    def export():
        return FileResponse(engine.csv_path, media_type='text/csv', filename='po-debris.csv')
    
    ui.expose_api('POST', '/api/config', configure)
    ui.expose_api('GET', '/frame.jpg', frame)
    ui.expose_api('GET', '/stream.mjpg', stream)
    ui.expose_api('GET', '/export.csv', export)
    App.run()

if __name__ == '__main__':
    main()
