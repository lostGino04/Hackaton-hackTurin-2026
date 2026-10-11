# PO-DEBRIS AI — componente AI del team

Applicazione Arduino App Lab per UNO Q 4 GB: inferenza YOLO11n NCNN sul processore Linux ARM64, camera CSI Sony IMX219 su Media Carrier, otto classi RFT. Modello già addestrato incluso; nessun training necessario. Una sola inferenza per frame, buffer dell'ultimo frame, tiling disattivato.

## Avvio e versioni

- `packages/PO_Debris_AppLab.zip`: versione camera/AI senza sketch periferiche, già verificata sulla UNO Q. Importare da My Apps → Create new app → Import App, fermare altre app che usano la camera, premere Run. Aprire la WebUI porta 7000 indicata da App Lab.
- `packages/PO_Debris_AppLab_Peripherals.zip`: integrazione periferiche, con sketch STM32 compilato ma NON caricato né collaudato fisicamente. Il suo Run può programmare lo sketch: non usarlo finché non è autorizzato il caricamento applicativo e verificata la conservazione del firmware base.
- `app/`: sorgenti modificabili della versione periferiche, `app.yaml`, `python/`, `sketch/`, `assets/`, `config/`, modello PT e tre export NCNN, wheel ARM64 inclusa per installazione offline.

La versione periferiche usa soglia iniziale 0.55, due rilevazioni coerenti, controllo periodico ogni 8 secondi e trigger manuale/PIR. Camera e preview rimangono attive in standby. I guasti MCU, OLED o ToF non arrestano l'AI. Servo inizialmente DISABILITATI.

## Integrazione con il resto del team

Questa cartella è autonoma; `../arduino` e `../python` restano quelli del team. NON eseguire i due sketch contemporaneamente sullo stesso STM32: occorre unificare il codice applicativo. Gli endpoint RouterBridge sono definiti in `app/sketch/sketch.ino`; Python li chiama da `app/python/peripherals.py`, con timeout di un secondo. YOLO resta nel container Linux, sensori e attuatori nello STM32.

Collegamenti previsti qui: movimento D2, SG90 D9 e D10, OLED su Wire (D20/D21), ToF individuato su Wire/Wire1 (Qwiic). Non sono i pin 7/5/6 indicati nel README principale del team. Camera IMX219 CSI, non webcam USB. Verificare le sigle reali: D2 non è ancora identificato fisicamente; ToF abilita Arduino_Modulino solo per chip compatibile; OLED rimane disabilitato finché è scelto il controller. Alimentazione dei servo e massa comune da verificare, movimenti iniziali 5 gradi, separati.

Le otto classi sono bottle, grass, branch, milk-box, plastic-bag, plastic-garbage, ball, leaf. Questo modello non ha una classe imbarcazione e non può implementare da solo il comportamento relativo alle barche descritto dal team.

## Comandi manuali

Da PC con Python 3: `python tools/peripheral_cli.py status --url http://<IP_UNO_Q>:7000`. Sostituire status con trigger, scan, oled, servo1, servo2 o cycle. Servo1/servo2/cycle richiedono l'abilitazione dopo la verifica dell'alimentazione. `config --values` accetta JSON; dettagli e API in [app/PERIPHERALS.md](app/PERIPHERALS.md).

## Verifiche e limiti reali

Camera live 1280×720, preview 640×360, NCNN nel container UNO Q, tre input 320/416/640 e pesi confrontati via SHA256 già verificati. Camera circa 28 FPS; AI attiva circa 2 FPS a 416 nella prova, dipendente da carico e scena. Trigger manuale/periodico e fallback senza servizi STM32 verificati. Sei test software del coordinatore: `python -m unittest discover -s tests`.

Sketch compilato con core Arduino Zephyr 1.0.0 / UNO Q e dipendenze pinning in `app/sketch/sketch.yaml`. D2 HIGH/LOW, ToF, OLED, servo D9/D10 e azione fisica da YOLO NON ancora verificati: nessun upload MCU effettuato. Nessuna modifica Linux, bootloader o firmware base. Prima del Run con sketch verificare che App Lab non tenti un aggiornamento automatico del firmware base. Non confondere compilazione con funzionamento hardware.

Test RFT completo: 474 immagini, precision macro 70.34%, recall 74.00%, mAP50 74.56%, mAP50–95 45.78% a 640. Non misura l'accuratezza sul Po né automaticamente a 320/416; grass resta debole. [Report](MODEL_RECOVERY_RESULTS.md). Modello sorgente SHA256: `bd23f47d3087a49200113843fa6b6243af6909e13a15db560e57d470b7402bdb`.

Dataset e ambiente Windows non inclusi; solo codice di deployment, pesi, pacchetti e documentazione. Licenze delle dipendenze e condizioni del dataset RFT restano applicabili; nessuna nuova licenza è attribuita ai componenti di terzi.
