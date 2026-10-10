# 🌊 Sistema di Sorveglianza Murazzi - HackTurin 2026

Sistema automatico di protezione e monitoraggio dei Murazzi di Torino sul fiume Po.

---

## Come funziona

### 1. Controllo piene → Barriera murazzi
- Il **Modulino Distance** (VL53L4CD) misura continuamente il livello dell'acqua via Time-of-Flight
- Se la distanza scende sotto la soglia critica (acqua alta) → il servo SG90 alza la **barriera** (stampa 3D)
- L'accesso ai murazzi viene automaticamente bloccato
- Alert inviato al comune

### 2. Rilevamento detriti → Paratia flipper
- Il sensore di movimento rileva attività sul fiume
- La camera si accende e l'AI classifica l'oggetto:
  - **Detrito** → il servo SG90 aziona la **paratia flipper** (stampa 3D) che lo dirige verso il centro del fiume + alert al comune
  - **Imbarcazione** → nessuna azione meccanica, solo log

---

## Hardware

| Componente | Modello | Funzione |
|---|---|---|
| Microcontrollore | Arduino UNO Q | Cervello del sistema |
| Carrier | Arduino Media Carrier | Hub Qwiic + connettività |
| Sensore livello acqua | Modulino Distance (VL53L4CD) | Misura distanza ToF fino a 1200mm via I2C/Qwiic |
| Sensore movimento | PIR (HC-SR501) | Rileva movimento sul fiume per attivare la camera |
| Servo barriera | SG90 | Alza/abbassa barriera murazzi (stampa 3D) |
| Servo paratia | SG90 | Direziona detriti al centro del fiume |
| Camera | Webcam USB | Acquisizione immagini per classificazione AI |

## Collegamento

```
Modulino Distance  → Qwiic connector (Media Carrier)
PIR OUT            → Pin 7  | VCC → 5V | GND → GND
Servo barriera     → Pin 5  | VCC → 5V | GND → GND
Servo paratia      → Pin 6  | VCC → 5V | GND → GND
```

## Librerie Arduino necessarie
- **Modulino** by Arduino → Gestione librerie → cerca "Modulino"
- **Servo** → già inclusa nell'IDE

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

### 1. Arduino
1. Apri `arduino/sorveglianza_po.ino` in Arduino IDE 2
2. Installa la libreria **Modulino** da Gestione librerie
3. Seleziona scheda **Arduino UNO Q**
4. Carica lo sketch

### 2. Python
```bash
pip install pyserial opencv-python pillow requests
python python/leggi_seriale.py
```

## Soglie configurabili (nel codice Arduino)

| Parametro | Valore default | Descrizione |
|---|---|---|
| `SOGLIA_PIENA_MM` | 200 mm | Distanza acqua → barriera su |
| `SOGLIA_ATTENZIONE_MM` | 400 mm | Distanza acqua → attenzione |
| `PARATIA_DURATA_MS` | 3000 ms | Quanto resta in posizione la paratia |
| `SOGLIA_CONFIDENZA` (Python) | 65% | Confidenza minima AI per agire |

## Team

- **lostGino04**
- **coricciatigiada**
