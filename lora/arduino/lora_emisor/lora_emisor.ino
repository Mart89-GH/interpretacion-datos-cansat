/*
 * ===================================================================
 * CANSAT EMISOR TODO-EN-UNO: BMP280 + LoRa DX-LR20
 * ===================================================================
 * Lee el sensor BMP280 por I2C y transmite los datos por LoRa.
 * Todo en un solo Arduino R4 WiFi (sin necesidad de un R3 separado).
 * 
 * Produce EXACTAMENTE el mismo formato de datos que el sistema
 * de dos Arduinos (bmp280_uno + lora_emisor), por lo que el
 * receptor (lora_receptor.ino) y el dashboard Python funcionan
 * sin ningun cambio.
 * 
 * FORMATO TRANSMITIDO: CANSAT,id,temp,pres,alt,hum,ms
 * 
 * HARDWARE:
 *   - Arduino UNO R4 WiFi
 *   - Sensor BMP280 (I2C)
 *   - Modulo LoRa DX-LR20 / SX1262 (SPI)
 * 
 * CONEXIONES BMP280 (I2C):
 *   VCC  -> 3.3V
 *   GND  -> GND
 *   SDA  -> SDA (A4)
 *   SCL  -> SCL (A5)
 * 
 * CONEXIONES LoRa DX-LR20 (SPI):
 *   VCC  -> 3.3V
 *   GND  -> GND
 *   SCK  -> Pin 13
 *   MISO -> Pin 12
 *   MOSI -> Pin 11
 *   NSS  -> Pin 10
 *   RST  -> Pin 9
 *   DIO1 -> Pin 2
 *   BUSY -> Pin 3
 *   RXEN -> Pin 5
 *   TXEN -> Pin 6
 * ===================================================================
 * Tensiones
 *----------------
 *   GND-VCC = ?
 */

#include <Wire.h>
#include <Adafruit_BMP280.h>
#include <RadioLib.h>

// ===================================================================
// CONFIGURACIÓN DE PINES LORA (igual que lora_emisor.ino)
// ===================================================================
#define LORA_NSS   10
#define LORA_DIO1  2
#define LORA_RST   9
#define LORA_BUSY  3
#define RXEN_PIN   5
#define TXEN_PIN   6

// ===================================================================
// CONFIGURACIÓN LORA (DEBE COINCIDIR con el receptor)
// ===================================================================
#define LORA_FREQ       433.0   // MHz
#define LORA_BW         125.0   // kHz
#define LORA_SF         9       // Spreading Factor
#define LORA_CR         7       // Coding Rate
#define LORA_SYNC       0x12    // Sync Word
#define LORA_POWER      10      // dBm

// ===================================================================
// CONFIGURACIÓN GENERAL
// ===================================================================
#define SEND_INTERVAL   1000    // Intervalo entre envios (ms) - 1Hz como original

// ===================================================================
// OBJETOS GLOBALES
// ===================================================================
Adafruit_BMP280 bmp;
SX1262 radio = new Module(LORA_NSS, LORA_DIO1, LORA_RST, LORA_BUSY);

unsigned long packetId = 0;
unsigned long lastSend = 0;
bool bmpOK = false;
bool loraOK = false;

// Variables para control remoto
volatile bool receivedFlag = false;
bool transmitting = false; // El CANSAT inicia en estado inactivo

// ISR para recepción de comandos
#if defined(ESP8266) || defined(ESP32)
  ICACHE_RAM_ATTR
#endif
void setFlag(void) {
  receivedFlag = true;
}

// ===================================================================
// SETUP
// ===================================================================
void setup() {
  Serial.begin(115200);
  while (!Serial);

  Serial.println(F("========================================="));
  Serial.println(F("  CANSAT EMISOR TODO-EN-UNO"));
  Serial.println(F("  BMP280 (I2C) + LoRa DX-LR20 (SPI)"));
  Serial.println(F("========================================="));

  // ----- Inicializar BMP280 -----
  Serial.print(F("[BMP280] Iniciando... "));
  if (bmp.begin(0x76) || bmp.begin(0x77)) {
    Serial.println(F("OK!"));
    bmpOK = true;

    // Misma configuracion que bmp280_uno.ino
    bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                    Adafruit_BMP280::SAMPLING_X2,   // Temperatura
                    Adafruit_BMP280::SAMPLING_X16,  // Presion
                    Adafruit_BMP280::FILTER_X16,
                    Adafruit_BMP280::STANDBY_MS_500);
  } else {
    Serial.println(F("ERROR! Sensor no encontrado."));
    Serial.println(F("  Verifica conexiones I2C (SDA=A4, SCL=A5)"));
  }

  // ----- Inicializar LoRa -----
  Serial.print(F("[LoRa] Iniciando... "));
  radio.setRfSwitchPins(RXEN_PIN, TXEN_PIN);
  int state = radio.begin(LORA_FREQ, LORA_BW, LORA_SF, LORA_CR, LORA_SYNC, LORA_POWER);

  if (state == RADIOLIB_ERR_NONE) {
    Serial.println(F("OK!"));
    loraOK = true;
    
    // Configurar interrupción de recepción para comandos
    radio.setDio1Action(setFlag);
    
    // Iniciar escucha continua para recibir comandos desde tierra
    state = radio.startReceive();
    if (state == RADIOLIB_ERR_NONE) {
      Serial.println(F("[LoRa] Escuchando comandos de activacion..."));
    }
  } else {
    Serial.print(F("ERROR! Codigo: "));
    Serial.println(state);
    Serial.println(F("  Verifica conexiones SPI y pin BUSY"));
  }

  // ----- Estado final -----
  Serial.println(F("-----------------------------------------"));
  if (bmpOK && loraOK) {
    Serial.println(F("[OK] Todo listo. Transmitiendo datos..."));
  } else {
    if (!bmpOK) Serial.println(F("[WARN] BMP280 no disponible"));
    if (!loraOK) Serial.println(F("[WARN] LoRa no disponible"));
    Serial.println(F("[WARN] Continuando con lo disponible..."));
  }
  Serial.println(F("-----------------------------------------"));
}

// ===================================================================
// LOOP
// ===================================================================
void loop() {
  unsigned long now = millis();

  // === 1. LEER COMANDOS RECIBIDOS DESDE TIERRA ===
  if (receivedFlag) {
    receivedFlag = false;
    
    String cmd;
    int state = radio.readData(cmd);
    
    if (state == RADIOLIB_ERR_NONE) {
      cmd.trim();
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
    
    // Volver a escuchar
    radio.startReceive();
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
    alt  = bmp.readAltitude(1013.25);   // Presion ref nivel del mar
  }

  packetId++;

  // ----- Construir cadena CANSAT -----
  // Formato EXACTO: CANSAT,id,temp,pres,alt,hum,ms
  // (identico a bmp280_uno.ino)
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

  // ----- Enviar por LoRa -----
  if (loraOK) {
    // Al llamar a transmit, cambia automaticamente a modo TX y luego a standby
    int state = radio.transmit(data);

    if (state == RADIOLIB_ERR_NONE) {
      Serial.print(F("[TX OK] "));
      Serial.println(data);
    } else {
      Serial.print(F("[TX ERR] Codigo: "));
      Serial.print(state);
      Serial.print(F(" | Datos: "));
      Serial.println(data);
    }
    
    // DESPUES de transmitir, volver a modo escucha para recibir el comando de apagado!
    radio.startReceive();
  } else {
    // Sin LoRa, solo imprimir por serial (para debug)
    Serial.print(F("[NO LORA] "));
    Serial.println(data);
  }
}
