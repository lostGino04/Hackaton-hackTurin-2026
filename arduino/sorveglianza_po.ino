// ============================================================
// Sistema di Sorveglianza Murazzi - HackTurin 2026
// Hardware: Arduino UNO Q
// Sensori: HC-SR04 (livello acqua), PIR (movimento)
// Attuatori: 2x Servo SG90 (barriera murazzi + paratia detriti)
// ============================================================
//
// PINOUT:
//   HC-SR04  TRIG → Pin 9
//   HC-SR04  ECHO → Pin 8
//   PIR OUT       → Pin 7
//   Servo BARRIERA → Pin 5  (alza barriera murazzi se piena)
//   Servo PARATIA  → Pin 6  (direziona detriti al centro)
//   LED ALERT      → Pin 13 (LED integrato)
//
// COLLEGAMENTO SERVO SG90:
//   Filo rosso   → 5V
//   Filo marrone → GND
//   Filo arancio → Pin segnale (5 o 6)
// ============================================================

#include <Servo.h>

// --- PIN ---
#define TRIG_PIN        9
#define ECHO_PIN        8
#define PIR_PIN         7
#define PIN_SERVO_BARRIERA 5
#define PIN_SERVO_PARATIA  6
#define LED_ALERT       13

// --- SOGLIE LIVELLO ACQUA ---
// Distanza misurata dall'HC-SR04 al pelo dell'acqua.
// Più l'acqua sale, più la distanza DIMINUISCE.
#define SOGLIA_PIENA_CM      20   // < 20cm → piena, barriera su
#define SOGLIA_ATTENZIONE_CM 40   // < 40cm → attenzione

// --- POSIZIONI SERVO BARRIERA (stampa 3D) ---
#define BARRIERA_GIU   0    // gradi → barriera abbassata (accesso libero)
#define BARRIERA_SU    90   // gradi → barriera alzata (accesso bloccato)

// --- POSIZIONI SERVO PARATIA (flipper stampa 3D) ---
#define PARATIA_RIPOSO  90  // gradi → posizione neutra
#define PARATIA_SINISTRA 45 // gradi → devia detriti da sinistra verso centro
#define PARATIA_DESTRA  135 // gradi → devia detriti da destra verso centro
#define PARATIA_DURATA  3000 // ms → quanto resta in posizione prima di tornare

// --- TIMING ---
#define INTERVALLO_SENSORI_MS  1000  // lettura sensori ogni secondo
#define TIMEOUT_PIR_MS        10000  // PIR rimane "attivo" per 10 secondi

// --- COMANDI DA PYTHON (via Serial) ---
// Python manda questi comandi dopo l'analisi AI della camera:
// "DETRITO_SX"  → paratia verso sinistra (detrito arriva da sinistra)
// "DETRITO_DX"  → paratia verso destra
// "IMBARCAZIONE" → nessuna azione meccanica, solo log

// ============================================================
Servo servoBarriera;
Servo servoParatia;

float    distanza_cm        = 0;
bool     movimento_rilevato = false;
bool     barriera_alzata    = false;
unsigned long ultimo_sensore  = 0;
unsigned long ultimo_pir      = 0;

// ============================================================
void setup() {
  Serial.begin(9600);

  pinMode(TRIG_PIN,  OUTPUT);
  pinMode(ECHO_PIN,  INPUT);
  pinMode(PIR_PIN,   INPUT);
  pinMode(LED_ALERT, OUTPUT);

  servoBarriera.attach(PIN_SERVO_BARRIERA);
  servoParatia.attach(PIN_SERVO_PARATIA);

  // Posizione iniziale
  servoBarriera.write(BARRIERA_GIU);
  servoParatia.write(PARATIA_RIPOSO);
  barriera_alzata = false;

  Serial.println("=== Sistema Murazzi Po - HackTurin 2026 ===");
  Serial.println("PRONTO");
}

// ============================================================
void loop() {
  unsigned long ora = millis();

  // 1. Lettura sensori a intervallo regolare
  if (ora - ultimo_sensore >= INTERVALLO_SENSORI_MS) {
    ultimo_sensore = ora;

    distanza_cm       = leggi_distanza();
    movimento_rilevato = leggi_pir(ora);

    String livello = valuta_livello(distanza_cm);

    // 2. Gestione barriera murazzi
    gestisci_barriera(livello);

    // 3. Invia stato a Python
    invia_stato(ora, distanza_cm, livello, movimento_rilevato);
  }

  // 4. Leggi comandi da Python (AI camera)
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();
    gestisci_comando_ai(comando);
  }
}

// ============================================================
// Misura distanza con HC-SR04
// ============================================================
float leggi_distanza() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long durata = pulseIn(ECHO_PIN, HIGH, 30000);
  if (durata == 0) return -1;

  return (durata * 0.0343) / 2.0;
}

// ============================================================
// Legge il PIR con timeout (evita falsi continui)
// ============================================================
bool leggi_pir(unsigned long ora) {
  if (digitalRead(PIR_PIN) == HIGH) {
    ultimo_pir = ora;
    return true;
  }
  // Rimane "attivo" per TIMEOUT_PIR_MS dopo l'ultimo rilevamento
  return (ora - ultimo_pir < TIMEOUT_PIR_MS);
}

// ============================================================
// Valuta livello acqua
// ============================================================
String valuta_livello(float dist) {
  if (dist < 0)                        return "ERRORE";
  if (dist <= SOGLIA_PIENA_CM)         return "PIENA";
  if (dist <= SOGLIA_ATTENZIONE_CM)    return "ATTENZIONE";
  return "NORMALE";
}

// ============================================================
// Gestisce la barriera murazzi (stampa 3D + servo)
// ============================================================
void gestisci_barriera(String livello) {
  if (livello == "PIENA" && !barriera_alzata) {
    servoBarriera.write(BARRIERA_SU);
    barriera_alzata = true;
    digitalWrite(LED_ALERT, HIGH);
    Serial.println("CMD:BARRIERA_ALZATA");  // notifica Python

  } else if (livello == "NORMALE" && barriera_alzata) {
    servoBarriera.write(BARRIERA_GIU);
    barriera_alzata = false;
    digitalWrite(LED_ALERT, LOW);
    Serial.println("CMD:BARRIERA_ABBASSATA");
  }

  // LED lampeggia in ATTENZIONE
  if (livello == "ATTENZIONE") {
    digitalWrite(LED_ALERT, (millis() / 500) % 2);
  }
}

// ============================================================
// Riceve comandi dall'AI Python e aziona la paratia
// ============================================================
void gestisci_comando_ai(String cmd) {
  if (cmd == "DETRITO_SX") {
    // Detrito arriva da sinistra → paratia inclina verso sinistra
    // per spingere il detrito verso il centro del fiume
    servoParatia.write(PARATIA_SINISTRA);
    Serial.println("CMD:PARATIA_SX");
    delay(PARATIA_DURATA);
    servoParatia.write(PARATIA_RIPOSO);
    Serial.println("CMD:PARATIA_RIPOSO");

  } else if (cmd == "DETRITO_DX") {
    // Detrito arriva da destra → paratia inclina verso destra
    servoParatia.write(PARATIA_DESTRA);
    Serial.println("CMD:PARATIA_DX");
    delay(PARATIA_DURATA);
    servoParatia.write(PARATIA_RIPOSO);
    Serial.println("CMD:PARATIA_RIPOSO");

  } else if (cmd == "IMBARCAZIONE") {
    // Imbarcazione rilevata: nessuna azione meccanica
    Serial.println("CMD:IMBARCAZIONE_OK");
  }
}

// ============================================================
// Invia stato CSV a Python ogni secondo
// Formato: timestamp,distanza_cm,livello,movimento,barriera
// ============================================================
void invia_stato(unsigned long ts, float dist, String livello, bool mov) {
  Serial.print("DATI:");
  Serial.print(ts);       Serial.print(",");
  Serial.print(dist);     Serial.print(",");
  Serial.print(livello);  Serial.print(",");
  Serial.print(mov ? "1" : "0"); Serial.print(",");
  Serial.println(barriera_alzata ? "1" : "0");
}
