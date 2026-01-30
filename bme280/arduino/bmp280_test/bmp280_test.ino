/*
 * BMP280 Test - Probando si es un BMP280 en lugar de BME280
 * El BMP280 es similar pero NO tiene sensor de humedad
 */

#include <Wire.h>
#include <Adafruit_BMP280.h>

Adafruit_BMP280 bmp;

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);
  
  Serial.println("=== Test BMP280 vs BME280 ===");
  Wire.begin();
  delay(100);
  
  // Escanear I2C
  Serial.println("Escaneando I2C...");
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print("Dispositivo en: 0x");
      if (addr < 16) Serial.print("0");
      Serial.println(addr, HEX);
    }
  }
  
  Serial.println("\nProbando con libreria BMP280...");
  
  // El BMP280 puede estar en 0x76 o 0x77
  if (bmp.begin(0x76)) {
    Serial.println("BMP280 encontrado en 0x76!");
  } else if (bmp.begin(0x77)) {
    Serial.println("BMP280 encontrado en 0x77!");
  } else {
    Serial.println("ERROR: Ni BME280 ni BMP280 detectado");
    Serial.println("El sensor puede estar dañado o mal conectado");
    while(1) delay(1000);
  }
  
  // Configuración del sensor
  bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                  Adafruit_BMP280::SAMPLING_X2,
                  Adafruit_BMP280::SAMPLING_X16,
                  Adafruit_BMP280::FILTER_X16,
                  Adafruit_BMP280::STANDBY_MS_500);
  
  Serial.println("\n=== Sensor Listo! ===\n");
  Serial.println("NOTA: Si esto funciona, tienes un BMP280 (sin humedad)");
  Serial.println("      no un BME280\n");
}

void loop() {
  float temp = bmp.readTemperature();
  float pres = bmp.readPressure() / 100.0F;
  float alt = bmp.readAltitude(1013.25);
  
  // Formato compatible con dashboard (humedad siempre 0)
  Serial.print("temp=");
  Serial.print(temp, 2);
  Serial.print(",hum=0.00");  // BMP280 no tiene humedad
  Serial.print(",pres=");
  Serial.print(pres, 2);
  Serial.print(",alt=");
  Serial.println(alt, 2);
  
  delay(1000);
}
