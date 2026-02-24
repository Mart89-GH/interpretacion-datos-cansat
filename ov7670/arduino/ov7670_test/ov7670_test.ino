/*
 * ============================================================================
 * OV7670 CONNECTION TEST
 * ============================================================================
 * 
 * Test básico para verificar la conexión I2C con el módulo OV7670.
 * Este sketch lee los registros de identificación del sensor.
 * 
 * CONEXIONES MÍNIMAS PARA TEST:
 *   VCC    -> 3.3V
 *   GND    -> GND
 *   SIOD   -> SDA
 *   SIOC   -> SCL
 *   XCLK   -> D9 (necesario para que el sensor responda)
 *   RESET  -> 3.3V
 *   PWDN   -> GND
 * 
 * ============================================================================
 */

#include <Wire.h>

// Posibles direcciones I2C del OV7670
#define OV7670_ADDR_1   0x21
#define OV7670_ADDR_2   0x42

// Pin para generar clock
#define PIN_XCLK  9

// Registros de identificación
#define REG_PID   0x0A  // Product ID (debería ser 0x76)
#define REG_VER   0x0B  // Version (debería ser 0x73)
#define REG_MIDH  0x1C  // Manufacturer ID High (debería ser 0x7F)
#define REG_MIDL  0x1D  // Manufacturer ID Low (debería ser 0xA2)

uint8_t ov7670_addr = 0;

/**
 * Escribe un valor en un registro
 */
bool writeRegister(uint8_t addr, uint8_t reg, uint8_t value) {
    Wire.beginTransmission(addr);
    Wire.write(reg);
    Wire.write(value);
    return (Wire.endTransmission() == 0);
}

/**
 * Lee un valor de un registro
 */
uint8_t readRegister(uint8_t addr, uint8_t reg) {
    Wire.beginTransmission(addr);
    Wire.write(reg);
    if (Wire.endTransmission() != 0) {
        return 0xFF;
    }
    
    Wire.requestFrom(addr, (uint8_t)1);
    if (Wire.available()) {
        return Wire.read();
    }
    return 0xFF;
}

/**
 * Escanea el bus I2C buscando el OV7670
 */
void scanI2C() {
    Serial.println("\n=== Escaneando bus I2C ===\n");
    
    int deviceCount = 0;
    
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        byte error = Wire.endTransmission();
        
        if (error == 0) {
            Serial.print("Dispositivo encontrado en 0x");
            if (addr < 16) Serial.print("0");
            Serial.print(addr, HEX);
            
            // Verificar si es OV7670
            if (addr == OV7670_ADDR_1 || addr == OV7670_ADDR_2) {
                Serial.print(" <- Posible OV7670!");
                ov7670_addr = addr;
            }
            
            Serial.println();
            deviceCount++;
        }
    }
    
    if (deviceCount == 0) {
        Serial.println("No se encontraron dispositivos I2C.");
        Serial.println("\nVerifica las conexiones:");
        Serial.println("  - VCC conectado a 3.3V (NO 5V!)");
        Serial.println("  - GND conectado");
        Serial.println("  - SIOD (SDA) conectado al pin SDA");
        Serial.println("  - SIOC (SCL) conectado al pin SCL");
        Serial.println("  - XCLK recibiendo señal de clock");
        Serial.println("  - RESET conectado a 3.3V");
        Serial.println("  - PWDN conectado a GND");
    } else {
        Serial.print("\nTotal de dispositivos encontrados: ");
        Serial.println(deviceCount);
    }
}

/**
 * Lee e imprime información del OV7670
 */
void readCameraInfo() {
    if (ov7670_addr == 0) {
        Serial.println("\nNo se detectó OV7670. No se puede leer información.");
        return;
    }
    
    Serial.println("\n=== Información del OV7670 ===\n");
    
    // Leer PID
    uint8_t pid = readRegister(ov7670_addr, REG_PID);
    Serial.print("Product ID (PID):       0x");
    Serial.print(pid, HEX);
    if (pid == 0x76) {
        Serial.println(" ✓ (OV7670 confirmado)");
    } else if (pid == 0xFF) {
        Serial.println(" ✗ (Error de lectura)");
    } else {
        Serial.print(" ? (Esperado: 0x76, sensor: OV76");
        Serial.print(pid, HEX);
        Serial.println(")");
    }
    
    // Leer Version
    uint8_t ver = readRegister(ov7670_addr, REG_VER);
    Serial.print("Version (VER):          0x");
    Serial.print(ver, HEX);
    if (ver == 0x73) {
        Serial.println(" ✓ (Versión estándar)");
    } else if (ver == 0xFF) {
        Serial.println(" ✗ (Error de lectura)");
    } else {
        Serial.println(" (Versión no estándar)");
    }
    
    // Leer Manufacturer ID
    uint8_t midh = readRegister(ov7670_addr, REG_MIDH);
    uint8_t midl = readRegister(ov7670_addr, REG_MIDL);
    Serial.print("Manufacturer ID:        0x");
    Serial.print(midh, HEX);
    Serial.print(midl, HEX);
    if (midh == 0x7F && midl == 0xA2) {
        Serial.println(" ✓ (OmniVision)");
    } else {
        Serial.println(" (Esperado: 0x7FA2)");
    }
    
    // Resultado final
    Serial.println("\n=== Resultado ===\n");
    if (pid == 0x76 && ver == 0x73) {
        Serial.println("✓ OV7670 detectado correctamente!");
        Serial.println("  El sensor está listo para usar.");
        Serial.println("  Puedes proceder con el sketch principal.");
    } else if (pid != 0xFF) {
        Serial.println("? Sensor detectado pero IDs no coinciden.");
        Serial.println("  Podría ser una variante del OV7670 o un clon.");
        Serial.println("  Intenta usar el sketch principal de todos modos.");
    } else {
        Serial.println("✗ No se pudo comunicar con el OV7670.");
        Serial.println("  Verifica:");
        Serial.println("  1. Que el módulo recibe los 3.3V correctamente");
        Serial.println("  2. Que XCLK está generando señal");
        Serial.println("  3. Las conexiones I2C (SDA/SCL)");
    }
}

/**
 * Intenta hacer un reset del sensor
 */
void resetSensor() {
    if (ov7670_addr == 0) return;
    
    Serial.println("\nIntentando reset del sensor...");
    
    // Escribir 0x80 en COM7 hace un reset suave
    if (writeRegister(ov7670_addr, 0x12, 0x80)) {
        Serial.println("Reset enviado correctamente.");
        delay(100);
    } else {
        Serial.println("Error al enviar reset.");
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial) delay(10);
    
    Serial.println();
    Serial.println("============================================");
    Serial.println("     OV7670 CONNECTION TEST");
    Serial.println("============================================");
    
    // Iniciar clock para el OV7670
    Serial.println("\nGenerando señal XCLK en pin 9...");
    pinMode(PIN_XCLK, OUTPUT);
    analogWrite(PIN_XCLK, 128);  // PWM 50%
    delay(500);
    Serial.println("XCLK activo.");
    
    // Iniciar I2C
    Serial.println("Iniciando I2C...");
    Wire.begin();
    delay(100);
    
    // Escanear bus I2C
    scanI2C();
    
    // Leer información del sensor
    readCameraInfo();
    
    // Reset del sensor
    if (ov7670_addr != 0) {
        resetSensor();
        delay(100);
        readCameraInfo();
    }
    
    Serial.println("\n============================================");
    Serial.println("Test completado. Revisa los resultados arriba.");
    Serial.println("============================================");
}

void loop() {
    // Parpadear LED para indicar que está funcionando
    digitalWrite(LED_BUILTIN, (millis() / 500) % 2);
    
    // Re-escanear cada 10 segundos si no hay sensor
    static unsigned long lastScan = 0;
    if (ov7670_addr == 0 && millis() - lastScan > 10000) {
        lastScan = millis();
        Serial.println("\n--- Re-escaneando... ---");
        scanI2C();
        if (ov7670_addr != 0) {
            readCameraInfo();
        }
    }
}
