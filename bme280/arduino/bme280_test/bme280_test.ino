/*
 * BME280 Test - Diagnóstico simple
 * Prueba la conexión con el sensor BME280
 */

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>

#define SEALEVELPRESSURE_HPA (1013.25)

Adafruit_BME280 bme;

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);
  
  Serial.println("=== BME280 Test ===");
  Serial.println("Iniciando Wire...");
  Wire.begin();
  delay(100);
  
  // Escanear I2C primero
  Serial.println("Escaneando I2C...");
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print("Dispositivo en: 0x");
      if (addr < 16) Serial.print("0");
      Serial.println(addr, HEX);
    }
  }
  
  Serial.println("\nIntentando inicializar BME280...");
  
  // Probar dirección 0x76
  Serial.print("Probando 0x76... ");
  if (bme.begin(0x76)) {
    Serial.println("OK!");
  } else {
    Serial.println("FALLO");
    
    // Probar dirección 0x77
    Serial.print("Probando 0x77... ");
    if (bme.begin(0x77)) {
      Serial.println("OK!");
    } else {
      Serial.println("FALLO");
      Serial.println("\nERROR: No se pudo inicializar el BME280");
      Serial.println("Verifica:");
      Serial.println("  1. Conexiones VCC, GND, SDA, SCL");
      Serial.println("  2. Que sea un BME280 (no BMP280)");
      Serial.println("  3. Voltaje de alimentación (3.3V)");
      while (1) {
        delay(1000);
        Serial.println("Reintentando...");
        if (bme.begin(0x76) || bme.begin(0x77)) {
          Serial.println("BME280 encontrado!");
          break;
        }
      }
    }
  }
  
  Serial.println("\n=== BME280 Listo! Enviando datos... ===\n");
}

void loop() {
  float temp = bme.readTemperature();
  float hum = bme.readHumidity();
  float pres = bme.readPressure() / 100.0F;
  float alt = bme.readAltitude(SEALEVELPRESSURE_HPA);
  
  // Formato compatible con el dashboard
  Serial.print("temp=");
  Serial.print(temp, 2);
  Serial.print(",hum=");
  Serial.print(hum, 2);
  Serial.print(",pres=");
  Serial.print(pres, 2);
  Serial.print(",alt=");
  Serial.println(alt, 2);
  
  delay(1000);
}
