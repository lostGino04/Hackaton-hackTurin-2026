# PO-DEBRIS AI — Arduino App Lab

Visione locale sulla UNO Q 4 GB con IMX219 CSI, YOLO11n NCNN e dashboard WebUI. Camera e anteprima sono indipendenti dall'inferenza: un solo processo NCNN legge un buffer condiviso che contiene esclusivamente l'ultimo frame. L'app parte da My Apps → Run senza Codex, senza Python sul PC e senza cloud.

## Avvio

1. In Arduino App Lab scegliere My Apps → Create new app → Import App e importare `PO_Debris_AppLab.zip`. Sulla scheda di collaudo **PO-DEBRIS AI** è già installata.
2. Fermare altre app attive e altri processi che usano la IMX219. La vecchia `fish-recognition` è stata sospesa per lasciare libera la camera; i suoi file sono conservati.
3. Aprire **PO-DEBRIS AI** e premere **Run**. Aprire la WebUI indicata da App Lab, oppure `http://<IP UNO Q>:7000`. IP rilevato sulla scheda di prova: `<IP UNO Q>` (può cambiare). Con il forwarding USB di App Lab la porta è disponibile anche su http://127.0.0.1:7000.
4. Usare **Stop** per fermare app, worker NCNN e camera. App Lab permette una sola app attiva: non avviare Interfaccia durante questa demo.

La versione con periferiche include uno sketch applicativo STM32. Il suo caricamento deve essere autorizzato separatamente per rispettare il vincolo di non modificare firmware; nessun aggiornamento di bootloader, Zephyr di base, Linux o configurazione camera. La scheda di prova ha già Media Carrier / Camera0 configurati.

## Configurazione verificata

- IMX219: 1280×720, caps RGB con libcamera/GStreamer, poi BGR per NCNN.
- Input: 416×416 iniziale, batch 1; letterboxing conserva le proporzioni.
- Anteprima: 640×360, compressione JPEG, streaming MJPEG dal Brick WebUI.
- Confidence iniziale 0.55, IoU 0.50, modificabili dalla dashboard.
- Selettore 320 (FAST), 416 (DEFAULT), 640: ogni opzione usa un export NCNN compatibile, non una dimensione arbitraria applicata allo stesso grafo.
- Una sola inferenza per frame analizzato, mai inferenze simultanee. Frame vecchi scartati. Nessuna suddivisione o scansione multipla dell'immagine.
- Tracking e registrazione video disattivati. I contatori artificiali/naturali rappresentano gli oggetti nell'ultimo frame AI; non sono conteggi cumulativi di oggetti unici.
- La dashboard mostra FPS misurati di camera e AI separatamente, millisecondi di inferenza, classe e confidence. I box dell'ultima inferenza sono sovrapposti alla preview corrente e scadono dopo due secondi; non implicano una nuova inferenza su ogni frame video.
- Il CSV persistente in `data/<timestamp>/detections.csv` registra timestamp UTC, frame camera analizzato, classe, gruppo, confidence, box in pixel originali, input e latenza. Esportabile dalla WebUI.
- Le impostazioni salvate in `data/settings.json` persistono tra Stop/Run. Il pacchetto importato su una nuova app usa 416 / 0.55.

## Modello e classi

Il modello è `runs/rft_pretrained/weights/best.pt`: YOLO11n pretrained ufficiale, fine-tuning soltanto RFT su GPU T4 Colab, 101 epoche completate, best selezionato sulla validation all’epoca 76. Tutti gli export NCNN FP32 320/416/640 provengono dagli stessi nuovi pesi e hanno superato la verifica numerica PyTorch/NCNN. Pesi sorgente e SHA256 sono inclusi in `model/`. Il vecchio bootstrap è conservato separatamente per ripristino.

Classi: bottle, grass, branch, milk-box, plastic-bag, plastic-garbage, ball, leaf. Grass/branch/leaf sono naturali; le altre artificiali.

Test RFT congelato: 474 immagini, precision macro 70.34%, recall macro 74.00%, mAP50 74.56%, mAP50–95 45.78% a input 640. La classe grass resta debole (AP50 33.07%); la foto test_00000 conserva un falso negativo sul box annotato. Queste metriche non certificano l’accuratezza sul Po e non valgono automaticamente a 416/320. Il tiling resta disattivato. Report completo: MODEL_RECOVERY_RESULTS.md.

## Ambiente App Lab

**Stato dei nuovi pesi:** Nuovi pesi installati sulla UNO Q e verificati tramite SHA256. NCNN eseguito nel container Linux ARM64 sulle cinque immagini RFT (tre input); IMX219 live 1280×720, preview 640×360 e inferenza effettiva verificati. Avvio mediante Arduino App CLI, lo stesso backend App Lab; non è stato simulato un click sul pulsante Run dell’interfaccia desktop.

Verificato su Linux ARM64 UNO Q, App CLI 0.13.0, base ufficiale `ghcr.io/arduino/app-bricks/python-apps-base:0.12.0`, CPython 3.13.14. OpenCV 4.13 con GStreamer, NumPy e PyYAML sono forniti dalla base Arduino. `python/requirements.txt` documenta le dipendenze senza reinstallarle.

La wheel NCNN 1.0.20260526 CPython 3.13 / manylinux ARM64 ufficiale PyPI è inclusa in `vendor/`; `main.py` la installa offline nella venv con `--no-deps`, preservando l'OpenCV Arduino che supporta CSI. L'inferenza non richiede internet. Un nuovo dispositivo può richiedere internet solo per scaricare l'immagine base Arduino. Se una futura versione App Lab cambia Python, occorre la wheel per la nuova ABI e una nuova verifica.

`csi_capture.py` usa discovery e lifecycle della CSICamera Arduino, imponendo il formato RGB per evitare il problema DMA osservato con il default ABGR. Non modifica librerie installate, driver o hardware.

## Diagnostica e shell

In caso di camera occupata/scollegata lo stato segnala l'errore e riprova. Consultare i log Python in App Lab. Un FPS AI basso non deve bloccare la preview.

```sh
arduino-app-cli app start user:po-debris-ai -v
arduino-app-cli app stop user:po-debris-ai
arduino-app-cli app restart user:po-debris-ai -v
```

L'ID deriva dalla cartella radice `po-debris-ai` dello ZIP esportato ufficialmente.

## Fonti ufficiali

- https://github.com/arduino/arduino-app-cli/blob/main/docs/app-specification.md
- https://docs.arduino.cc/software/app-lab/
- https://github.com/arduino/app-bricks-py

Struttura: app.yaml, python/main.py, python/requirements.txt, assets/index.html, model/, vendor/. Dati di sessione e cache non sono distribuiti nel pacchetto.

## Integrazione periferiche

Configurazione in `config/peripherals.json`, sketch in `sketch/`, coordinatore `python/peripherals.py`. Confidence iniziale 0.55, due rilevazioni coerenti, trigger D2/manuale/controllo video periodico, camera sempre pronta, OLED aggiornato su cambiamenti e due servo D9/D10 in sequenza con cooldown. Nessun tiling. `servo_enabled` false fino alla verifica dell'alimentazione; OLED `unknown` fino all'identificazione del controller. Pesi e grafi YOLO restano identici.

Il codice Python è stato verificato sulla UNO Q con camera/AI reali e bridge MCU assente; il nuovo sketch è compilato ma non caricato. Non dichiarare i test fisici completati prima della loro reale esecuzione. Documentazione e comandi: `PERIPHERALS.md`; prove in `applab/peripheral_verification/` nel progetto PC.
