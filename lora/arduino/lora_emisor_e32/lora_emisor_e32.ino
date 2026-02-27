/*
 * ===================================================================
 * CANSAT EMISOR TODO-EN-UNO: BMP280 + LoRa EBYTE E32-433T30D
 * ===================================================================
 * Lee el sensor BMP280 por I2C y transmite los datos por LoRa
 * usando el módulo EBYTE E32-433T30D (basado en UART).
 * 
 * Produce EXACTAMENTE el mismo formato de datos que el emisor DX-LR20
 * original: "CANSAT,id,temp,pres,alt,hum,ms"
 * 
 * HARDWARE:
 *   - Arduino UNO R4 WiFi
 *   - Sensor BMP280 (I2C)
 *   - Módulo LoRa EBYTE E32-433T30D (UART)
 * 
 * CONEXIONES BMP280 (I2C):
 *   VCC  -> 3.3V
 *   GND  -> GND
 *   SDA  -> SDA (A4)
 *   SCL  -> SCL (A5)
 * 
 * CONEXIONES E32-433T30D:
 *   VCC  -> 5V  (el E32-433T30D soporta 3.3-5.2V)
 *   GND  -> GND
 *   TXD  -> Pin 2 (RX de SoftwareSerial)
 *   RXD  -> Pin 3 (TX de SoftwareSerial)
 *   M0   -> Pin 4 (control de modo)
 *   M1   -> Pin 5 (control de modo)
 *   AUX  -> Pin 6 (indicador de estado)
 * ===================================================================
 */

#include <Wire.h>
#include <Adafruit_BMP280.h>
#include <SoftwareSerial.h>

// ===================================================================
// CONFIGURACIÓN DE PINES
// ===================================================================
#define E32_TX_PIN   2    // TXD del E32 -> Pin 2 (RX del Arduino)
#define E32_RX_PIN   3    // RXD del E32 -> Pin 3 (TX del Arduino)
#define E32_M0_PIN   4    // Control de modo M0
#define E32_M1_PIN   5    // Control de modo M1
#define E32_AUX_PIN  6    // Pin AUX (estado del módulo)

// ===================================================================
// CONFIGURACIÓN GENERAL
// ===================================================================
#define E32_BAUD_RATE    9600    // Velocidad UART del E32 (por defecto)
#define SEND_INTERVAL   1000    // Intervalo entre envios (ms) - 1Hz

// ===================================================================
// OBJETOS GLOBALES
// ===================================================================
Adafruit_BMP280 bmp;
SoftwareSerial e32Serial(E32_TX_PIN, E32_RX_PIN);  // RX, TX

unsigned long packetId = 0;
unsigned long lastSend = 0;
bool bmpOK = false;

// Variables para control remoto
bool transmitting = false; // El CANSAT inicia en estado inactivo

// ===================================================================
// FUNCIONES AUXILIARES E32
// ===================================================================

// Esperar a que el módulo E32 esté listo (AUX = HIGH)
void esperarAUX() {
  unsigned long inicio = millis();
  while (digitalRead(E32_AUX_PIN) == LOW) {
    if (millis() - inicio > 2000) {
      Serial.println(F("[WARN] Timeout esperando AUX"));
      break;
    }
  }
  delay(50);  // Pequeño margen después de AUX HIGH
}

// Configurar el módulo en modo normal (M0=LOW, M1=LOW)
void setModoNormal() {
  digitalWrite(E32_M0_PIN, LOW);
  digitalWrite(E32_M1_PIN, LOW);
  esperarAUX();
}

// Configurar el módulo en modo sleep/config (M0=HIGH, M1=HIGH)
void setModoConfig() {
  digitalWrite(E32_M0_PIN, HIGH);
  digitalWrite(E32_M1_PIN, HIGH);
  esperarAUX();
}

// ===================================================================
// SETUP
// ===================================================================
void setup() {
  Serial.begin(9600);
  while (!Serial);

  Serial.println(F("========================================="));
  Serial.println(F("  CANSAT EMISOR TODO-EN-UNO"));
  Serial.println(F("  BMP280 (I2C) + E32-433T30D (UART)"));
  Serial.println(F("========================================="));

  // ----- Inicializar BMP280 -----
  Serial.print(F("[BMP280] Iniciando... "));
  if (bmp.begin(0x76) || bmp.begin(0x77)) {
    Serial.println(F("OK!"));
    bmpOK = true;

    // Misma configuracion estándar
    bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                    Adafruit_BMP280::SAMPLING_X2,   // Temperatura
                    Adafruit_BMP280::SAMPLING_X16,  // Presion
                    Adafruit_BMP280::FILTER_X16,
                    Adafruit_BMP280::STANDBY_MS_500);
  } else {
    Serial.println(F("ERROR! Sensor no encontrado."));
    Serial.println(F("  Verifica conexiones I2C (SDA=A4, SCL=A5)"));
  }

  // ----- Inicializar LoRa E32 -----
  Serial.print(F("[E32] Iniciando UART... "));
  pinMode(E32_M0_PIN, OUTPUT);
  pinMode(E32_M1_PIN, OUTPUT);
  pinMode(E32_AUX_PIN, INPUT);

  // Poner en modo config brevemente para encender y luego normal
  setModoConfig();
  delay(500);
  
  e32Serial.begin(E32_BAUD_RATE);
  setModoNormal();
  Serial.println(F("OK!"));

  // ----- Estado final -----
  Serial.println(F("-----------------------------------------"));
  if (bmpOK) {
    Serial.println(F("[OK] Todo listo. Transmitiendo datos..."));
  } else {
    Serial.println(F("[WARN] BMP280 no disponible. Enviando 0s..."));
  }
  Serial.println(F("-----------------------------------------"));
}

// ===================================================================
// LOOP
// ===================================================================
void loop() {
  unsigned long now = millis();

  // === 1. LEER COMANDOS RECIBIDOS DESDE TIERRA ===
  if (e32Serial.available()) {
    String cmd = e32Serial.readStringUntil('\n');
    cmd.trim();
    
    if (cmd.length() > 0) {
      Serial.print(F("[CMD RX] Recibido: "));
      Serial.println(cmd);
      
      // Comandos de activacion
      if (cmd == "280" || cmd == "ON" || cmd == "START") {
        transmitting = true;
        Serial.println(F("[!] TRANSMISION ACTIVADA"));
      } 
      // Comandos de desactivacion
      else if (cmd == "OFF" || cmd == "STOP") {
        transmitting = false;
        Serial.println(F("[!] TRANSMISION DETENIDA"));
      }
    }
  }

  // === 2. VERIFICAR SI ESTAMOS ACTIVOS ===
  if (!transmitting) {
    return; // Si no estamos transmitiendo, terminar loop
  }

  // === 3. TRANSMITIR DATOS (Respetar SEND_INTERVAL) ===
  if (now - lastSend < SEND_INTERVAL) {
    return;
  }
  lastSend = now;

  // ----- Leer BMP280 -----
  float temp = 0.0;
  float pres = 0.0;
  float alt  = 0.0;
  float hum  = 0.0;  // BMP280 no tiene humedad

  if (bmpOK) {
    temp = bmp.readTemperature();
    pres = bmp.readPressure() / 100.0;  // Pa -> hPa
    alt  = bmp.readAltitude(1017);   // Presion ref nivel del mar
  }

  packetId++;

  // ----- Construir cadena CANSAT -----
  String data = "CANSAT,";
  data += String(packetId);
  data += ",";
  data += String(temp, 2);
  data += ",";
  data += String(pres, 2);
  data += ",";
  data += String(alt, 2);
  data += ",";
  data += String(hum, 2);
  data += ",";
  data += String(now);

  // ----- Enviar por LoRa E32 -----
  // El E32 envía lo que reciba por UART a todos los módulos en el canal
  esperarAUX(); // Comprobar si módulo está libre antes de emitir
  e32Serial.println(data);
  esperarAUX(); // Esperar a que se termine de emitir

  // Imprimir por serial (para debug local)
  Serial.print(F("[TX OK] "));
  Serial.println(data);
}
