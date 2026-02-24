/*
 * OV7670 BASIC PHOTO CAPTURE
 * ==========================
 * Código ultra básico para capturar fotos y enviarlas por serial.
 * 
 * IMPORTANTE: Dado que Arduino UNO tiene poca RAM (2KB), 
 * capturamos imágenes muy pequeñas (40x30 pixels).
 * 
 * Conexiones:
 *   VCC    -> 3.3V
 *   GND    -> GND
 *   SCL    -> SCL
 *   SDA    -> SDA
 *   XCLK   -> D9
 *   PCLK   -> D2
 *   VSYNC  -> D3
 *   HREF   -> D4
 *   D0-D3  -> A0-A3
 *   D4     -> D10
 *   D5     -> D11
 *   D6     -> D5
 *   D7     -> D8
 */

#include <Wire.h>

// Direcciones I2C del OV7670
#define OV7670_ADDR   0x21

// Pines de sincronización
#define PIN_XCLK    9
#define PIN_PCLK    2
#define PIN_VSYNC   3
#define PIN_HREF    4

// Pines de datos
#define PIN_D0      A0
#define PIN_D1      A1
#define PIN_D2      A2
#define PIN_D3      A3
#define PIN_D4      10
#define PIN_D5      11
#define PIN_D6      5
#define PIN_D7      8

// Resolución muy pequeña para caber en RAM
#define IMG_WIDTH   40
#define IMG_HEIGHT  30

// Buffer pequeño (solo 1 línea a la vez)
uint8_t lineBuffer[IMG_WIDTH * 2];  // RGB565 = 2 bytes por pixel

// ============================================================================
// FUNCIONES I2C PARA CONFIGURAR LA CÁMARA
// ============================================================================

bool writeReg(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(OV7670_ADDR);
    Wire.write(reg);
    Wire.write(val);
    return (Wire.endTransmission() == 0);
}

uint8_t readReg(uint8_t reg) {
    Wire.beginTransmission(OV7670_ADDR);
    Wire.write(reg);
    Wire.endTransmission();
    Wire.requestFrom((uint8_t)OV7670_ADDR, (uint8_t)1);
    if (Wire.available()) return Wire.read();
    return 0xFF;
}

// ============================================================================
// CONFIGURACIÓN BÁSICA DEL OV7670
// ============================================================================

void configureCamera() {
    Serial.println("Configurando camara...");
    
    // Reset
    writeReg(0x12, 0x80);
    delay(100);
    
    // Configuración básica RGB565
    writeReg(0x12, 0x04);   // RGB output
    writeReg(0x11, 0x80);   // Clock prescaler (lento para Arduino)
    writeReg(0x0C, 0x00);   // COM3 - no scaling
    writeReg(0x3E, 0x00);   // COM14 - no scaling
    writeReg(0x40, 0xD0);   // COM15 - RGB565
    writeReg(0x42, 0x08);   // COM17
    
    // Resolución QQVGA (160x120) - la más pequeña nativa
    writeReg(0x70, 0x3A);   // SCALING_XSC
    writeReg(0x71, 0x35);   // SCALING_YSC
    writeReg(0x72, 0x11);   // SCALING_DCWCTR
    writeReg(0x73, 0xF0);   // SCALING_PCLK_DIV
    writeReg(0xA2, 0x02);   // SCALING_PCLK_DELAY
    
    // Color bars para test (descomentar para probar)
    // writeReg(0x42, 0x08);  // Activa barras de color
    
    Serial.println("Camara configurada");
    delay(300);
}

// ============================================================================
// LECTURA DE DATOS DE LA CÁMARA
// ============================================================================

inline uint8_t readByte() {
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

// Esperar con timeout (microsegundos)
bool waitFor(uint8_t pin, bool state, unsigned long timeoutUs) {
    unsigned long start = micros();
    while (digitalRead(pin) != state) {
        if (micros() - start > timeoutUs) return false;
    }
    return true;
}

// ============================================================================
// CAPTURA Y ENVÍO DE FOTO
// ============================================================================

void captureAndSendPhoto() {
    Serial.println("PHOTO_START");
    Serial.print("SIZE:");
    Serial.print(IMG_WIDTH);
    Serial.print("x");
    Serial.println(IMG_HEIGHT);
    
    // Esperar inicio de frame (VSYNC)
    if (!waitFor(PIN_VSYNC, HIGH, 100000)) {
        Serial.println("ERROR:VSYNC_TIMEOUT");
        return;
    }
    if (!waitFor(PIN_VSYNC, LOW, 100000)) {
        Serial.println("ERROR:VSYNC_LOW_TIMEOUT");
        return;
    }
    
    int linesRead = 0;
    int skipLines = 4;  // Saltar líneas para submuestrear de 120 a 30
    int lineCounter = 0;
    
    // Timeout general para toda la captura
    unsigned long captureTimeout = millis() + 5000;
    
    while (linesRead < IMG_HEIGHT && millis() < captureTimeout) {
        // Esperar inicio de línea (HREF HIGH)
        if (!waitFor(PIN_HREF, HIGH, 50000)) continue;
        
        lineCounter++;
        
        // Solo capturar cada N líneas
        if (lineCounter % skipLines != 0) {
            // Saltar esta línea
            while (digitalRead(PIN_HREF) == HIGH && millis() < captureTimeout);
            continue;
        }
        
        // Capturar píxeles de esta línea
        int pixelCount = 0;
        int skipPixels = 4;  // Saltar pixels para submuestrear de 160 a 40
        int pixelCounter = 0;
        int bufferPos = 0;
        
        while (digitalRead(PIN_HREF) == HIGH && pixelCount < IMG_WIDTH && millis() < captureTimeout) {
            // Esperar PCLK HIGH (primer byte)
            if (!waitFor(PIN_PCLK, HIGH, 100)) continue;
            uint8_t b1 = readByte();
            if (!waitFor(PIN_PCLK, LOW, 100)) continue;
            
            // Esperar PCLK HIGH (segundo byte)
            if (!waitFor(PIN_PCLK, HIGH, 100)) continue;
            uint8_t b2 = readByte();
            if (!waitFor(PIN_PCLK, LOW, 100)) continue;
            
            pixelCounter++;
            
            // Solo guardar cada N píxeles
            if (pixelCounter % skipPixels == 0 && bufferPos < IMG_WIDTH * 2) {
                lineBuffer[bufferPos++] = b1;
                lineBuffer[bufferPos++] = b2;
                pixelCount++;
            }
        }
        
        // Enviar la línea capturada
        if (pixelCount > 0) {
            Serial.print("LINE:");
            Serial.println(linesRead);
            
            // Enviar datos en hexadecimal
            for (int i = 0; i < pixelCount * 2; i++) {
                if (lineBuffer[i] < 16) Serial.print("0");
                Serial.print(lineBuffer[i], HEX);
            }
            Serial.println();
            
            linesRead++;
        }
        
        // Esperar fin de línea
        while (digitalRead(PIN_HREF) == HIGH && millis() < captureTimeout);
    }
    
    Serial.print("LINES_READ:");
    Serial.println(linesRead);
    Serial.println("PHOTO_END");
}

// ============================================================================
// SETUP
// ============================================================================

void setup() {
    Serial.begin(115200);
    while (!Serial) delay(10);
    
    Serial.println();
    Serial.println("================================");
    Serial.println("OV7670 BASIC PHOTO CAPTURE");
    Serial.println("================================");
    
    // Configurar pines
    pinMode(PIN_XCLK, OUTPUT);
    pinMode(PIN_PCLK, INPUT);
    pinMode(PIN_VSYNC, INPUT);
    pinMode(PIN_HREF, INPUT);
    pinMode(PIN_D0, INPUT);
    pinMode(PIN_D1, INPUT);
    pinMode(PIN_D2, INPUT);
    pinMode(PIN_D3, INPUT);
    pinMode(PIN_D4, INPUT);
    pinMode(PIN_D5, INPUT);
    pinMode(PIN_D6, INPUT);
    pinMode(PIN_D7, INPUT);
    
    // Generar clock para la cámara
    analogWrite(PIN_XCLK, 128);
    delay(100);
    
    // Iniciar I2C
    Wire.begin();
    delay(100);
    
    // Verificar cámara
    Serial.print("Buscando camara... ");
    Wire.beginTransmission(OV7670_ADDR);
    if (Wire.endTransmission() == 0) {
        Serial.println("ENCONTRADA");
        
        uint8_t pid = readReg(0x0A);
        Serial.print("PID: 0x");
        Serial.println(pid, HEX);
        
        configureCamera();
    } else {
        Serial.println("NO ENCONTRADA");
        Serial.println("Verifica las conexiones");
    }
    
    Serial.println();
    Serial.println("Comandos:");
    Serial.println("  'p' = Capturar foto");
    Serial.println("  't' = Test de barras de color");
    Serial.println("================================");
}

// ============================================================================
// LOOP
// ============================================================================

void loop() {
    if (Serial.available()) {
        char cmd = Serial.read();
        
        if (cmd == 'p' || cmd == 'P') {
            captureAndSendPhoto();
        }
        else if (cmd == 't' || cmd == 'T') {
            // Activar barras de color para test
            writeReg(0x42, 0x08);
            Serial.println("Barras de color activadas");
            delay(100);
            captureAndSendPhoto();
            writeReg(0x42, 0x00);
            Serial.println("Barras de color desactivadas");
        }
    }
    
    delay(10);
}
