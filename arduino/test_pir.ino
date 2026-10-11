// Test PIR - HackTurin 2026
// Collega il PIR: VCC → 5V | GND → GND | OUT → Pin D2 (o D3)

#define PIN_PIR    2   // cambia in 3 se usi D3
#define LED_ALERT  13

void setup() {
  Serial.begin(9600);
  pinMode(PIN_PIR, INPUT);
  pinMode(LED_ALERT, OUTPUT);
  Serial.println("Test PIR avviato — in attesa di movimento...");
}

void loop() {
  if (digitalRead(PIN_PIR) == HIGH) {
    digitalWrite(LED_ALERT, HIGH);
    Serial.println("MOVIMENTO RILEVATO!");
  } else {
    digitalWrite(LED_ALERT, LOW);
    Serial.println("Nessun movimento");
  }
  delay(500);
}
