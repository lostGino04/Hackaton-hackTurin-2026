"""
Sistema Murazzi Po - HackTurin 2026
Script Python:
  - Legge dati sensori dall'Arduino UNO Q via seriale
  - Attiva la camera quando il PIR rileva movimento
  - Usa AI (MobileNet via TensorFlow Lite) per distinguere detriti/imbarcazioni
  - Manda comandi alla paratia (servo) se rileva detriti
  - Simula alert al comune via email/HTTP

Requisiti:
    pip install pyserial opencv-python tflite-runtime pillow requests
"""

import serial
import serial.tools.list_ports
import csv
import time
import threading
from datetime import datetime

# Importazioni AI e camera (opzionali per demo senza hardware)
try:
    import cv2
    import numpy as np
    CAMERA_DISPONIBILE = True
except ImportError:
    CAMERA_DISPONIBILE = False
    print("⚠️  OpenCV non trovato - camera disabilitata")

try:
    import requests
    REQUESTS_DISPONIBILE = True
except ImportError:
    REQUESTS_DISPONIBILE = False

# ============================================================
# CONFIGURAZIONE
# ============================================================
BAUD_RATE        = 9600
OUTPUT_FILE      = "dati_po.csv"
CAMERA_INDEX     = 0          # 0 = prima webcam disponibile
ALERT_EMAIL      = "comune.torino@example.com"  # sostituire con email reale
WEBHOOK_URL      = ""         # URL webhook comune (opzionale)

# Soglia confidenza AI per classificare un oggetto
SOGLIA_CONFIDENZA = 0.65

# ============================================================
# Trova porta Arduino automaticamente
# ============================================================
def trova_porta_arduino():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if any(x in port.description for x in ["Arduino", "CH340", "USB Serial", "ttyUSB", "ttyACM"]):
            print(f"✅ Arduino trovato su: {port.device}")
            return port.device

    print("⚠️  Arduino non trovato automaticamente. Porte disponibili:")
    for p in ports:
        print(f"   {p.device} - {p.description}")
    return input("Inserisci la porta manualmente (es. COM3): ").strip()

# ============================================================
# Classificatore AI detriti/imbarcazioni
# Usa la camera per scattare una foto e classificare l'oggetto
# ============================================================
class ClassificatoreAI:
    def __init__(self):
        self.cap = None
        if CAMERA_DISPONIBILE:
            self.cap = cv2.VideoCapture(CAMERA_INDEX)
            if self.cap.isOpened():
                print("✅ Camera inizializzata")
            else:
                print("⚠️  Camera non disponibile")
                self.cap = None

    def cattura_e_classifica(self):
        """
        Cattura un frame dalla camera e classifica l'oggetto.
        Restituisce: ("DETRITO_SX" | "DETRITO_DX" | "IMBARCAZIONE" | None, confidenza)

        NOTA: in questa versione demo usa un classificatore semplificato
        basato su forma e colore. Per la versione finale si integra
        il modello esportato da Arduino App Lab (.tflite).
        """
        if not CAMERA_DISPONIBILE or self.cap is None or not self.cap.isOpened():
            print("📷 Camera non disponibile - simulazione AI")
            return self._simula_classificazione()

        ret, frame = self.cap.read()
        if not ret:
            return None, 0.0

        # Salva snapshot per debug
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cv2.imwrite(f"snapshot_{timestamp}.jpg", frame)

        # Analisi semplificata per demo:
        # - Oggetti con colori scuri/marroni → detriti
        # - Oggetti con colori chiari/riflessi → imbarcazioni
        risultato, confidenza = self._analizza_frame(frame)

        return risultato, confidenza

    def _analizza_frame(self, frame):
        """
        Classificazione base per demo.
        Da sostituire con modello .tflite di App Lab per la versione finale.
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, w = frame.shape[:2]

        # Dividi il frame in sinistra e destra per capire da dove arriva
        meta_sx = hsv[:, :w//2]
        meta_dx = hsv[:, w//2:]

        # Rileva oggetti scuri (detriti: legno, plastica scura)
        mask_scuro = cv2.inRange(hsv, (0, 0, 0), (180, 255, 80))
        pixel_scuri = cv2.countNonZero(mask_scuro)
        totale_pixel = h * w

        percentuale_scuro = pixel_scuri / totale_pixel

        if percentuale_scuro > 0.15:  # più del 15% di pixel scuri → detrito
            # Capisce da che lato è il detrito
            scuri_sx = cv2.countNonZero(mask_scuro[:, :w//2])
            scuri_dx = cv2.countNonZero(mask_scuro[:, w//2:])

            confidenza = min(0.95, 0.65 + percentuale_scuro)
            if scuri_sx > scuri_dx:
                return "DETRITO_SX", confidenza
            else:
                return "DETRITO_DX", confidenza
        else:
            return "IMBARCAZIONE", 0.70

    def _simula_classificazione(self):
        """Simulazione per demo senza camera fisica."""
        import random
        scelte = [("DETRITO_SX", 0.82), ("DETRITO_DX", 0.78), ("IMBARCAZIONE", 0.91)]
        return random.choice(scelte)

    def chiudi(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()

# ============================================================
# Alert al Comune
# ============================================================
def invia_alert_comune(tipo, distanza_cm=None, confidenza=None):
    ora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if tipo == "PIENA":
        messaggio = f"[{ora}] 🚨 ALLERTA PIENA - Livello critico rilevato ai Murazzi. Distanza acqua: {distanza_cm:.1f} cm. Barriere alzate automaticamente."
    elif tipo in ("DETRITO_SX", "DETRITO_DX"):
        lato = "sinistra" if tipo == "DETRITO_SX" else "destra"
        messaggio = f"[{ora}] ⚠️  DETRITI rilevati (lato {lato}) - Confidenza AI: {confidenza:.0%}. Paratia attivata."
    else:
        return  # imbarcazioni non generano alert

    print(f"\n📧 ALERT COMUNE: {messaggio}\n")

    # Webhook HTTP (se configurato)
    if REQUESTS_DISPONIBILE and WEBHOOK_URL:
        try:
            requests.post(WEBHOOK_URL, json={"messaggio": messaggio, "tipo": tipo}, timeout=5)
            print("✅ Alert inviato al comune via webhook")
        except Exception as e:
            print(f"⚠️  Invio webhook fallito: {e}")

# ============================================================
# Parsing riga dati da Arduino
# Formato: "DATI:timestamp,distanza,livello,movimento,barriera"
# ============================================================
def parse_riga(riga):
    riga = riga.strip()
    if not riga.startswith("DATI:"):
        return None

    try:
        parti = riga[5:].split(",")
        if len(parti) != 5:
            return None
        return {
            "timestamp"   : int(parti[0]),
            "distanza_cm" : float(parti[1]),
            "livello"     : parti[2],
            "movimento"   : parti[3] == "1",
            "barriera"    : parti[4] == "1",
            "ora_reale"   : datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except ValueError:
        return None

# ============================================================
# Thread camera: si attiva quando il PIR rileva movimento
# ============================================================
def thread_camera(ser, ai, dati):
    print("📷 Movimento rilevato! Camera attivata...")
    risultato, confidenza = ai.cattura_e_classifica()

    if risultato is None:
        print("⚠️  Classificazione fallita")
        return

    etichetta = "IMBARCAZIONE" if risultato == "IMBARCAZIONE" else "DETRITO"
    lato      = ""
    if risultato == "DETRITO_SX":
        lato = " (lato sinistro)"
    elif risultato == "DETRITO_DX":
        lato = " (lato destro)"

    print(f"🤖 AI: {etichetta}{lato} - Confidenza: {confidenza:.0%}")

    if confidenza >= SOGLIA_CONFIDENZA:
        # Manda comando al servo paratia
        ser.write((risultato + "\n").encode())

        # Alert al comune se detriti
        if risultato in ("DETRITO_SX", "DETRITO_DX"):
            invia_alert_comune(risultato, confidenza=confidenza)

# ============================================================
# Main
# ============================================================
def main():
    porta = trova_porta_arduino()
    ai    = ClassificatoreAI()
    camera_in_uso = False

    print(f"\nConnessione a {porta} a {BAUD_RATE} baud...")

    try:
        ser = serial.Serial(porta, BAUD_RATE, timeout=5)
        time.sleep(2)
        print("✅ Connesso! Sistema attivo.\n")
        print("Premi CTRL+C per fermare.\n")

        ultimo_livello_piena = False

        with open(OUTPUT_FILE, "a", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=[
                "ora_reale", "timestamp", "distanza_cm", "livello", "movimento", "barriera"
            ])
            if csvfile.tell() == 0:
                writer.writeheader()

            while True:
                if ser.in_waiting > 0:
                    riga = ser.readline().decode("utf-8", errors="ignore").strip()

                    # Log comandi Arduino
                    if riga.startswith("CMD:"):
                        print(f"🔧 Arduino: {riga[4:]}")
                        continue

                    dati = parse_riga(riga)
                    if not dati:
                        continue

                    # Stampa stato
                    barriera_str = "🔒 ALZATA" if dati["barriera"] else "🔓 abbassata"
                    print(f"[{dati['ora_reale']}] "
                          f"Acqua: {dati['distanza_cm']:.1f}cm | "
                          f"Livello: {dati['livello']} | "
                          f"Barriera: {barriera_str} | "
                          f"Movimento: {'SÌ' if dati['movimento'] else 'no'}")

                    # Alert piena (solo al cambio di stato)
                    if dati["livello"] == "PIENA" and not ultimo_livello_piena:
                        invia_alert_comune("PIENA", distanza_cm=dati["distanza_cm"])
                        ultimo_livello_piena = True
                    elif dati["livello"] == "NORMALE":
                        ultimo_livello_piena = False

                    # Attiva camera se c'è movimento (in thread separato)
                    if dati["movimento"] and not camera_in_uso:
                        camera_in_uso = True
                        t = threading.Thread(
                            target=lambda: (thread_camera(ser, ai, dati),
                                           setattr(t, '_done', True)),
                            daemon=True
                        )
                        t.start()
                        # Reset flag dopo 5 secondi per evitare attivazioni continue
                        threading.Timer(5.0, lambda: globals().update(camera_in_uso=False)).start()

                    writer.writerow(dati)
                    csvfile.flush()

    except serial.SerialException as e:
        print(f"❌ Errore seriale: {e}")
    except KeyboardInterrupt:
        print(f"\n🛑 Sistema fermato. Dati salvati in: {OUTPUT_FILE}")
    finally:
        ai.chiudi()
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    main()
