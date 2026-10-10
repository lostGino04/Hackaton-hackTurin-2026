// ============================================================
// Sistema di Sorveglianza Murazzi - HackTurin 2026
// Hardware: Arduino UNO Q + Arduino Media Carrier
// Modulino Distance  (VL53L4CD  - Time of Flight, I2C/Qwiic)
// Sensore movimento  PIR (HC-SR501 o compatibile)
// Servo SG90 x2 (barriera murazzi + paratia detriti)
//
// COLLEGAMENTO:
//   Modulino Distance  → connettore Qwiic della Media Carrier
//   PIR OUT            → Pin 7 | VCC → 5V | GND → GND
//   Servo barriera     → Pin 5 | VCC → 5V | GND → GND
//   Servo paratia      → Pin 6 | VCC → 5V | GND → GND
//   LED alert          → Pin 13 (integrato)
//
// LIBRERIE NECESSARIE (Arduino IDE → Gestione librerie):
//   - Modulino  (by Arduino)
//   - Servo     (inclusa nell'IDE)
// ============================================================

#include <Modulino.h>
#include <Servo.h>

// --- OGGETTI MODULINO ---
ModulinoDistance distance;   // VL53L4CD - livello acqua

// --- SENSORE MOVIMENTO PIR ---
#define PIN_PIR   7

// --- SERVO ---
Servo servoBarriera;
Servo servoParatia;

#define PIN_SERVO_BARRIERA  5
#define PIN_SERVO_PARATIA   6
#define LED_ALERT           13

// --- SOGLIE LIVELLO ACQUA ---
// Il VL53L4CD misura in millimetri (range 0-1200mm)
// Più l'acqua sale, più la distanza DIMINUISCE
#define SOGLIA_PIENA_MM       200   // < 200mm (~20cm) → piena, barriera su
#define SOGLIA_ATTENZIONE_MM  400   // < 400mm (~40cm) → attenzione

// --- POSIZIONI SERVO ---
#define BARRIERA_GIU        0    // barriera abbassata (accesso libero)
#define BARRIERA_SU         90   // barriera alzata (accesso bloccato)
#define PARATIA_RIPOSO      90   // paratia neutra
#define PARATIA_SINISTRA    45   // devia detriti da sinistra verso centro
#define PARATIA_DESTRA      135  // devia detriti da destra verso centro
#define PARATIA_DURATA_MS   3000 // ms in posizione prima di tornare a riposo

// --- TIMING ---
#define INTERVALLO_MS         1000  // lettura sensori ogni secondo
#define TIMEOUT_PIR_MS        8000  // PIR rimane "attivo" per 8 secondi

// --- VARIABILI ---
bool     barriera_alzata   = false;
bool     movimento_attivo  = false;
unsigned long ultimo_loop  = 0;
unsigned long ultimo_pir   = 0;

// ============================================================
void setup() {
  Serial.begin(9600);

  // Inizializza bus I2C e Modulino
  Modulino.begin();
  distance.begin();

  // PIR
  pinMode(PIN_PIR, INPUT);

  // Servo
  servoBarriera.attach(PIN_SERVO_BARRIERA);
  servoParatia.attach(PIN_SERVO_PARATIA);
  servoBarriera.write(BARRIERA_GIU);
  servoParatia.write(PARATIA_RIPOSO);

  pinMode(LED_ALERT, OUTPUT);

  Serial.println("=== Sistema Murazzi Po - HackTurin 2026 ===");
  Serial.println("PRONTO");
}

// ============================================================
void loop() {
  unsigned long ora = millis();

  if (ora - ultimo_loop < INTERVALLO_MS) return;
  ultimo_loop = ora;

  // --- 1. LETTURA DISTANZA (livello acqua) ---
  int distanza_mm = -1;
  if (distance.available()) {
    distanza_mm = distance.get();  // valore in mm
  }

  String livello = valuta_livello(distanza_mm);

  // --- 2. LETTURA PIR ---
  if (digitalRead(PIN_PIR) == HIGH) {
    ultimo_pir = ora;
  }
  // Rimane "attivo" per TIMEOUT_PIR_MS dopo l'ultimo rilevamento
  movimento_attivo = (ora - ultimo_pir < TIMEOUT_PIR_MS);

  // --- 3. GESTIONE BARRIERA MURAZZI ---
  gestisci_barriera(livello);

  // --- 4. INVIA STATO A PYTHON ---
  invia_stato(ora, distanza_mm, livello, movimento_attivo);

  // --- 5. LEGGI COMANDI DA PYTHON (AI camera) ---
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    gestisci_comando_ai(cmd);
  }
}

// ============================================================
// Valuta livello acqua in base alla distanza
// ============================================================
String valuta_livello(int dist_mm) {
  if (dist_mm < 0)                      return "ERRORE";
  if (dist_mm <= SOGLIA_PIENA_MM)       return "PIENA";
  if (dist_mm <= SOGLIA_ATTENZIONE_MM)  return "ATTENZIONE";
  return "NORMALE";
}

// ============================================================
// Gestisce la barriera murazzi (servo + LED)
// ============================================================
void gestisci_barriera(String livello) {
  if (livello == "PIENA" && !barriera_alzata) {
    servoBarriera.write(BARRIERA_SU);
    barriera_alzata = true;
    digitalWrite(LED_ALERT, HIGH);
    Serial.println("CMD:BARRIERA_ALZATA");

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
// Riceve comandi da Python dopo analisi AI camera
// ============================================================
void gestisci_comando_ai(String cmd) {
  if (cmd == "DETRITO_SX") {
    servoParatia.write(PARATIA_SINISTRA);
    Serial.println("CMD:PARATIA_SX");
    delay(PARATIA_DURATA_MS);
    servoParatia.write(PARATIA_RIPOSO);
    Serial.println("CMD:PARATIA_RIPOSO");

  } else if (cmd == "DETRITO_DX") {
    servoParatia.write(PARATIA_DESTRA);
    Serial.println("CMD:PARATIA_DX");
    delay(PARATIA_DURATA_MS);
    servoParatia.write(PARATIA_RIPOSO);
    Serial.println("CMD:PARATIA_RIPOSO");

  } else if (cmd == "IMBARCAZIONE") {
    Serial.println("CMD:IMBARCAZIONE_OK");
  }
}

// ============================================================
// Invia stato CSV a Python
// Formato: DATI:timestamp,distanza_mm,livello,movimento,barriera
// ============================================================
void invia_stato(unsigned long ts, int dist, String livello, bool mov) {
  Serial.print("DATI:");
  Serial.print(ts);       Serial.print(",");
  Serial.print(dist);     Serial.print(",");
  Serial.print(livello);  Serial.print(",");
  Serial.print(mov ? "1" : "0"); Serial.print(",");
  Serial.println(barriera_alzata ? "1" : "0");
}
