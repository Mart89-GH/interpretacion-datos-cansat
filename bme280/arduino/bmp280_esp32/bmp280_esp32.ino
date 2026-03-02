/*
 * BMP280 Data Node - ESP32
 * Lee el sensor y envía datos formateados por Serial
 * Formato: CANSAT,id,temp,pres,alt,hum,ms
 * 
 * Conectar (pines por defecto I2C en ESP32):
 *   VCC  -> 3.3V
 *   GND  -> GND
 *   SDA  -> GPIO 21
 *   SCL  -> GPIO 22
 *   
 *   TX (GPIO 1 / TX0) -> RX del dispositivo receptor (ej. módulo LoRa)
 *   GND               -> GND del dispositivo receptor
 */

#include <Wire.h>
#include <Adafruit_BMP280.h>

// Definir pines I2C (21 y 22 son los estándar en ESP32)
#define I2C_SDA 21
#define I2C_SCL 22

Adafruit_BMP280 bmp;
unsigned long packetId = 0;

void setup() {
  // Velocidad recomendada en ESP32 es 115200 (en Arduino Uno usabas 9600)
  Serial.begin(115200);
  while(!Serial) delay(10);
  
  // Inicializar bus I2C en el ESP32 con sus pines específicos
  Wire.begin(I2C_SDA, I2C_SCL);
  
  // Inicializar BMP280 (Suele venir en 0x76, en caso de fallo prueba 0x77)
  if (!bmp.begin(0x76) && !bmp.begin(0x77)) {
    Serial.println("ER,Sensor BMP280 no encontrado");
    while (1) delay(1000); // En ESP32 es recomendable dejar un delay() dentro del while(1)
  }

  // Configuración del sensor
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
  float hum = 0.0; // BMP280 no tiene humedad, mantenemos 0.0 para compatibilidad de formato

  packetId++;

  // Formato estricto CANSAT para enviar por Radio/Serial
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
