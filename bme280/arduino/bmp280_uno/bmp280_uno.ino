/*
 * BMP280 Data Node - Arduino UNO R3
 * Lee el sensor y envía datos formateados por Serial
 * Formato: CANSAT,id,temp,pres,alt,hum,ms
 * 
 * Conectar:
 *   VCC  -> 3.3V
 *   GND  -> GND
 *   SDA  -> A4
 *   SCL  -> A5
 *   
 *   TX (Pin 1) -> Arduino R4 RX (Pin 0)
 *   GND        -> Arduino R4 GND
 */

#include <Wire.h>
#include <Adafruit_BMP280.h>

Adafruit_BMP280 bmp;
unsigned long packetId = 0;

void setup() {
  Serial.begin(9600);
  while(!Serial);
  
  // Inicializar BMP280
  if (!bmp.begin(0x76) && !bmp.begin(0x77)) {
    Serial.println("ER,Sensor no encontrado");
    while (1);
  }

  // Configuración
  bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                  Adafruit_BMP280::SAMPLING_X2,
                  Adafruit_BMP280::SAMPLING_X16,
                  Adafruit_BMP280::FILTER_X16,
                  Adafruit_BMP280::STANDBY_MS_500);
}

void loop() {
  float temp = bmp.readTemperature();
  float pres = bmp.readPressure() / 100.0;
  float alt = bmp.readAltitude(1013.25);
  float hum = 0.0; // BMP280 no tiene humedad

  packetId++;

  // Formato estricto para LoRa
  // CANSAT,id,temp,pres,alt,hum,ms
  Serial.print("CANSAT,");
  Serial.print(packetId);
  Serial.print(",");
  Serial.print(temp, 2);
  Serial.print(",");
  Serial.print(pres, 2);
  Serial.print(",");
  Serial.print(alt, 2);
  Serial.print(",");
  Serial.print(hum, 2);
  Serial.print(",");
  Serial.println(millis());

  delay(1000); // 1Hz rate
}
