/*
 * =========================================================================================
 * CANSAT: MISIÓN DE PREDICCIÓN DE TRAYECTORIA Y ZONA DE ATERRIZAJE EN TIEMPO REAL
 * =========================================================================================
 * Microcontrolador: ESP32
 * Sensores:
 *   - MPU9250 (I2C): Acelerómetro, Giroscopio, Magnetómetro.
 *   - BMP280 (I2C): Presión, Temperatura, Altitud.
 *   - GPS NEO-6M (UART): Posición global, Velocidad inicial.
 *   - Módulo SD (SPI): Registro de datos locales.
 *   - Módulo LoRa EBYTE E32 (UART): Transmisión telemétrica a tierra.
 * 
 * Arquitectura:
 *   - Máquina de Estados Finita No Bloqueante (millis()).
 *   - Filtro Madgwick (>100Hz) para estimación de orientación y aceleración lineal.
 *   - Fusión GPS (1Hz) + Integración Inercial para dead reckoning de velocidad horizontal.
 *   - Derivación de altitud filtrada para Tasa de Descenso (Velocidad Vertical).
 *   - Algoritmo de Predicción Espacial (Punto de Impacto).
 * =========================================================================================
 */

#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include <HardwareSerial.h>
#include <Adafruit_BMP280.h>
#include <TinyGPSPlus.h>
// Se asume el uso de una librería MPU9250 compatible (ej. hideakitai/MPU9250 o básica)
// y un filtro MadgwickAHRS. Si no dispones de ella, deberás instalarla en tu IDE.
#include "MPU9250.h" 

// =========================================================================================
// DEFINICIÓN DE PINES ESP32
// =========================================================================================
// I2C (BMP280 y MPU9250 compartiendo bus)
#define I2C_SDA       21
#define I2C_SCL       22

// UART GPS (NEO-6M a 9600 baudios)
#define GPS_RX_PIN    12  // TX del GPS a RX ESP32
#define GPS_TX_PIN    13  // RX del GPS a TX ESP32
#define GPS_BAUD      9600

// UART LoRa EBYTE E32 (a 9600 baudios)
#define LORA_RX_PIN   16  // TXD LoRa a RX2 ESP32
#define LORA_TX_PIN   17  // RXD LoRa a TX2 ESP32
#define LORA_M0       4
#define LORA_M1       5
#define LORA_AUX      15

// SPI SD Card (Pines por defecto del VSPI en ESP32)
#define SD_CS_PIN     5
#define SD_MOSI_PIN   23
#define SD_MISO_PIN   19
#define SD_SCK_PIN    18

// =========================================================================================
// OBJETOS GLOBALES Y CONSTANTES
// =========================================================================================
Adafruit_BMP280 bmp;
MPU9250 mpu;
TinyGPSPlus gps;

HardwareSerial gpsSerial(1);   // UART1 para GPS
HardwareSerial loraSerial(2);  // UART2 para LoRa

File dataFile;
String fileName = "/flight_log.csv";

// =========================================================================================
// MÁQUINA DE ESTADOS
// =========================================================================================
enum FlightState {
  STATE_PRE_FLIGHT,
  STATE_ASCENT,
  STATE_APOGEE,
  STATE_DESCENT,
  STATE_LANDED
};
FlightState currentState = STATE_PRE_FLIGHT;

// =========================================================================================
// VARIABLES DEL SISTEMA DE NAVEGACIÓN Y PREDICCIÓN
// =========================================================================================
// Altímetro y Velocidad Vertical (dz/dt)
float baroAlt = 0.0;
float groundAltFloor = 0.0;     // Altitud cero en tierra
float filteredAlt = 0.0;
float verticalVelocity = 0.0;
unsigned long lastAltTime = 0;

// GPS y Dead Reckoning (Inercial + GPS)
float gpsLat = 0.0, gpsLng = 0.0;
float horizVelX = 0.0; // Velocidad Horizontal E-W (m/s)
float horizVelY = 0.0; // Velocidad Horizontal N-S (m/s)
unsigned long lastGpsTime = 0;

// Cinemática Inercial (Integración 100Hz)
unsigned long lastImuTime = 0;
float linAccelX = 0.0, linAccelY = 0.0, linAccelZ = 0.0; // Aceleración sin gravedad

// Predicción de Aterrizaje
float predictedLat = 0.0;
float predictedLng = 0.0;
float timeToLanding = 0.0;

// Temporizadores tareas
unsigned long lastTelemetryTime = 0;
unsigned long lastLogTime = 0;
const int TELEMETRY_INTERVAL = 1000; // 1Hz LoRa
const int LOG_INTERVAL = 100;        // 10Hz SD
const int IMU_INTERVAL = 10;         // 100Hz Madgwick/IMU

// =========================================================================================
// FUNCIONES AUXILIARES: LORA Y SD
// =========================================================================================
void setupLoRa() {
  pinMode(LORA_M0, OUTPUT);
  pinMode(LORA_M1, OUTPUT);
  pinMode(LORA_AUX, INPUT);
  
  // Set Normal Mode
  digitalWrite(LORA_M0, LOW);
  digitalWrite(LORA_M1, LOW);
  delay(100);
  loraSerial.begin(9600, SERIAL_8N1, LORA_RX_PIN, LORA_TX_PIN);
}

void setupSD() {
  if (!SD.begin(SD_CS_PIN)) {
    Serial.println("[ERROR] SD no montada o fallida.");
    return;
  }
  Serial.println("[INFO] SD Inicializada.");
  // Crear archivo con cabeceras
  dataFile = SD.open(fileName, FILE_APPEND);
  if (dataFile) {
    dataFile.println("Millis,State,Alt,dZ,Lat,Lng,Vx,Vy,PredLat,PredLng,TTL,Ax,Ay,Az");
    dataFile.close();
  }
}

void resetGroundAltitude() {
  float sum = 0;
  for (int i = 0; i < 20; i++) {
    sum += bmp.readAltitude(1013.25);
    delay(50);
  }
  groundAltFloor = sum / 20.0;
}

// =========================================================================================
// PRE-PROCESAMIENTO Y FILTROS
// =========================================================================================
// Actualizar orientación e integrar inercialmente
void updateIMU() {
  unsigned long now = millis();
  if (now - lastImuTime >= IMU_INTERVAL) { // >100 Hz
    float dt = (now - lastImuTime) / 1000.0;
    lastImuTime = now;
    
    if (mpu.update()) {
      // mpu.update() corre internamente el filtro Madgwick (según librería hideakitai/MPU9250)
      // Obtenemos la aceleración lineal (sin gravedad) en el marco de la Tierra (Norte, Este, Abajo).
      linAccelX = mpu.getLinearAccX(); // Eje X (Aprox compensado)
      linAccelY = mpu.getLinearAccY(); // Eje Y
      linAccelZ = mpu.getLinearAccZ(); // Eje Z (Vertical)
      
      // Dead Reckoning Inercial de Velocidad Horizontal entre lecturas GPS
      // Reducimos la deriva forzando a 0 si la aceleración es menor al ruido.
      if (abs(linAccelX) > 0.05) horizVelX += linAccelX * 9.81 * dt;
      if (abs(linAccelY) > 0.05) horizVelY += linAccelY * 9.81 * dt;
    }
  }
}

// Actualizar vel. vertical: Derivada de altitud con Low-Pass Básico
void updateBaroKinematics() {
  unsigned long now = millis();
  if (now - lastAltTime >= 50) { // 20 Hz
    float dt = (now - lastAltTime) / 1000.0;
    lastAltTime = now;
    
    float newAlt = bmp.readAltitude(1013.25) - groundAltFloor;
    
    // Low Pass Filter para Altitud (Suavizado)
    filteredAlt = (filteredAlt * 0.8) + (newAlt * 0.2);
    
    // Derivada Numérica v = (y2 - y1) / dt.  Si es negativo -> cayendo.
    float rawVel = (newAlt - baroAlt) / dt;
    verticalVelocity = (verticalVelocity * 0.9) + (rawVel * 0.1); 
    
    baroAlt = newAlt;
  }
}

// Actualizar GPS (Corrige derivas inerciales cada 1 segundo)
void updateGPS() {
  while (gpsSerial.available() > 0) {
    if (gps.encode(gpsSerial.read())) {
      if (gps.location.isValid()) {
        gpsLat = gps.location.lat();
        gpsLng = gps.location.lng();
        
        // El GPS también nos da la velocidad sobre el suelo y el rumbo.
        // Convertimos a componentes cartesianos X, Y (Oeste-Este, Sur-Norte)
        if (gps.speed.isValid() && gps.course.isValid()) {
          float speedMps = gps.speed.mps(); 
          float courseRad = radians(gps.course.deg());
          
          // Corrección absoluta de la velocidad inercial (Evita el drift infinito)
          // X = Este (Seno del rumbo), Y = Norte (Coseno del rumbo)
          horizVelX = speedMps * sin(courseRad);
          horizVelY = speedMps * cos(courseRad);
        }
      }
    }
  }
}

// =========================================================================================
// ALGORITMO PREDICTOR DE ATERRIZAJE
// =========================================================================================
void runPredictionAlgorithm() {
  // Solo predecimos en descenso y si estamos cayendo a una velocidad lógica (ej. > 1 m/s)
  if (currentState == STATE_DESCENT && verticalVelocity < -1.0) { 
    // Tiempo Restante = Distancia / Velocidad = Altitud / |dz/dt|
    timeToLanding = filteredAlt / abs(verticalVelocity);
    
    // Prevenir divisiones muy locas en ruido temporal
    if (timeToLanding > 300) timeToLanding = 300; 
    
    // Distancia Proyectada (metros) = VelHorizontal * t
    float distX = horizVelX * timeToLanding;
    float distY = horizVelY * timeToLanding;
    
    // Conversión de Offset Metros a Grados Coordenadas (Aprox flat-earth para distancias cortas)
    // 1 grado Latitud = ~111.32 km. 1 grado Longitud = ~111.32 * cos(lat) km
    float deltaLat = distY / 111320.0; 
    float deltaLng = distX / (111320.0 * cos(radians(gpsLat)));
    
    predictedLat = gpsLat + deltaLat;
    predictedLng = gpsLng + deltaLng;
  } else {
    // Si no desciende, caería teóricamente aquí mismo
    predictedLat = gpsLat;
    predictedLng = gpsLng;
    timeToLanding = 0;
  }
}

// =========================================================================================
// EVALUAR MÁQUINA DE ESTADOS
// =========================================================================================
void checkFlightState() {
  static float maxAltReached = 0;
  if (filteredAlt > maxAltReached) maxAltReached = filteredAlt;

  switch (currentState) {
    case STATE_PRE_FLIGHT:
      // Si subimos > 20 m y vel > 2m/s -> Despegue detectado
      if (filteredAlt > 20.0 && verticalVelocity > 2.0) {
        currentState = STATE_ASCENT;
        Serial.println("[STATE] ASCENT DETECTADO.");
      }
      break;

    case STATE_ASCENT:
      // Si la velocidad vertical es <= 0 y estamos altos -> Apogeo
      if (verticalVelocity <= 0.0 && filteredAlt > 30.0) {
        currentState = STATE_APOGEE;
        Serial.println("[STATE] APOGEE DETECTADO.");
      }
      break;

    case STATE_APOGEE:
      // Tras el apogeo, la velocidad cae definitivamente negativo
      if (verticalVelocity < -2.0) {
        currentState = STATE_DESCENT;
        Serial.println("[STATE] DESCENT DETECTADO.");
      }
      break;

    case STATE_DESCENT:
      // Si estamos cerca del suelo y la Tasa de Caída < 0.5 m/s prolongadamente
      if (filteredAlt < 10.0 && abs(verticalVelocity) < 1.0) {
        currentState = STATE_LANDED;
        Serial.println("[STATE] CANSAT LANDED.");
      }
      break;

    case STATE_LANDED:
      // Fin del vuelo, activa buzzer o modo bajo consumo
      break;
  }
}

// =========================================================================================
// EMPAQUETADO Y ENVÍO DE DATOS
// =========================================================================================
String buildTelemetryString() {
  // Formato: CSAT,State,Alt,dZ,Vvx,Vvy,Lat,Lng,PredLat,PredLng,TTL
  String data = "CSAT,";
  data += String(currentState) + ",";
  data += String(filteredAlt, 1) + ",";
  data += String(verticalVelocity, 2) + ",";
  data += String(horizVelX, 2) + ",";
  data += String(horizVelY, 2) + ",";
  data += String(gpsLat, 6) + ",";
  data += String(gpsLng, 6) + ",";
  data += String(predictedLat, 6) + ",";
  data += String(predictedLng, 6) + ",";
  data += String(timeToLanding, 1);
  return data;
}

void logDataToSD(String &telemetry) {
  dataFile = SD.open(fileName, FILE_APPEND);
  if (dataFile) {
    dataFile.print(millis()); dataFile.print(",");
    dataFile.print(telemetry); dataFile.print(",");
    // Añadimos datos de inercial solo a la SD para no saturar LoRa
    dataFile.print(linAccelX, 3); dataFile.print(",");
    dataFile.print(linAccelY, 3); dataFile.print(",");
    dataFile.println(linAccelZ, 3);
    dataFile.close();
  }
}

// =========================================================================================
// MAIN SETUP
// =========================================================================================
void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);
  
  Serial.println("============================================");
  Serial.println("  CANSAT PREDICTION MISSION - INICIALIZANDO  ");
  Serial.println("============================================");

  // 1. Buses
  Wire.begin(I2C_SDA, I2C_SCL);
  gpsSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);

  // 2. Sensores I2C
  if (!bmp.begin(0x76)) {
    Serial.println("[ERROR] BMP280 Fail.");
  } else {
    bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                    Adafruit_BMP280::SAMPLING_X2,
                    Adafruit_BMP280::SAMPLING_X16,
                    Adafruit_BMP280::FILTER_X16,
                    Adafruit_BMP280::STANDBY_MS_1); // Muestreo rápido
    Serial.println("[OK] BMP280 Encontrado.");
  }
  
  if (!mpu.setup(0x68)) {  // o 0x69
    Serial.println("[ERROR] MPU9250 Fail.");
  } else {
    Serial.println("[OK] MPU9250 Encontrado y Calibrado.");
  }

  // 3. Periféricos
  setupSD();
  setupLoRa();

  // 4. Calibración Terrestre (Establecer la cota 0)
  Serial.println("[INFO] Calibrando altímetro GND... No mover.");
  resetGroundAltitude();
  Serial.print("[INFO] Zero Alt: "); Serial.println(groundAltFloor);
  
  Serial.println("\n[SISTEMA LISTO] Esperando despegue...");
}

// =========================================================================================
// MAIN LOOP (NO BLOQUEANTE)
// =========================================================================================
void loop() {
  unsigned long now = millis();

  // -- 1. ACTUALIZAR SENSORES --
  updateIMU();             // ~100 Hz: Filtro Madgwick e Integración Aceleraciones Lineales
  updateBaroKinematics();  // ~20 Hz: LPF Altitud, Derivación Tasa Descenso dZ
  updateGPS();             // Continuo UART (1Hz ref): Anclaje de Velocidad Horizontal ABS

  // -- 2. LÓGICA DE MISIÓN --
  checkFlightState();
  runPredictionAlgorithm();

  // -- 3. LOGGING (SD) a ~10 Hz --
  if (now - lastLogTime >= LOG_INTERVAL) {
    lastLogTime = now;
    String tData = buildTelemetryString();
    logDataToSD(tData);
  }

  // -- 4. TELEMETRÍA (LoRa) a 1 Hz --
  if (now - lastTelemetryTime >= TELEMETRY_INTERVAL) {
    lastTelemetryTime = now;
    String tData = buildTelemetryString();
    
    // Transmitir asegurando disponibilidad en caso del E32 (verificando AUX si fuera bloquente, 
    // pero para no bloquear el bucle asumimos TX buffer asincrono).
    if (digitalRead(LORA_AUX) == HIGH) {
      loraSerial.println(tData);
      Serial.print("[TX->] ");
      Serial.println(tData); // Monitoreo en PC
    } else {
      Serial.println("[INFO] LoRa Busy... salto TX.");
    }
  }
}
