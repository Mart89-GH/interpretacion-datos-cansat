/*
 * ===================================================================
 * CANSAT RECEPTOR #2 - LoRa EBYTE E32-433T30D
 * ===================================================================
 * Segundo receptor LoRa para recibir datos del CanSat.
 * Usa el módulo EBYTE E32-433T30D (UART, basado en SX1278).
 * 
 * Produce EXACTAMENTE la misma salida serial que lora_receptor.ino
 * (el receptor SX1262), por lo que el dashboard Python funciona
 * sin ningún cambio.
 * 
 * FORMATO DE SALIDA SERIAL (para dashboard Python):
 *   Línea "RSSI: -XX.X"  -> capturada por dashboard
 *   Línea "SNR: X.X"     -> capturada por dashboard  
 *   Línea "CANSAT,id,temp,presion,altitud,humedad,millis"
 * 
 * NOTA: El E32 no proporciona RSSI/SNR por software, así que
 *       se envían valores estimados para mantener compatibilidad.
 *       Se puede activar el modo RSSI del módulo con el pin
 *       de configuración (ver más abajo).
 * 
 * HARDWARE:
 *   - Arduino UNO (o R4 WiFi)
 *   - Módulo LoRa EBYTE E32-433T30D (UART)
 * 
 * CONEXIONES E32-433T30D:
 *   VCC  -> 5V  (el E32-433T30D soporta 3.3-5.2V)
 *   GND  -> GND
 *   TXD  -> Pin 2 (RX del SoftwareSerial)
 *   RXD  -> Pin 3 (TX del SoftwareSerial)
 *   M0   -> Pin 4 (control de modo)
 *   M1   -> Pin 5 (control de modo)
 *   AUX  -> Pin 6 (indicador de estado)
 * 
 * MODOS DEL E32 (M0, M1):
 *   M0=LOW,  M1=LOW  -> Modo Normal (transmisión/recepción)
 *   M0=HIGH, M1=LOW  -> Modo Wake-Up
 *   M0=LOW,  M1=HIGH -> Modo Power-Saving
 *   M0=HIGH, M1=HIGH -> Modo Sleep/Configuración
 * 
 * IMPORTANTE - CONFIGURACIÓN DEL MÓDULO:
 *   El E32-433T30D debe estar configurado con los mismos
 *   parámetros que el emisor (canal, dirección, air data rate).
 *   Por defecto de fábrica:
 *     - Dirección: 0x0000
 *     - Canal: 0x17 (433 MHz)
 *     - Air Data Rate: 2.4kbps
 *     - UART: 9600 bps, 8N1
 *   Si el emisor usa configuración por defecto, este receptor
 *   funcionará directamente.
 * ===================================================================
 */

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
#define SERIAL_BAUD      9600    // Velocidad Serial Monitor (igual que receptor original)
#define BUFFER_SIZE      128     // Tamaño del buffer de recepción
#define TIMEOUT_MS       100     // Timeout para lectura de mensaje completo

// ===================================================================
// OBJETOS GLOBALES
// ===================================================================
SoftwareSerial e32Serial(E32_TX_PIN, E32_RX_PIN);  // RX, TX

int paquetesRecibidos = 0;
char buffer[BUFFER_SIZE];
int bufferIndex = 0;

// ===================================================================
// FUNCIONES AUXILIARES
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
  // Iniciar Serial Monitor
  Serial.begin(SERIAL_BAUD);
  while (!Serial);

  Serial.println(F("========================================="));
  Serial.println(F("  CANSAT RECEPTOR #2 - E32-433T30D"));
  Serial.println(F("  Frecuencia: 433 MHz (UART)"));
  Serial.println(F("========================================="));

  // Configurar pines de control
  pinMode(E32_M0_PIN, OUTPUT);
  pinMode(E32_M1_PIN, OUTPUT);
  pinMode(E32_AUX_PIN, INPUT);

  // Poner en modo config brevemente para verificar
  setModoConfig();
  delay(500);

  // Iniciar comunicación UART con el E32
  e32Serial.begin(E32_BAUD_RATE);

  // Poner en modo normal para recibir
  Serial.print(F("[E32] Configurando modo normal... "));
  setModoNormal();
  Serial.println(F("OK!"));

  // Limpiar buffer serial
  while (e32Serial.available()) {
    e32Serial.read();
  }

  Serial.println(F("[E32] Escuchando paquetes..."));
  Serial.println(F("-----------------------------------------"));
  Serial.println(F("NOTA: RSSI/SNR son valores estimados"));
  Serial.println(F("      (E32 no proporciona estos datos)"));
  Serial.println(F("-----------------------------------------"));
}

// ===================================================================
// LOOP
// ===================================================================
void loop() {
  // Verificar si hay datos disponibles del E32
  if (!e32Serial.available()) {
    return;
  }

  // Leer datos del E32 hasta encontrar fin de línea o timeout
  bufferIndex = 0;
  unsigned long startTime = millis();

  while (millis() - startTime < TIMEOUT_MS) {
    if (e32Serial.available()) {
      char c = e32Serial.read();

      // Detectar fin de mensaje
      if (c == '\n' || c == '\r') {
        if (bufferIndex > 0) {
          // Tenemos un mensaje completo
          buffer[bufferIndex] = '\0';
          break;
        }
        // Ignorar \r o \n sueltos al inicio
        continue;
      }

      // Agregar carácter al buffer
      if (bufferIndex < BUFFER_SIZE - 1) {
        buffer[bufferIndex++] = c;
      }

      // Reiniciar timeout con cada carácter recibido
      startTime = millis();
    }
  }

  // Si no se recibió nada útil, salir
  if (bufferIndex == 0) {
    return;
  }

  // Asegurar terminación del string
  buffer[bufferIndex] = '\0';
  String mensaje = String(buffer);

  // Verificar que es un paquete CANSAT válido o CANSAT_SEC (Misión Secundaria)
  if (mensaje.startsWith("CANSAT,") || mensaje.startsWith("CANSAT_SEC,")) {
    paquetesRecibidos++;

    // === SALIDA SERIAL PARA DASHBOARD PYTHON ===
    // Formato idéntico al receptor SX1262 original

    // Línea 1: RSSI (estimado - el E32 no lo proporciona directamente)
    // El E32-433T30D tiene 30dBm de potencia, estimamos RSSI basado
    // en que si recibimos datos, la señal es razonablemente buena
    Serial.print(F("RSSI: "));
    Serial.println(F("-50.0"));

    // Línea 2: SNR (estimado)
    Serial.print(F("SNR: "));
    Serial.println(F("10.0"));

    // Línea 3: Datos CANSAT (tal cual, ya vienen en formato correcto)
    Serial.println(mensaje);

    // Línea 4: Info de debug (ignorada por dashboard)
    Serial.print(F("[RX #"));
    Serial.print(paquetesRecibidos);
    Serial.print(F("] via E32-433T30D - Tipo: "));
    Serial.println(mensaje.startsWith("CANSAT_SEC") ? F("SECUNDARIA") : F("PRIMARIA"));

  } else {
    // Mensaje recibido pero no es formato CANSAT
    Serial.print(F("[RX?] Dato no-CANSAT: "));
    Serial.println(mensaje);
  }
}
