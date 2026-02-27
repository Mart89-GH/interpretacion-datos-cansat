/*
 * ===================================================================
 * LORA RECEPTOR + DASHBOARD - CANSAT ESPAÑA 2026
 * ===================================================================
 * Recibe datos del CanSat por LoRa y los envía por Serial
 * para que el dashboard Python los muestre en tiempo real.
 * 
 * HARDWARE:
 *   - Arduino UNO R4 WiFi
 *   - Módulo LoRa DX-LR20 (SX1262/LLCC68) a 433 MHz
 * 
 * CONEXIONES LORA DX-LR20:
 *   VCC  -> 3.3V
 *   GND  -> GND
 *   SCK  -> Pin 13 (SPI)
 *   MISO -> Pin 12 (SPI)
 *   MOSI -> Pin 11 (SPI)
 *   NSS  -> Pin 10
 *   RST  -> Pin 9
 *   DIO1 -> Pin 2
 *   BUSY -> Pin 3
 *   RXEN -> Pin 5
 *   TXEN -> Pin 6
 * 
 * FORMATO DE SALIDA SERIAL (para dashboard Python):
 *   Línea "RSSI: -XX.X"  -> capturada por dashboard
 *   Línea "SNR: X.X"     -> capturada por dashboard
 *   Línea "CANSAT,id,temp,presion,altitud,humedad,millis"
 * ===================================================================
 */

#include <RadioLib.h>

// ===================================================================
// CONFIGURACIÓN DE PINES (igual que emisor)
// ===================================================================
#define LORA_NSS   10
#define LORA_DIO1  2
#define LORA_RST   9
#define LORA_BUSY  3
#define RXEN_PIN   5
#define TXEN_PIN   6

// ===================================================================
// CONFIGURACIÓN LORA (DEBE COINCIDIR con el emisor)
// ===================================================================
#define LORA_FREQ       433.0   // MHz
#define LORA_BW         125.0   // kHz
#define LORA_SF         9       // Spreading Factor
#define LORA_CR         7       // Coding Rate
#define LORA_SYNC       0x12    // Sync Word
#define LORA_POWER      10      // dBm

// ===================================================================
// OBJETOS GLOBALES
// ===================================================================
SX1262 radio = new Module(LORA_NSS, LORA_DIO1, LORA_RST, LORA_BUSY);

volatile bool receivedFlag = false;
int paquetesRecibidos = 0;

// ISR para recepción
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
  Serial.begin(9600);
  while (!Serial);
  
  Serial.println(F("========================================="));
  Serial.println(F("  CANSAT RECEPTOR - LoRa DX-LR20"));
  Serial.println(F("  Frecuencia: 433 MHz"));
  Serial.println(F("========================================="));
  
  // Configurar pines de antena
  radio.setRfSwitchPins(RXEN_PIN, TXEN_PIN);
  
  // Inicializar LoRa (mismos parámetros que emisor)
  Serial.print(F("[LoRa] Iniciando... "));
  int state = radio.begin(LORA_FREQ, LORA_BW, LORA_SF, LORA_CR, LORA_SYNC, LORA_POWER);
  
  if (state == RADIOLIB_ERR_NONE) {
    Serial.println(F("OK!"));
  } else {
    Serial.print(F("ERROR! Codigo: "));
    Serial.println(state);
    while (true);
  }
  
  // Configurar interrupción de recepción
  radio.setDio1Action(setFlag);
  
  // Iniciar modo recepción continua
  state = radio.startReceive();
  if (state == RADIOLIB_ERR_NONE) {
    Serial.println(F("[LoRa] Escuchando paquetes..."));
  } else {
    Serial.print(F("[LoRa] Error al escuchar: "));
    Serial.println(state);
  }
  
  Serial.println(F("-----------------------------------------"));
}

// ===================================================================
// LOOP
// ===================================================================
void loop() {
  // === 1. LEER COMANDOS DEL SERIAL MONITOR Y ENVIAR AL EMISOR ===
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) {
      Serial.print(F(">>> ENVIANDO COMANDO: "));
      Serial.println(cmd);
      
      // Cambiar a standby para transmitir
      radio.standby();
      
      // Enviar comando
      int state = radio.transmit(cmd);
      
      if (state == RADIOLIB_ERR_NONE) {
        Serial.println(F(">>> COMANDO ENVIADO OK"));
      } else {
        Serial.print(F(">>> ERROR AL ENVIAR COMANDO: "));
        Serial.println(state);
      }
      
      // Volver a escuchar
      radio.startReceive();
    }
  }

  // === 2. PROCESAR PAQUETES RECIBIDOS ===
  if (!receivedFlag) {
    return;  // No hay paquetes, terminar iteracion
  }
  
  // Resetear bandera
  receivedFlag = false;
  
  // Leer datos
  String mensaje;
  int state = radio.readData(mensaje);
  
  if (state == RADIOLIB_ERR_NONE) {
    paquetesRecibidos++;
    
    // Obtener calidad de señal
    float rssi = radio.getRSSI();
    float snr = radio.getSNR();
    
    // === SALIDA SERIAL PARA DASHBOARD PYTHON ===
    // Formato limpio que el dashboard puede parsear fácilmente:
    // Línea 1: RSSI
    Serial.print(F("RSSI: "));
    Serial.println(rssi, 1);
    
    // Línea 2: SNR
    Serial.print(F("SNR: "));
    Serial.println(snr, 1);
    
    // Línea 3: Datos (ya vienen en formato CANSAT,...)
    Serial.println(mensaje);
    
    // Línea 4: Separador (ignorado por dashboard)
    Serial.print(F("[RX #"));
    Serial.print(paquetesRecibidos);
    Serial.print(F("] RSSI="));
    Serial.print(rssi, 0);
    Serial.print(F(" SNR="));
    Serial.println(snr, 1);
    
  } else if (state == RADIOLIB_ERR_CRC_MISMATCH) {
    Serial.println(F("[ERR] CRC - paquete corrupto"));
  } else {
    Serial.print(F("[ERR] Codigo: "));
    Serial.println(state);
  }
  
  // Volver a escuchar
  radio.startReceive();
}
