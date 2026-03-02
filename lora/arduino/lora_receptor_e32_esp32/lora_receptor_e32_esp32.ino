/*
 * ===================================================================
 * CANSAT RECEPTOR #2 - LoRa EBYTE E32-433T30D PARA ESP32
 * ===================================================================
 * Segundo receptor LoRa para recibir datos del CanSat.
 * Usa el módulo EBYTE E32-433T30D (UART, basado en SX1278).
 * 
 * En ESP32 se recomienda usar HardwareSerial (Serial1 o Serial2) 
 * ya que tiene múltiples UARTs por hardware en lugar de SoftwareSerial.
 * 
 * Produce EXACTAMENTE la misma salida serial que el receptor original
 * por lo que el dashboard Python funciona sin ningún cambio.
 * 
 * FORMATO DE SALIDA SERIAL (para dashboard Python):
 *   Línea "RSSI: -50.0" -> estimado
 *   Línea "SNR: 10.0"   -> estimado  
 *   Línea "CANSAT,id,temp,presion,altitud,humedad,millis"
 * 
 * HARDWARE:
 *   - ESP32
 *   - Módulo LoRa EBYTE E32-433T30D (UART)
 * 
 * CONEXIONES E32-433T30D (A ESP32):
 *   VCC  -> 5V o 3.3V
 *   GND  -> GND
 *   TXD  -> GPIO 16 (RX2 del ESP32)
 *   RXD  -> GPIO 17 (TX2 del ESP32)
 *   M0   -> GPIO 4  (control de modo)
 *   M1   -> GPIO 5  (control de modo)
 *   AUX  -> GPIO 15 (indicador de estado)
 * ===================================================================
 */

// ===================================================================
// CONFIGURACIÓN DE PINES
// ===================================================================
#define E32_RX_PIN   16   // Conectar al TXD del E32
#define E32_TX_PIN   17   // Conectar al RXD del E32

#define E32_M0_PIN   4    // Control de modo M0
#define E32_M1_PIN   5    // Control de modo M1
#define E32_AUX_PIN  15   // Pin AUX (estado del módulo)

// ===================================================================
// CONFIGURACIÓN GENERAL
// ===================================================================
#define E32_BAUD_RATE    9600    // Velocidad UART del E32 (por defecto)
#define SERIAL_BAUD      115200  // Velocidad Serial Monitor para ESP32
#define BUFFER_SIZE      128     // Tamaño del buffer de recepción
#define TIMEOUT_MS       100     // Timeout para lectura de mensaje completo

// ===================================================================
// OBJETOS GLOBALES
// ===================================================================
HardwareSerial e32Serial(2); // Usando UART2 ()

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
    delay(10); // Alimentar el watchdog
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
  while (!Serial) delay(10);

  Serial.println(F("========================================="));
  Serial.println(F("  CANSAT RECEPTOR #2 ESP32 - E32-433T30D"));
  Serial.println(F("  Frecuencia: 433 MHz (UART)"));
  Serial.println(F("========================================="));

  // Configurar pines de control
  pinMode(E32_M0_PIN, OUTPUT);
  pinMode(E32_M1_PIN, OUTPUT);
  pinMode(E32_AUX_PIN, INPUT);

  // Poner en modo config brevemente para verificar
  setModoConfig();
  delay(500);

  // Iniciar comunicación UART2 con el E32
  e32Serial.begin(E32_BAUD_RATE, SERIAL_8N1, E32_RX_PIN, E32_TX_PIN);

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
  // === 1. LEER COMANDOS DEL SERIAL MONITOR Y ENVIAR AL EMISOR ===
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) {
      Serial.print(F(">>> ENVIANDO COMANDO: "));
      Serial.println(cmd);
      
      esperarAUX();
      e32Serial.println(cmd);
      esperarAUX();
      
      Serial.println(F(">>> COMANDO ENVIADO OK"));
    }
  }

  // === 2. VERIFICAR SI HAY DATOS DISPONIBLES DEL E32 ===
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

    // Línea 1: RSSI (estimado)
    Serial.print(F("RSSI: "));
    Serial.println(F("-50.0"));

    // Línea 2: SNR (estimado)
    Serial.print(F("SNR: "));
    Serial.println(F("10.0"));

    // Línea 3: Datos CANSAT
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
