#include <Arduino.h>

void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println("Agent F fixture boot");
}

void loop() {
  Serial.println("tick");
  delay(1000);
}
