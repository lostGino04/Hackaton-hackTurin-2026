# PO-DEBRIS: integrazione delle periferiche

Pesi e grafi NCNN conservati, SHA256 sorgente `bd23f47d3087a49200113843fa6b6243af6909e13a15db560e57d470b7402bdb`. Nessun training, export o modifica del modello. Backup iniziale: `peripheral_verification/backup.json`.

## Componenti

- `PO_Debris_AI/python/peripherals.py`: coordinatore con un thread RouterBridge, timeout RPC 1 secondo, trigger manuale/D2/ToF/periodico e conferma su due frame AI coerenti.
- `PO_Debris_AI/sketch/sketch.ino`: D2 input, ToF su Wire1/Qwiic o Wire/shield dopo lettura model ID, OLED su I²C, servo D9 e D10 sequenziali. Callback RPC su dati memorizzati; I²C su thread MCU separato.
- `PO_Debris_AI/config/peripherals.json`: confidence iniziale 0.55, cooldown 10 s, controllo video ogni 8 s, finestre di inferenza 6 s, movimento iniziale 90°→95°→90°. Le posizioni richiedono verifica meccanica: nessun servo ha feedback di posizione.
- `PO_Debris_AI/sketch/sketch.yaml`: RouterBridge 0.4.3, Arduino_Modulino 0.7.0, Servo 1.3.0 con supporto Zephyr, U8g2 2.36.19. Il core già installato viene riutilizzato senza aggiornamento.

Camera IMX219 e preview continuano anche in IDLE, SERVO ACTION e COOLDOWN. Il grafo YOLO rimane caricato: nessun riavvio video per trigger, nessun tiling, nessuna inferenza concorrente. Gli FPS AI diventano zero durante il vero standby.

Il PIR non è sufficiente per i detriti inanimati: trigger manuale e controllo video periodico sono sempre disponibili. Un ToF non valido/out of range viene ignorato. Aggiornamenti OLED solo quando cambia il contenuto. Servomotori mai simultanei, rientro separato a home, timer Servo spento in standby.

Conteggio di eventi confermati per episodio di presenza. Finché resta almeno un oggetto sopra soglia non si riattiva il ciclo; tre frame AI senza detriti riarmano il sistema. Non è tracking di identità individuali né garanzia di conteggio unico per oggetti in gruppi.

## Identificazione e condizioni prima del collaudo fisico

Il Qwiic ufficiale UNO Q corrisponde a **Wire1**; l'I²C dei connettori UNO/shield a **Wire**. Non viene scandito l'I²C Linux della camera/PMIC. Lo sketch legge il model ID del ToF a 0x29, registro 0x010F; solo il modello 0xEBAA supportato viene inizializzato tramite Arduino_Modulino. Un altro modello viene segnalato e disabilitato.

Un indirizzo OLED 0x3C/0x3D **non identifica il controller**. `oled_controller` rimane `unknown` e il display disabilitato fino alla verifica della sigla. SSD1306, SSD1308 e SSD1315 usano il driver U8g2 compatibile SSD1306; SH1106 ha un driver distinto.

`servo_enabled` è inizialmente false. Verificare alimentazione 5 V, massa comune, polarità e limiti meccanici. Eseguire prima D9 e poi D10 singolarmente; il ciclo completo resta sequenziale anche dopo il collaudo. Non collegare mai l'alimentazione dei servo all'uscita digitale.

Lo sketch è codice applicativo STM32: App Lab Run lo programma nel microcontrollore. Dato il vincolo dell'utente «Non cambiare firmware», il caricamento richiede la sua autorizzazione specifica allo sketch applicativo. Bootloader, firmware Zephyr di base, Linux e configurazione camera non devono essere modificati. Finché manca tale autorizzazione, sulla scheda viene installato soltanto il coordinatore Python; i servizi MCU risultano assenti e l'AI continua normalmente.

## Comandi dalla cartella principale del progetto

```powershell
.\.venv\Scripts\python.exe scripts/peripheral_cli.py status
.\.venv\Scripts\python.exe scripts/peripheral_cli.py trigger
.\.venv\Scripts\python.exe scripts/peripheral_cli.py scan
.\.venv\Scripts\python.exe scripts/peripheral_cli.py oled
# SOLO dopo verifica dell'alimentazione e abilitazione della configurazione:
.\.venv\Scripts\python.exe scripts/peripheral_cli.py servo1
.\.venv\Scripts\python.exe scripts/peripheral_cli.py servo2
.\.venv\Scripts\python.exe scripts/peripheral_cli.py cycle
```

`--url http://<IP UNO Q>:7000` consente di usare la LAN. Le API sono nello stesso Brick WebUI già esistente: GET `/api/peripherals/status`, POST `/api/peripherals/test` con `{"action":"trigger"}`, POST `/api/peripherals/config` per i soli parametri dichiarati. Nessuna nuova dashboard.

Per modificare parametri tramite file senza problemi di quoting PowerShell: salvare JSON e inviarlo con `Invoke-RestMethod -Uri http://127.0.0.1:7000/api/peripherals/config -Method Post -ContentType application/json -Body (Get-Content configurazione.json -Raw)`.

## Prove realmente effettuate

- Sketch compilato sul compilatore UNO Q/Zephyr della scheda, senza upload; log `peripheral_verification/compile.log`.
- Sei test della state machine: conferma doppia, frame duplicati/confidence/matching, latch di presenza, cooldown, limiti servo, fallback con bridge guasto.
- Camera reale e trigger manuale YOLO verificati sul backend nuovo. Frame camera e frame AI avanzano, nessun errore video; tutti gli hash dei modelli originali confrontati sulla scheda. `peripheral_verification/python-verified.json`.
- D2 HIGH/LOW, ToF, OLED, D9 e D10 fisici e collegamento ai callback STM32 **non ancora collaudati**: occorrono lo sketch autorizzato, sigle dei moduli e verifica alimentazione.

Fonti: [UNO Q Wire/Wire1](https://docs.arduino.cc/tutorials/uno-q/user-manual/), [RouterBridge MCU](https://github.com/arduino-libraries/Arduino_RouterBridge), [Modulino Distance](https://docs.arduino.cc/hardware/modulino-distance), [Servo Zephyr](https://github.com/arduino-libraries/Servo), [Seeed OLED](https://wiki.seeedstudio.com/Grove-OLED_Display_0.96inch/).
