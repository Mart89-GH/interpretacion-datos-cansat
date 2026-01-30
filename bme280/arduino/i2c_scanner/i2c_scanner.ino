// I2C Scanner - Detecta dispositivos en el bus I2C
#include <Wire.h>

void setup() {
  Wire.begin();
  Serial.begin(115200);
  while (!Serial);
  Serial.println("I2C Scanner - Buscando dispositivos...");
}

void loop() {
  byte count = 0;
  
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print("Dispositivo encontrado en: 0x");
      if (addr < 16) Serial.print("0");
      Serial.println(addr, HEX);
      count++;
    }
  }
  
  if (count == 0) {
    Serial.println("NO HAY DISPOSITIVOS I2C DETECTADOS");
  } else {
    Serial.print("Total dispositivos: ");
    Serial.println(count);
  }
  
  Serial.println("---");
  delay(3000);
}
