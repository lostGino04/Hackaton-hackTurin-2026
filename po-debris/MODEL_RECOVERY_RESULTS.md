# PO-DEBRIS — audit e nuovo training RFT

Il modello distribuito `runs/bootstrap/weights/best.pt` contiene **1 epoca effettiva**, inizializzazione `yolo11n.yaml` da zero. Non era il training definitivo. Il run CPU separato `runs/rft` è stato fermato dopo 19 epoche, preservando i suoi checkpoint.

Dataset: 1517 train / 224 validation / 474 test; 712 oggetti nel test. Tutti i 2215 abbinamenti immagine/annotazione verificati, valori originali preservati, nessuna rotazione EXIF non banale o immagine identica decodificata tra split. Il filtro precedente elimina anche quasi duplicati; non prova l’assenza di tutte le scene correlate. Dettagli in `outputs/model_audit/audit.json`.

Le 20 sovrapposizioni originali sono in `outputs/model_audit/20_original_annotations.jpg`; controllo semantico in `visual_review.md`. Alcune etichette originali sono incomplete. Non sono state corrette usando le predizioni.

Nuovo modello: YOLO11n pretrained ufficiale, fine-tuning esclusivamente RFT su Tesla T4 Colab, **101 epoche completate**, massimo 150/patience 25, input 640, AdamW, configurazione fissata prima del test in `configs/rft_pretrained.json`. Best selezionato sulla validation all’epoca **76** (mAP50=74.52%, mAP50–95=47.26%).

## Confronto sullo stesso test completo

| Metrica (%) | Bootstrap | Pretrained |
|---|---:|---:|
| Precision macro | 63.90 | 70.34 |
| Recall macro | 1.43 | 74.00 |
| mAP50 | 0.57 | 74.56 |
| mAP50–95 | 0.18 | 45.78 |

Precision/recall macro sono quelle Ultralytics al punto di massimo F1; non sono il risultato alla confidence 0.10. Nel bootstrap la precision macro è gonfiata dalla convenzione precision=1 per classi senza predizioni/recall=0. Il mAP e il confronto micro sotto evidenziano il problema.

## Stesse 30 immagini, confidence 0.10 e matching IoU 0.50

| Modello | TP | FP | FN | Precision micro | Recall micro |
|---|---:|---:|---:|---:|---:|
| Bootstrap | 1 | 11 | 40 | 8.33% | 2.44% |
| Pretrained | 36 | 38 | 5 | 48.65% | 87.80% |

## Metriche per classe sul test completo

| Classe | AP50 prima | AP50 dopo | Recall dopo |
|---|---:|---:|---:|
| bottle | 4.32% | 92.38% | 96.42% |
| grass | 0.00% | 33.07% | 31.43% |
| branch | 0.00% | 59.36% | 54.99% |
| milk-box | 0.22% | 85.01% | 84.31% |
| plastic-bag | 0.02% | 83.31% | 74.99% |
| plastic-garbage | 0.00% | 79.41% | 83.88% |
| ball | 0.00% | 94.79% | 100.00% |
| leaf | 0.00% | 69.18% | 66.00% |

Le cinque immagini mostrate sono le prime cinque della lista congelata di 30; nessuna selezione in base alla qualità delle predizioni. File originali annotati in `runs/pretrained_test/comparison_30/`, tavola `outputs/model_audit/five_new_test_predictions.jpg`. Confusion matrix: `runs/pretrained_test/confusion_matrix.png`.

La valutazione dimostra generalizzazione sui file RFT tenuti fuori dal training, con i limiti delle annotazioni e delle scene correlate. Non certifica la precisione su nuove foto annotate del Po riprese dal ponte. Input live ridotti a 416/320 possono perdere piccoli oggetti; mAP riportato qui è a 640. Nessun tiling.

Deployment e velocità sono riportati separatamente solo dopo il collaudo effettivo. Pesi: `runs/rft_pretrained/weights/best.pt`; provenienza iniziale: `logs/pretrained-provenance.json`; risultati numerici: `outputs/model_audit/comparison.json`.

## Foto diagnostica originale grass

Il nuovo modello rileva grass in altre zone di test_00000.jpg (massima confidence 0.563), ma IoU massima con il box grass originale è 0. Il caso annotato resta un falso negativo a confidence 0.10/input 640. Non va dichiarato risolto. 123 istanze grass nel training, contro 1041 bottle; qualità e delimitazione della vegetazione originale sono un limite. Non sono stati scelti nuovi iperparametri usando questo test.

## Artefatti e deployment effettivo

Pesi nuovi SHA256: `bd23f47d3087a49200113843fa6b6243af6909e13a15db560e57d470b7402bdb`. Download Colab verificato per hash e caricamento YOLO. Log completo delle 101 epoche: `logs/colab-training-completed.log`.

Export NCNN FP32 batch 1 a 320/416/640: tutti verificati numericamente PyTorch/NCNN, dettaglio `applab/recovery_exports/verified.json`. Inoltre i tre export sono stati realmente eseguiti sul PC sulle cinque immagini congelate, 15 inferenze senza tiling, con bounding box nelle coordinate originali: `outputs/ncnn_new_pc/probe.json`. Questo test AMD64 non è una prova ARM64 né un benchmark UNO Q.

App nativa aggiornata in `applab/PO_Debris_AI`; ZIP `applab/PO_Debris_AppLab.zip`, struttura App Lab, CRC e SHA256 di tutti i modelli inclusi verificati. Stato del pacchetto: `applab/recovery_verification/package.json`. Vecchio ZIP e sorgenti conservati separatamente.

**Installazione e prova hardware completate:** Nuovi pesi installati sulla UNO Q e verificati tramite SHA256. NCNN eseguito nel container Linux ARM64 sulle cinque immagini RFT (tre input); IMX219 live 1280×720, preview 640×360 e inferenza effettiva verificati. Avvio mediante Arduino App CLI, lo stesso backend App Lab; non è stato simulato un click sul pulsante Run dell’interfaccia desktop.

| Input | AI FPS prima | AI FPS dopo | Inferenza dopo (ms) | Camera FPS dopo | Preview FPS dopo |
|---|---:|---:|---:|---:|---:|
| 320 | 3.10 | 3.49 | 254.63 | 28.37 | 21.02 |
| 416 | 2.09 | 2.36 | 380.23 | 28.40 | 21.05 |
| 640 | 1.10 | 1.09 | 908.98 | 28.07 | 20.85 |

Campioni per input circa 22 secondi, confidence 0.35, IoU 0.50. Latenza comprende NCNN e NMS. Sono misure di sessioni diverse, non un confronto controllato di carico/temperatura. Input finale 416; nessun tiling, tracking o registrazione. Camera separata dall’unico worker AI, ultimo frame soltanto. Le scene live di collaudo non certificano accuratezza sui detriti del Po.

## Importazione e scena live finale

Importazione ufficiale dello ZIP realmente eseguita: copia temporanea `user:po-debris-ai-20261010-190634`, avvio in container nuovo, IMX219 e AI funzionanti. Prova `import-verified.json`. Copia fermata e conservata nel backup `imported-app-validated.tgz`, poi rimossa da My Apps; app principale ripristinata e attiva. Non è stato usato il pulsante UI Import/Run del desktop, ma i comandi ufficiali dello stesso backend.

Durante il benchmark l'obiettivo era coperto: frame quasi neri. Dopo la rimozione del copriobiettivo da parte dell'utente, immagine reale visibile verificata (`camera-visible.jpg`, luminosità media 44.84/255, massimo 209), camera 28.69 FPS e AI 2.05 FPS a 416 in quel campione. Le misure del benchmark tabellare riguardano la scena scura, non una scena con molti oggetti. Nessun detrito è stato presentato alla camera durante questa prova; i box sono stati verificati separatamente su immagini RFT nella UNO Q.
