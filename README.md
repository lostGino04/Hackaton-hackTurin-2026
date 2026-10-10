# 🌊 Sistema di Sorveglianza Murazzi - HackTurin 2026

Sistema automatico di protezione e monitoraggio dei Murazzi di Torino sul fiume Po.

---

## Come funziona

### 1. Controllo piene → Barriera murazzi
- Il sensore HC-SR04 misura continuamente il livello dell'acqua
- Se supera la soglia critica → il servo SG90 alza la **barriera** (stampa 3D)
- L'accesso ai murazzi viene automaticamente bloccato
- Alert inviato al comune

### 2. Rilevamento detriti → Paratia flipper
- Il sensore PIR rileva qualsiasi movimento sul fiume
- La camera si accende e l'AI classifica l'oggetto:
  - **Detrito** → il servo SG90 aziona la **paratia** (stampa 3D) che lo dirige verso il centro del fiume + alert al comune
  - **Imbarcazione** → nessuna azione, solo log

---

## Hardware

| Componente | Modello | Funzione |
|---|---|---|
| Microcontrollore | Arduino UNO Q | Cervello del sistema |
| Sensore livello acqua | HC-SR04 | Misura distanza dall'acqua |
| Sensore movimento | PIR | Attiva la camera |
| Servo barriera | SG90 | Alza/abbassa barriera murazzi (3D) |
| Servo paratia | SG90 | Direziona detriti al centro |
| Camera | Webcam USB | Acquisizione immagini per AI |

## Collegamento

```
HC-SR04:   TRIG → Pin 9 | ECHO → Pin 8 | VCC → 5V | GND → GND
PIR:       OUT  → Pin 7 | VCC  → 5V    | GND → GND
Servo barriera → Pin 5  | VCC  → 5V    | GND → GND
Servo paratia  → Pin 6  | VCC  → 5V    | GND → GND
```

## Struttura del progetto

```
Hackaton-hackTurin-2026/
├── arduino/
│   └── sorveglianza_po.ino   # Codice Arduino UNO Q
├── python/
│   └── leggi_seriale.py      # AI + lettura seriale + alert comune
│   └── dati_po.csv           # Log dati (generato automaticamente)
└── README.md
```

## Setup

### Arduino
1. Apri `arduino/sorveglianza_po.ino` in Arduino IDE 2
2. Seleziona scheda **Arduino UNO Q**
3. Carica lo sketch

### Python
```bash
pip install pyserial opencv-python pillow requests
python python/leggi_seriale.py
```

## Soglie configurabili (nel codice Arduino)

| Parametro | Valore default | Descrizione |
|---|---|---|
| `SOGLIA_PIENA_CM` | 20 cm | Distanza acqua → barriera su |
| `SOGLIA_ATTENZIONE_CM` | 40 cm | Distanza acqua → attenzione |
| `PARATIA_DURATA` | 3000 ms | Quanto resta in posizione la paratia |
| `SOGLIA_CONFIDENZA` (Python) | 65% | Confidenza minima AI per agire |

## Team

- **lostGino04**
- **coricciatigiada**
