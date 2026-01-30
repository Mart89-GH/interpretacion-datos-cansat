/*
 * BMP280 Data Logger for Arduino R4 WiFi
 * Con detección de anomalías y auto-reset del sensor
 * 
 * NOTA: Este sensor es un BMP280, NO un BME280
 * El BMP280 NO tiene sensor de humedad
 * 
 * Conexiones BMP280 -> Arduino R4 WiFi:
 *   VCC  -> 3.3V
 *   GND  -> GND
 *   SDA  -> SDA (pin 20)
 *   SCL  -> SCL (pin 21)
 */

#include <Wire.h>
#include <Adafruit_BMP280.h>

// ========= CONFIGURACIÓN =========
#define SEALEVELPRESSURE_HPA (1012)
#define READ_INTERVAL 1000
#define STATUS_LED LED_BUILTIN

// ========= UMBRALES DE ANOMALÍAS =========
// Cambios máximos permitidos entre lecturas consecutivas
#define MAX_DELTA_TEMP   10.0   // °C
#define MAX_DELTA_PRES   20.0   // hPa
#define MAX_DELTA_ALT    50.0   // metros

// Rangos válidos absolutos
#define MIN_TEMP   -40.0
#define MAX_TEMP    85.0
#define MIN_PRES    300.0
#define MAX_PRES    1100.0
#define BASELINE_ALT  650.0   // Altitud base de tu ubicación (metros)
#define ALT_TOLERANCE 500.0   // Tolerancia en metros

// Número de errores consecutivos antes de reset
#define MAX_CONSECUTIVE_ERRORS 3

// ========= VARIABLES GLOBALES =========
Adafruit_BMP280 bmp;
bool sensor_ok = false;

// Últimos valores válidos (para detectar cambios bruscos)
float last_temp = NAN;
float last_pres = NAN;
float last_alt = NAN;
bool first_reading = true;

// Contadores de errores
int consecutive_errors = 0;
int total_resets = 0;

// ========= FUNCIONES DE UTILIDAD =========

// Función para hacer un reset completo del Arduino
void softwareReset() {
  Serial.println("info=ARDUINO_RESETTING");
  delay(100);
  NVIC_SystemReset();
}

// Reinicializar solo el sensor BMP280
bool reinitializeSensor() {
  Serial.println("info=SENSOR_REINITIALIZING");
  
  Wire.end();
  delay(100);
  Wire.begin();
  delay(100);
  
  if (bmp.begin(0x76) || bmp.begin(0x77)) {
    Serial.println("info=SENSOR_REINITIALIZED_OK");
    total_resets++;
    
    // Resetear valores anteriores
    first_reading = true;
    last_temp = NAN;
    last_pres = NAN;
    last_alt = NAN;
    consecutive_errors = 0;
    
    // Reconfigurar sensor
    bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                    Adafruit_BMP280::SAMPLING_X2,
                    Adafruit_BMP280::SAMPLING_X16,
                    Adafruit_BMP280::FILTER_X16,
                    Adafruit_BMP280::STANDBY_MS_500);
    
    return true;
  } else {
    Serial.println("error=SENSOR_REINIT_FAILED");
    return false;
  }
}

// Verificar si un valor está en rango válido
bool isInValidRange(float value, float minVal, float maxVal) {
  if (isnan(value)) return false;
  return (value >= minVal && value <= maxVal);
}

// Verificar si hay un cambio anómalo
bool isAnomalyDelta(float newVal, float oldVal, float maxDelta) {
  if (isnan(oldVal) || isnan(newVal)) return false;
  return (abs(newVal - oldVal) > maxDelta);
}

// ========= SETUP =========
void setup() {
  pinMode(STATUS_LED, OUTPUT);
  Serial.begin(115200);
  while (!Serial) delay(10);

  Serial.println("BMP280 Data Logger with Anomaly Detection - Arduino R4 WiFi");
  Serial.println("============================================================");

  Wire.begin();
  delay(100);

  // Inicializar BMP280
  if (!bmp.begin(0x76) && !bmp.begin(0x77)) {
    Serial.println("error=SENSOR_NOT_FOUND");
    sensor_ok = false;
  } else {
    Serial.println("info=BMP280_INITIALIZED");
    sensor_ok = true;
    
    // Configuración óptima
    bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                    Adafruit_BMP280::SAMPLING_X2,
                    Adafruit_BMP280::SAMPLING_X16,
                    Adafruit_BMP280::FILTER_X16,
                    Adafruit_BMP280::STANDBY_MS_500);
  }

  delay(1000);
}

// ========= LOOP PRINCIPAL =========
void loop() {
  // Health check rápido
  float temp_check = bmp.readTemperature();
  
  if (isnan(temp_check) || temp_check < -50 || temp_check > 100) {
    if (!bmp.begin(0x76) && !bmp.begin(0x77)) {
      Serial.println("error=SENSOR_DISCONNECTED");
      sensor_ok = false;
      digitalWrite(STATUS_LED, LOW);
      consecutive_errors++;
      
      if (consecutive_errors >= MAX_CONSECUTIVE_ERRORS * 2) {
        Serial.println("error=TOO_MANY_ERRORS_RESETTING_ARDUINO");
        delay(500);
        softwareReset();
      }
    } else {
      sensor_ok = true;
      consecutive_errors = 0;
    }
  } else {
    sensor_ok = true;
  }

  if (sensor_ok) {
    // Leer todos los valores
    float temperature = bmp.readTemperature();
    float pressure = bmp.readPressure() / 100.0F;
    float altitude = bmp.readAltitude(SEALEVELPRESSURE_HPA);
    
    bool anomaly_detected = false;
    bool range_error = false;
    String anomaly_sensors = "";
    
    // ========= VERIFICAR RANGOS ABSOLUTOS =========
    if (!isInValidRange(temperature, MIN_TEMP, MAX_TEMP)) {
      range_error = true;
      anomaly_sensors += "TEMP,";
      Serial.print("warning=TEMP_OUT_OF_RANGE:");
      Serial.println(temperature);
    }
    
    if (!isInValidRange(pressure, MIN_PRES, MAX_PRES)) {
      range_error = true;
      anomaly_sensors += "PRES,";
      Serial.print("warning=PRES_OUT_OF_RANGE:");
      Serial.println(pressure);
    }
    
    float min_alt = BASELINE_ALT - ALT_TOLERANCE;
    float max_alt = BASELINE_ALT + ALT_TOLERANCE;
    if (!isInValidRange(altitude, min_alt, max_alt)) {
      range_error = true;
      anomaly_sensors += "ALT,";
      Serial.print("warning=ALT_OUT_OF_RANGE:");
      Serial.println(altitude);
    }
    
    // ========= VERIFICAR CAMBIOS BRUSCOS =========
    if (!first_reading) {
      if (isAnomalyDelta(temperature, last_temp, MAX_DELTA_TEMP)) {
        anomaly_detected = true;
        Serial.print("anomaly=TEMP_DELTA:");
        Serial.print(last_temp);
        Serial.print("->");
        Serial.println(temperature);
      }
      
      if (isAnomalyDelta(pressure, last_pres, MAX_DELTA_PRES)) {
        anomaly_detected = true;
        Serial.print("anomaly=PRES_DELTA:");
        Serial.print(last_pres);
        Serial.print("->");
        Serial.println(pressure);
      }
      
      if (isAnomalyDelta(altitude, last_alt, MAX_DELTA_ALT)) {
        anomaly_detected = true;
        Serial.print("anomaly=ALT_DELTA:");
        Serial.print(last_alt);
        Serial.print("->");
        Serial.println(altitude);
      }
    }
    
    // ========= MANEJAR ANOMALÍAS =========
    if (anomaly_detected || range_error) {
      consecutive_errors++;
      
      // Parpadeo rápido de error
      for (int i = 0; i < 3; i++) {
        digitalWrite(STATUS_LED, HIGH);
        delay(50);
        digitalWrite(STATUS_LED, LOW);
        delay(50);
      }
      
      // Reiniciar sensor si hay muchos errores consecutivos
      if (consecutive_errors >= MAX_CONSECUTIVE_ERRORS) {
        Serial.print("error=CONSECUTIVE_ANOMALIES:");
        Serial.println(consecutive_errors);
        
        if (!reinitializeSensor()) {
          Serial.println("error=SENSOR_REINIT_FAILED_RESETTING");
          delay(500);
          softwareReset();
        }
        
        delay(READ_INTERVAL);
        return;
      }
    } else {
      consecutive_errors = 0;
    }
    
    // ========= GUARDAR VALORES PARA PRÓXIMA COMPARACIÓN =========
    last_temp = temperature;
    last_pres = pressure;
    last_alt = altitude;
    first_reading = false;
    
    // ========= ENVIAR DATOS =========
    Serial.print("temp=");
    Serial.print(temperature, 2);
    Serial.print(",hum=0.00");  // BMP280 no tiene humedad
    Serial.print(",pres=");
    Serial.print(pressure, 2);
    Serial.print(",alt=");
    Serial.print(altitude, 2);
    Serial.print(",resets=");
    Serial.print(total_resets);
    Serial.print(",errors=");
    Serial.println(consecutive_errors);

    // LED de estado normal
    digitalWrite(STATUS_LED, HIGH);
    delay(50);
    digitalWrite(STATUS_LED, LOW);
  }

  delay(READ_INTERVAL);
}
