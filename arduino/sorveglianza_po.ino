// ============================================================
// Sistema di Sorveglianza Murazzi - HackTurin 2026
// Hardware: Arduino UNO Q + Arduino Media Carrier
// Comunicazione con Python via Bridge (Arduino_RouterBridge)
//
// COLLEGAMENTO:
//   Modulino Distance  → connettore Qwiic della Media Carrier
//   PIR                → connettore Grove D2
//   LED ROSSO          → Pin 3
//   LED GIALLO         → Pin 4
//   LED VERDE          → Pin 5
//   Servo paratia SX   → Pin 9  | VCC → 5V | GND → GND
//   Servo paratia DX   → Pin 10 | VCC → 5V | GND → GND
//   Servo barriera     → Pin 11 | VCC → 5V | GND → GND
//
// LIBRERIE NECESSARIE:
//   - Arduino_RouterBridge  (by Arduino)
//   - Modulino              (by Arduino)
//   - Servo                 (inclusa nell'IDE)
// ============================================================

#include "Arduino_RouterBridge.h"
#include <Modulino.h>
#include <Servo.h>

// --- MODULINO ---
ModulinoDistance distance;

// --- PIR ---
#define PIN_PIR   2

// --- LED ---
#define LED_ROSSO   3
#define LED_GIALLO  4
#define LED_VERDE   5

// --- SERVO PARATIE ---
Servo servoSX;
Servo servoDX;
#define PIN_SERVO_SX        9
#define PIN_SERVO_DX        10
#define PARATIA_RIPOSO      90
#define PARATIA_SX_CHIUSA   45
#define PARATIA_DX_CHIUSA   135
#define PARATIA_DURATA_MS   30000

// --- SERVO BARRIERA ---
Servo servoBarriera;
#define PIN_SERVO_BARRIERA  11
#define BARRIERA_GIU        0
#define BARRIERA_SU         90
bool barriera_alzata = false;

// --- SOGLIE ---
#define SOGLIA_PIENA_MM       200
#define SOGLIA_ATTENZIONE_MM  1000

// --- TIMING ---
#define INTERVALLO_MS     1000
#define TIMEOUT_PIR_MS    8000

// --- STATO GLOBALE (letto da Python via Bridge) ---
int   g_distanza_mm    = -1;
int   g_movimento      = 0;
char  g_livello[12]    = "NORMALE";

unsigned long ultimo_loop = 0;
unsigned long ultimo_pir  = 0;

// ============================================================
// FUNZIONI BRIDGE — chiamate da Python
// ============================================================

// Python chiama get_distanza() → restituisce distanza in mm
int get_distanza() {
  return g_distanza_mm;
}

// Python chiama get_movimento() → 1 se c'è movimento, 0 altrimenti
int get_movimento() {
  return g_movimento;
}

// Python chiama get_livello() → "NORMALE" / "ATTENZIONE" / "PIENA"
const char* get_livello() {
  return g_livello;
}

// Python chiama attiva_paratie() quando AI rileva detriti
void attiva_paratie() {
  servoSX.write(PARATIA_SX_CHIUSA);
  servoDX.write(PARATIA_DX_CHIUSA);
  Monitor.println("PARATIE_CHIUSE");
  delay(PARATIA_DURATA_MS);
  servoSX.write(PARATIA_RIPOSO);
  servoDX.write(PARATIA_RIPOSO);
  Monitor.println("PARATIE_APERTE");
}

// ============================================================
void setup() {
  Bridge.begin();
  Monitor.begin();

  Modulino.begin();
  distance.begin();

  pinMode(PIN_PIR,    INPUT);
  pinMode(LED_ROSSO,  OUTPUT);
  pinMode(LED_GIALLO, OUTPUT);
  pinMode(LED_VERDE,  OUTPUT);

  servoSX.attach(PIN_SERVO_SX);
  servoDX.attach(PIN_SERVO_DX);
  servoSX.write(PARATIA_RIPOSO);
  servoDX.write(PARATIA_RIPOSO);

  servoBarriera.attach(PIN_SERVO_BARRIERA);
  servoBarriera.write(BARRIERA_GIU);

  // Registra le funzioni chiamabili da Python
  Bridge.provide_safe("get_distanza",   get_distanza);
  Bridge.provide_safe("get_movimento",  get_movimento);
  Bridge.provide_safe("get_livello",    get_livello);
  Bridge.provide_safe("attiva_paratie", attiva_paratie);

  Monitor.println("=== Sistema Murazzi Po - HackTurin 2026 ===");
  Monitor.println("Bridge pronto");
}

// ============================================================
void loop() {
  unsigned long ora = millis();
  if (ora - ultimo_loop < INTERVALLO_MS) return;
  ultimo_loop = ora;

  // Lettura distanza
  if (distance.available()) {
    g_distanza_mm = distance.get();
  }

  // Lettura PIR
  if (digitalRead(PIN_PIR) == HIGH) {
    ultimo_pir = ora;
  }
  g_movimento = (ora - ultimo_pir < TIMEOUT_PIR_MS) ? 1 : 0;

  // Valuta livello
  if (g_distanza_mm < 0) {
    strcpy(g_livello, "ERRORE");
  } else if (g_distanza_mm <= SOGLIA_PIENA_MM) {
    strcpy(g_livello, "PIENA");
  } else if (g_distanza_mm <= SOGLIA_ATTENZIONE_MM) {
    strcpy(g_livello, "ATTENZIONE");
  } else {
    strcpy(g_livello, "NORMALE");
  }

  // LED semaforo
  digitalWrite(LED_ROSSO,  LOW);
  digitalWrite(LED_GIALLO, LOW);
  digitalWrite(LED_VERDE,  LOW);

  if (strcmp(g_livello, "NORMALE") == 0) {
    digitalWrite(LED_VERDE, HIGH);
  } else if (strcmp(g_livello, "ATTENZIONE") == 0) {
    digitalWrite(LED_GIALLO, HIGH);
  } else if (strcmp(g_livello, "PIENA") == 0) {
    digitalWrite(LED_ROSSO, HIGH);
    // Gestione barriera
    if (!barriera_alzata) {
      servoBarriera.write(BARRIERA_SU);
      barriera_alzata = true;
      Monitor.println("BARRIERA_ALZATA");
    }
  }

  if (strcmp(g_livello, "NORMALE") == 0 && barriera_alzata) {
    servoBarriera.write(BARRIERA_GIU);
    barriera_alzata = false;
    Monitor.println("BARRIERA_ABBASSATA");
  }
}
