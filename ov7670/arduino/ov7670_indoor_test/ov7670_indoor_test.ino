/*
 * ============================================================================
 * OV7670 FIRE DETECTION - INDOOR TEST VERSION
 * ============================================================================
 * 
 * Versión simplificada y optimizada para pruebas en interiores.
 * - Envío de datos más frecuente (100ms)
 * - Sin modo simulación (usa datos reales solamente)
 * - Optimizado para detectar llamas de mechero
 * 
 * Autor: CanSat Team
 * Fecha: Febrero 2026
 * ============================================================================
 */

#include <Wire.h>

// ============================================================================
// CONFIGURACIÓN 
// ============================================================================

#define OV7670_I2C_ADDR   0x21
#define PIN_XCLK    9
#define PIN_PCLK    2
#define PIN_VSYNC   3
#define PIN_HREF    4
// IMPORTANTE: D4 y D5 NO pueden usar A4/A5 porque son los pines I2C (SDA/SCL)
// Los movemos a pines digitales libres
#define PIN_D0      A0
#define PIN_D1      A1
#define PIN_D2      A2
#define PIN_D3      A3
#define PIN_D4      10    // Cambiado de A4 - evita conflicto I2C
#define PIN_D5      11    // Cambiado de A5 - evita conflicto I2C  
#define PIN_D6      5     // Cambiado de 6 para mejor distribución
#define PIN_D7      8     // Cambiado de 7 para evitar conflictos
#define STATUS_LED  LED_BUILTIN

// INTERVALO RÁPIDO para pruebas en tiempo real
#define ANALYSIS_INTERVAL     100   // 100ms = 10 Hz

#define SAMPLE_SIZE           100   // Menos muestras = más rápido
#define IMAGE_HEIGHT          240

// ============================================================================
// UMBRALES - OPTIMIZADOS PARA MECHERO
// ============================================================================

// Fuego (llama de mechero)
#define FIRE_RED_MIN          180   // Rojo mínimo
#define FIRE_RG_RATIO         1.3   // R/G > 1.3
#define FIRE_BRIGHTNESS_MIN   120   // Brillo mínimo

// Humo
#define SMOKE_BRIGHTNESS_MIN  100
#define SMOKE_BRIGHTNESS_MAX  200
#define SMOKE_MAX_DIFF        30

// ============================================================================
// VARIABLES
// ============================================================================

uint8_t sampleR[SAMPLE_SIZE];
uint8_t sampleG[SAMPLE_SIZE];
uint8_t sampleB[SAMPLE_SIZE];
int sampleCount = 0;

bool cameraOK = false;
unsigned long lastAnalysis = 0;
unsigned long frameCount = 0;

// Resultados del análisis
float pctFire = 0;
float pctSmoke = 0;
float avgR = 0, avgG = 0, avgB = 0;
float fireProbability = 0;
int riskLevel = 0;

// ============================================================================
// FUNCIONES I2C
// ============================================================================

bool writeReg(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(OV7670_I2C_ADDR);
    Wire.write(reg);
    Wire.write(val);
    return (Wire.endTransmission() == 0);
}

uint8_t readReg(uint8_t reg) {
    Wire.beginTransmission(OV7670_I2C_ADDR);
    Wire.write(reg);
    Wire.endTransmission();
    Wire.requestFrom((uint8_t)OV7670_I2C_ADDR, (uint8_t)1);
    if (Wire.available()) return Wire.read();
    return 0xFF;
}

bool checkCamera() {
    uint8_t pid = readReg(0x0A);  // PID register
    uint8_t ver = readReg(0x0B);  // VER register
    
    Serial.print("info=CAMERA_CHECK,pid=0x");
    Serial.print(pid, HEX);
    Serial.print(",ver=0x");
    Serial.println(ver, HEX);
    
    return (pid == 0x76);  // OV7670 PID is 0x76
}

void configCamera() {
    writeReg(0x12, 0x80);  // Reset
    delay(100);
    writeReg(0x12, 0x04);  // RGB output
    writeReg(0x40, 0xD0);  // RGB565
    writeReg(0x11, 0x01);  // Clock prescaler
    Serial.println("info=CAMERA_CONFIGURED");
}

// ============================================================================
// LECTURA DE PÍXELES
// ============================================================================

uint8_t readByte() {
    uint8_t data = 0;
    data |= (digitalRead(PIN_D0) << 0);
    data |= (digitalRead(PIN_D1) << 1);
    data |= (digitalRead(PIN_D2) << 2);
    data |= (digitalRead(PIN_D3) << 3);
    data |= (digitalRead(PIN_D4) << 4);
    data |= (digitalRead(PIN_D5) << 5);
    data |= (digitalRead(PIN_D6) << 6);
    data |= (digitalRead(PIN_D7) << 7);
    return data;
}

// Espera con timeout para evitar bucles infinitos
bool waitForPCLK(bool state, unsigned long timeoutUs) {
    unsigned long start = micros();
    while (digitalRead(PIN_PCLK) != state) {
        if (micros() - start > timeoutUs) return false;
    }
    return true;
}

// Captura rápida de muestras con protección de timeout
void captureQuick() {
    sampleCount = 0;
    
    // Timeout de 100ms para toda la captura
    unsigned long timeout = millis() + 100;
    
    // Esperar flanco de VSYNC (inicio de frame)
    // Primero esperar a que esté LOW
    while (digitalRead(PIN_VSYNC) == HIGH && millis() < timeout);
    // Luego esperar a que suba (inicio real del frame)
    while (digitalRead(PIN_VSYNC) == LOW && millis() < timeout);
    // Esperar a que baje (área activa)
    while (digitalRead(PIN_VSYNC) == HIGH && millis() < timeout);
    
    if (millis() >= timeout) {
        Serial.println("warning=VSYNC_TIMEOUT");
        return;
    }
    
    int pixelNum = 0;
    int targetInterval = 50;  // Capturar cada 50 píxeles
    unsigned long captureTimeout = millis() + 150;  // Timeout para captura
    int failedReads = 0;
    
    while (sampleCount < SAMPLE_SIZE && millis() < captureTimeout) {
        // Verificar si estamos en línea activa
        if (digitalRead(PIN_HREF) == HIGH) {
            // Esperar flanco ascendente de PCLK con timeout (10us max)
            if (!waitForPCLK(HIGH, 10)) {
                failedReads++;
                if (failedReads > 100) break;  // Demasiados fallos
                continue;
            }
            uint8_t b1 = readByte();
            
            // Esperar flanco descendente
            if (!waitForPCLK(LOW, 10)) continue;
            
            // Esperar segundo byte (segundo flanco)
            if (!waitForPCLK(HIGH, 10)) continue;
            uint8_t b2 = readByte();
            if (!waitForPCLK(LOW, 10)) continue;
            
            pixelNum++;
            
            // Muestrear cada N píxeles para distribuir en toda la imagen
            if (pixelNum % targetInterval == 0) {
                // RGB565 -> RGB888
                // Formato: RRRRR GGGGGG BBBBB
                uint16_t rgb565 = (b1 << 8) | b2;
                sampleR[sampleCount] = ((rgb565 >> 11) & 0x1F) << 3;
                sampleG[sampleCount] = ((rgb565 >> 5) & 0x3F) << 2;
                sampleB[sampleCount] = (rgb565 & 0x1F) << 3;
                sampleCount++;
            }
        }
        
        // Fin de frame
        if (digitalRead(PIN_VSYNC) == HIGH) break;
    }
    
    // Debug: mostrar estadísticas de captura
    if (sampleCount < 10) {
        Serial.print("debug=pixels:");
        Serial.print(pixelNum);
        Serial.print(",samples:");
        Serial.print(sampleCount);
        Serial.print(",fails:");
        Serial.println(failedReads);
    }
}

// ============================================================================
// ANÁLISIS - SIMPLIFICADO PARA VELOCIDAD
// ============================================================================

void analyzePixels() {
    if (sampleCount < 10) {
        Serial.println("warning=NOT_ENOUGH_SAMPLES");
        return;
    }
    
    int fireCount = 0;
    int smokeCount = 0;
    float sumR = 0, sumG = 0, sumB = 0;
    
    for (int i = 0; i < sampleCount; i++) {
        uint8_t r = sampleR[i];
        uint8_t g = sampleG[i];
        uint8_t b = sampleB[i];
        
        sumR += r;
        sumG += g;
        sumB += b;
        
        int brightness = (r + g + b) / 3;
        
        // *** DETECCIÓN DE FUEGO ***
        // Llama de mechero: rojo dominante, brillante
        if (r > FIRE_RED_MIN && 
            r > g * FIRE_RG_RATIO && 
            r > b * 1.5 &&
            brightness > FIRE_BRIGHTNESS_MIN) {
            fireCount++;
        }
        
        // *** DETECCIÓN DE HUMO ***
        int maxDiff = max(max(abs(r-g), abs(g-b)), abs(r-b));
        if (brightness >= SMOKE_BRIGHTNESS_MIN && 
            brightness <= SMOKE_BRIGHTNESS_MAX &&
            maxDiff < SMOKE_MAX_DIFF) {
            smokeCount++;
        }
    }
    
    // Calcular porcentajes
    float n = (float)sampleCount;
    pctFire = (fireCount / n) * 100.0;
    pctSmoke = (smokeCount / n) * 100.0;
    avgR = sumR / n;
    avgG = sumG / n;
    avgB = sumB / n;
    
    // PROBABILIDAD DE INCENDIO simplificada
    fireProbability = 0;
    
    // Factor 1: Píxeles de fuego (40%)
    fireProbability += pctFire * 4.0;
    
    // Factor 2: Humo (30%)
    fireProbability += pctSmoke * 3.0;
    
    // Factor 3: Rojo dominante (20%)
    if (avgR > avgG && avgR > avgB) {
        float redDom = avgR / max(1.0f, (avgR + avgG + avgB) / 3.0f);
        fireProbability += (redDom - 0.33) * 200;
    }
    
    // Factor 4: Brillo alto (10%)
    float avgBrightness = (avgR + avgG + avgB) / 3.0;
    if (avgBrightness > 150) {
        fireProbability += 10;
    }
    
    fireProbability = constrain(fireProbability, 0, 100);
    
    // Nivel de riesgo
    if (fireProbability < 15) riskLevel = 0;
    else if (fireProbability < 35) riskLevel = 1;
    else if (fireProbability < 55) riskLevel = 2;
    else if (fireProbability < 75) riskLevel = 3;
    else riskLevel = 4;
}

// ============================================================================
// OUTPUT
// ============================================================================

void sendData() {
    // Formato compatible con dashboard
    Serial.print("terrain=");
    Serial.print("sky:0,cloud:0,veg:0,dryveg:0,soil:");
    Serial.print(100 - pctFire - pctSmoke, 1);
    Serial.print(",water:0,smoke:");
    Serial.print(pctSmoke, 1);
    Serial.print(",fire:");
    Serial.print(pctFire, 1);
    Serial.println(",burned:0,urban:0");
    
    Serial.print("fire=fdi:");
    Serial.print(fireProbability, 1);
    Serial.print(",smoke:");
    Serial.print(pctSmoke, 1);
    Serial.print(",color:");
    Serial.print(pctFire, 1);
    Serial.print(",burn:0,risk:");
    Serial.println(riskLevel);
    
    Serial.print("veg=exg:0,vari:0,grvi:0,ngbdi:0,health:0");
    Serial.println();
    
    Serial.print("raw=r:");
    Serial.print(avgR, 0);
    Serial.print(",g:");
    Serial.print(avgG, 0);
    Serial.print(",b:");
    Serial.print(avgB, 0);
    Serial.print(",samples:");
    Serial.println(sampleCount);
    
    if (pctFire > 5 || fireProbability > 50) {
        Serial.println("alert=FIRE_DETECTED");
    } else if (pctSmoke > 10) {
        Serial.println("alert=SMOKE_DETECTED");
    }
    
    Serial.println("---");
}

void updateLED() {
    switch (riskLevel) {
        case 0: digitalWrite(STATUS_LED, LOW); break;
        case 1: digitalWrite(STATUS_LED, (millis() / 1000) % 2); break;
        case 2: digitalWrite(STATUS_LED, (millis() / 500) % 2); break;
        case 3: digitalWrite(STATUS_LED, (millis() / 200) % 2); break;
        case 4: digitalWrite(STATUS_LED, (millis() / 100) % 2); break;
    }
}

// ============================================================================
// SETUP
// ============================================================================

void setup() {
    pinMode(STATUS_LED, OUTPUT);
    digitalWrite(STATUS_LED, HIGH);
    
    Serial.begin(115200);
    while (!Serial) delay(10);
    
    Serial.println();
    Serial.println("========================================");
    Serial.println("OV7670 FIRE DETECTION - INDOOR TEST");
    Serial.println("Optimizado para pruebas con mechero");
    Serial.println("========================================");
    
    // Pines de datos como entrada
    pinMode(PIN_D0, INPUT);
    pinMode(PIN_D1, INPUT);
    pinMode(PIN_D2, INPUT);
    pinMode(PIN_D3, INPUT);
    pinMode(PIN_D4, INPUT);
    pinMode(PIN_D5, INPUT);
    pinMode(PIN_D6, INPUT);
    pinMode(PIN_D7, INPUT);
    pinMode(PIN_PCLK, INPUT);
    pinMode(PIN_VSYNC, INPUT);
    pinMode(PIN_HREF, INPUT);
    
    // Iniciar I2C
    Wire.begin();
    delay(100);
    
    // Clock para OV7670
    pinMode(PIN_XCLK, OUTPUT);
    analogWrite(PIN_XCLK, 128);
    delay(500);
    
    // Verificar cámara
    cameraOK = checkCamera();
    
    if (cameraOK) {
        configCamera();
        Serial.println("info=CAMERA_READY");
    } else {
        Serial.println("warning=CAMERA_NOT_DETECTED");
        Serial.println("info=WILL_TRY_ANYWAY");
    }
    
    Serial.println();
    Serial.println("info=READY");
    Serial.print("info=INTERVAL=");
    Serial.print(ANALYSIS_INTERVAL);
    Serial.println("ms");
    Serial.println("========================================");
    
    digitalWrite(STATUS_LED, LOW);
    delay(500);
}

// ============================================================================
// LOOP
// ============================================================================

void loop() {
    unsigned long now = millis();
    
    if (now - lastAnalysis >= ANALYSIS_INTERVAL) {
        lastAnalysis = now;
        frameCount++;
        
        // Capturar
        captureQuick();
        
        // Analizar
        analyzePixels();
        
        // Enviar resultados
        sendData();
    }
    
    // Actualizar LED
    updateLED();
}
