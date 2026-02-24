/*
 * ============================================================================
 * OV7670 DIAGNOSTIC TEST - FULL CONNECTION TESTING
 * ============================================================================
 * 
 * Test exhaustivo para diagnosticar problemas de conexión del OV7670.
 * Prueba cada pin individualmente y reporta el estado.
 * 
 * Autor: CanSat Team
 * Fecha: Febrero 2026
 * ============================================================================
 */

#include <Wire.h>

// ============================================================================
// CONFIGURACIÓN DE PINES
// ============================================================================

#define OV7670_ADDR_1   0x21    // Dirección I2C alternativa 1
#define OV7670_ADDR_2   0x42    // Dirección I2C alternativa 2

#define PIN_XCLK    9     // Clock salida (MCLK)
#define PIN_PCLK    2     // Pixel clock entrada
#define PIN_VSYNC   3     // Frame sync (VS)
#define PIN_HREF    4     // Line valid (HS)

#define PIN_D0      A0
#define PIN_D1      A1
#define PIN_D2      A2
#define PIN_D3      A3
// IMPORTANTE: D4 y D5 NO pueden usar A4/A5 porque son los pines I2C (SDA/SCL)
#define PIN_D4      10    // Cambiado de A4 - evita conflicto I2C
#define PIN_D5      11    // Cambiado de A5 - evita conflicto I2C
#define PIN_D6      5     // Cambiado para mejor distribución
#define PIN_D7      8     // Cambiado para evitar conflictos

#define LED_PIN     LED_BUILTIN

// ============================================================================
// VARIABLES DE TEST
// ============================================================================

bool i2cFound = false;
uint8_t i2cAddress = 0;

int vsyncPulses = 0;
int hrefPulses = 0;
int pclkPulses = 0;

unsigned long testStartTime = 0;

// ============================================================================
// TEST 1: ESCANEO I2C
// ============================================================================

void testI2C() {
    Serial.println();
    Serial.println("========================================");
    Serial.println("TEST 1: ESCANEO BUS I2C");
    Serial.println("========================================");
    Serial.println("Conexiones requeridas:");
    Serial.println("  SDA (OV7670) -> SDA (Arduino)");
    Serial.println("  SCL (OV7670) -> SCL (Arduino)");
    Serial.println("  VCC -> 3.3V");
    Serial.println("  GND -> GND");
    Serial.println("----------------------------------------");
    
    int devicesFound = 0;
    
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        byte error = Wire.endTransmission();
        
        if (error == 0) {
            Serial.print("[ENCONTRADO] Dispositivo en direccion 0x");
            Serial.print(addr, HEX);
            
            if (addr == 0x21 || addr == 0x42) {
                Serial.println(" <- Posible OV7670!");
                i2cFound = true;
                i2cAddress = addr;
            } else {
                Serial.println();
            }
            devicesFound++;
        }
    }
    
    if (devicesFound == 0) {
        Serial.println("[ERROR] No se encontraron dispositivos I2C");
        Serial.println();
        Serial.println("Posibles causas:");
        Serial.println("  1. SDA no conectado o mal conectado");
        Serial.println("  2. SCL no conectado o mal conectado");
        Serial.println("  3. VCC no conectado (camara sin alimentacion)");
        Serial.println("  4. GND no conectado");
        Serial.println("  5. Camara danada");
    } else {
        Serial.print("[OK] Encontrados ");
        Serial.print(devicesFound);
        Serial.println(" dispositivo(s)");
    }
    
    Serial.println("----------------------------------------");
    if (i2cFound) {
        Serial.println("RESULTADO: PASS - OV7670 detectado por I2C");
    } else {
        Serial.println("RESULTADO: FAIL - OV7670 NO detectado");
    }
    Serial.println();
}

// ============================================================================
// TEST 2: REGISTROS OV7670
// ============================================================================

uint8_t readReg(uint8_t addr, uint8_t reg) {
    Wire.beginTransmission(addr);
    Wire.write(reg);
    if (Wire.endTransmission() != 0) return 0xFF;
    Wire.requestFrom(addr, (uint8_t)1);
    if (Wire.available()) return Wire.read();
    return 0xFF;
}

void testRegisters() {
    Serial.println("========================================");
    Serial.println("TEST 2: REGISTROS DEL OV7670");
    Serial.println("========================================");
    
    if (!i2cFound) {
        Serial.println("[SKIP] No se puede probar - I2C no disponible");
        Serial.println();
        return;
    }
    
    Serial.print("Usando direccion I2C: 0x");
    Serial.println(i2cAddress, HEX);
    Serial.println("----------------------------------------");
    
    // Leer registros de identificación
    uint8_t pid = readReg(i2cAddress, 0x0A);   // PID
    uint8_t ver = readReg(i2cAddress, 0x0B);   // VER  
    uint8_t midh = readReg(i2cAddress, 0x1C);  // Manufacturer ID High
    uint8_t midl = readReg(i2cAddress, 0x1D);  // Manufacturer ID Low
    
    Serial.print("PID  (0x0A): 0x"); Serial.print(pid, HEX);
    if (pid == 0x76) Serial.println(" <- CORRECTO (OV7670)");
    else if (pid == 0xFF) Serial.println(" <- ERROR de lectura");
    else Serial.println(" <- Valor inesperado");
    
    Serial.print("VER  (0x0B): 0x"); Serial.print(ver, HEX);
    if (ver == 0x73) Serial.println(" <- CORRECTO (OV7670)");
    else if (ver == 0xFF) Serial.println(" <- ERROR de lectura");
    else Serial.println(" <- Valor inesperado");
    
    Serial.print("MIDH (0x1C): 0x"); Serial.print(midh, HEX);
    if (midh == 0x7F) Serial.println(" <- CORRECTO (OmniVision)");
    else Serial.println();
    
    Serial.print("MIDL (0x1D): 0x"); Serial.print(midl, HEX);
    if (midl == 0xA2) Serial.println(" <- CORRECTO (OmniVision)");
    else Serial.println();
    
    Serial.println("----------------------------------------");
    if (pid == 0x76 && ver == 0x73) {
        Serial.println("RESULTADO: PASS - OV7670 identificado correctamente");
    } else if (pid == 0xFF) {
        Serial.println("RESULTADO: FAIL - No se pueden leer registros");
    } else {
        Serial.println("RESULTADO: WARNING - Sensor detectado pero IDs no coinciden");
    }
    Serial.println();
}

// ============================================================================
// TEST 3: SEÑAL XCLK/MCLK (Clock de entrada)
// ============================================================================

void testXCLK() {
    Serial.println("========================================");
    Serial.println("TEST 3: SENAL XCLK/MCLK (Clock)");
    Serial.println("========================================");
    Serial.println("Conexion requerida:");
    Serial.println("  MCLK (OV7670) <- D9 (Arduino)");
    Serial.println("----------------------------------------");
    
    // Generar señal de clock
    pinMode(PIN_XCLK, OUTPUT);
    analogWrite(PIN_XCLK, 128);
    
    Serial.println("[INFO] Generando senal PWM en D9...");
    Serial.println("[INFO] Frecuencia aproximada: ~490 Hz (PWM estandar)");
    Serial.println();
    Serial.println("Nota: El OV7670 necesita esta senal para funcionar.");
    Serial.println("      Sin MCLK, la camara no genera VSYNC ni PCLK.");
    Serial.println("----------------------------------------");
    Serial.println("RESULTADO: Clock generado - Verificar conexion MCLK");
    Serial.println();
    
    delay(500);  // Dar tiempo a la cámara para estabilizarse
}

// ============================================================================
// TEST 4: SEÑAL VSYNC (Frame Sync)
// ============================================================================

volatile int vsyncCounter = 0;

void vsyncISR() {
    vsyncCounter++;
}

void testVSYNC() {
    Serial.println("========================================");
    Serial.println("TEST 4: SENAL VSYNC/VS (Frame Sync)");
    Serial.println("========================================");
    Serial.println("Conexion requerida:");
    Serial.println("  VS (OV7670) -> D3 (Arduino)");
    Serial.println("----------------------------------------");
    
    pinMode(PIN_VSYNC, INPUT);
    vsyncCounter = 0;
    
    // Usar interrupción para contar pulsos
    attachInterrupt(digitalPinToInterrupt(PIN_VSYNC), vsyncISR, RISING);
    
    Serial.println("[INFO] Contando pulsos VSYNC durante 2 segundos...");
    
    unsigned long start = millis();
    while (millis() - start < 2000) {
        // Esperar
    }
    
    detachInterrupt(digitalPinToInterrupt(PIN_VSYNC));
    
    Serial.print("[INFO] Pulsos VSYNC detectados: ");
    Serial.println(vsyncCounter);
    
    // También verificar el estado actual
    Serial.print("[INFO] Estado actual del pin D3: ");
    Serial.println(digitalRead(PIN_VSYNC) ? "HIGH" : "LOW");
    
    Serial.println("----------------------------------------");
    
    if (vsyncCounter > 20) {
        float fps = vsyncCounter / 2.0;
        Serial.print("RESULTADO: PASS - ");
        Serial.print(fps, 1);
        Serial.println(" frames/segundo");
    } else if (vsyncCounter > 0) {
        Serial.println("RESULTADO: WARNING - Pocos pulsos (senal debil?)");
    } else {
        Serial.println("RESULTADO: FAIL - No hay senal VSYNC");
        Serial.println();
        Serial.println("Posibles causas:");
        Serial.println("  1. Pin VS no conectado a D3");
        Serial.println("  2. MCLK no llega a la camara (camara no funciona)");
        Serial.println("  3. Camara no configurada/inicializada");
        Serial.println("  4. Problemas de alimentacion");
    }
    Serial.println();
}

// ============================================================================
// TEST 5: SEÑAL HREF/HS (Line Sync)
// ============================================================================

void testHREF() {
    Serial.println("========================================");
    Serial.println("TEST 5: SENAL HREF/HS (Line Sync)");
    Serial.println("========================================");
    Serial.println("Conexion requerida:");
    Serial.println("  HS (OV7670) -> D4 (Arduino)");
    Serial.println("----------------------------------------");
    
    pinMode(PIN_HREF, INPUT);
    int hrefTransitions = 0;
    int lastState = digitalRead(PIN_HREF);
    
    Serial.println("[INFO] Contando transiciones HREF durante 1 segundo...");
    
    unsigned long start = millis();
    while (millis() - start < 1000) {
        int currentState = digitalRead(PIN_HREF);
        if (currentState != lastState) {
            hrefTransitions++;
            lastState = currentState;
        }
    }
    
    Serial.print("[INFO] Transiciones HREF: ");
    Serial.println(hrefTransitions);
    
    Serial.print("[INFO] Estado actual del pin D4: ");
    Serial.println(digitalRead(PIN_HREF) ? "HIGH" : "LOW");
    
    Serial.println("----------------------------------------");
    
    if (hrefTransitions > 100) {
        Serial.println("RESULTADO: PASS - Senal HREF activa");
    } else if (hrefTransitions > 0) {
        Serial.println("RESULTADO: WARNING - Pocas transiciones");
    } else {
        Serial.println("RESULTADO: FAIL - No hay senal HREF");
    }
    Serial.println();
}

// ============================================================================
// TEST 6: SEÑAL PCLK (Pixel Clock)
// ============================================================================

volatile int pclkCounter = 0;

void pclkISR() {
    pclkCounter++;
}

void testPCLK() {
    Serial.println("========================================");
    Serial.println("TEST 6: SENAL PCLK (Pixel Clock)");
    Serial.println("========================================");
    Serial.println("Conexion requerida:");
    Serial.println("  PCLK (OV7670) -> D2 (Arduino)");
    Serial.println("----------------------------------------");
    
    pinMode(PIN_PCLK, INPUT);
    pclkCounter = 0;
    
    // El PCLK es muy rápido, solo contamos un poco
    attachInterrupt(digitalPinToInterrupt(PIN_PCLK), pclkISR, RISING);
    
    Serial.println("[INFO] Contando pulsos PCLK durante 100ms...");
    
    delay(100);
    
    detachInterrupt(digitalPinToInterrupt(PIN_PCLK));
    
    Serial.print("[INFO] Pulsos PCLK detectados: ");
    Serial.println(pclkCounter);
    
    Serial.print("[INFO] Estado actual del pin D2: ");
    Serial.println(digitalRead(PIN_PCLK) ? "HIGH" : "LOW");
    
    Serial.println("----------------------------------------");
    
    if (pclkCounter > 1000) {
        float khz = pclkCounter / 100.0;
        Serial.print("RESULTADO: PASS - ");
        Serial.print(khz, 1);
        Serial.println(" KHz (aprox)");
    } else if (pclkCounter > 0) {
        Serial.println("RESULTADO: WARNING - Frecuencia baja");
    } else {
        Serial.println("RESULTADO: FAIL - No hay senal PCLK");
    }
    Serial.println();
}

// ============================================================================
// TEST 7: BUS DE DATOS D0-D7
// ============================================================================

void testDataBus() {
    Serial.println("========================================");
    Serial.println("TEST 7: BUS DE DATOS D0-D7");
    Serial.println("========================================");
    Serial.println("Conexiones requeridas:");
    Serial.println("  D0 -> A0, D1 -> A1, D2 -> A2, D3 -> A3");
    Serial.println("  D4 -> D10, D5 -> D11, D6 -> D5, D7 -> D8");
    Serial.println("----------------------------------------");
    
    pinMode(PIN_D0, INPUT);
    pinMode(PIN_D1, INPUT);
    pinMode(PIN_D2, INPUT);
    pinMode(PIN_D3, INPUT);
    pinMode(PIN_D4, INPUT);
    pinMode(PIN_D5, INPUT);
    pinMode(PIN_D6, INPUT);
    pinMode(PIN_D7, INPUT);
    
    // Leer varias veces para ver si cambia
    Serial.println("[INFO] Leyendo bus de datos 5 veces (100ms entre lecturas):");
    
    int allSame = 1;
    uint8_t prevByte = 0;
    
    for (int i = 0; i < 5; i++) {
        uint8_t dataByte = 0;
        dataByte |= (digitalRead(PIN_D0) << 0);
        dataByte |= (digitalRead(PIN_D1) << 1);
        dataByte |= (digitalRead(PIN_D2) << 2);
        dataByte |= (digitalRead(PIN_D3) << 3);
        dataByte |= (digitalRead(PIN_D4) << 4);
        dataByte |= (digitalRead(PIN_D5) << 5);
        dataByte |= (digitalRead(PIN_D6) << 6);
        dataByte |= (digitalRead(PIN_D7) << 7);
        
        Serial.print("  Lectura ");
        Serial.print(i + 1);
        Serial.print(": 0x");
        if (dataByte < 16) Serial.print("0");
        Serial.print(dataByte, HEX);
        Serial.print(" (");
        for (int b = 7; b >= 0; b--) {
            Serial.print((dataByte >> b) & 1);
        }
        Serial.println(")");
        
        if (i > 0 && dataByte != prevByte) allSame = 0;
        prevByte = dataByte;
        
        delay(100);
    }
    
    Serial.println("----------------------------------------");
    
    if (!allSame) {
        Serial.println("RESULTADO: PASS - Bus de datos activo (valores cambian)");
    } else if (prevByte == 0x00) {
        Serial.println("RESULTADO: WARNING - Todos los bits en 0");
        Serial.println("  Puede ser normal si no hay frame activo");
    } else if (prevByte == 0xFF) {
        Serial.println("RESULTADO: WARNING - Todos los bits en 1");
        Serial.println("  Verificar conexiones de datos");
    } else {
        Serial.println("RESULTADO: WARNING - Valores estaticos");
    }
    Serial.println();
}

// ============================================================================
// TEST 8: RESUMEN Y RECOMENDACIONES
// ============================================================================

void showSummary() {
    Serial.println("========================================");
    Serial.println("RESUMEN DE DIAGNOSTICO");
    Serial.println("========================================");
    
    bool allOK = true;
    
    Serial.print("I2C:    ");
    if (i2cFound) {
        Serial.println("OK");
    } else {
        Serial.println("FALLO - Verificar SDA/SCL/VCC/GND");
        allOK = false;
    }
    
    Serial.print("VSYNC:  ");
    if (vsyncCounter > 20) {
        Serial.println("OK");
    } else {
        Serial.println("FALLO - Verificar VS->D3 y MCLK->D9");
        allOK = false;
    }
    
    Serial.print("PCLK:   ");
    if (pclkCounter > 100) {
        Serial.println("OK");
    } else {
        Serial.println("FALLO - Verificar PCLK->D2");
        allOK = false;
    }
    
    Serial.println("----------------------------------------");
    
    if (allOK) {
        Serial.println("ESTADO: CAMARA LISTA PARA USAR");
    } else {
        Serial.println("ESTADO: HAY PROBLEMAS DE CONEXION");
        Serial.println();
        Serial.println("PASOS A SEGUIR:");
        if (!i2cFound) {
            Serial.println("1. Verificar alimentacion 3.3V y GND");
            Serial.println("2. Verificar conexiones SDA y SCL");
        }
        if (vsyncCounter == 0) {
            Serial.println("3. Verificar que MCLK este conectado a D9");
            Serial.println("4. Verificar que VS este conectado a D3");
        }
        if (pclkCounter == 0) {
            Serial.println("5. Verificar que PCLK este conectado a D2");
        }
    }
    
    Serial.println("========================================");
}

// ============================================================================
// SETUP
// ============================================================================

void setup() {
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, HIGH);
    
    Serial.begin(115200);
    while (!Serial) delay(10);
    
    delay(1000);  // Esperar a que serial esté listo
    
    Serial.println();
    Serial.println("########################################");
    Serial.println("#   OV7670 DIAGNOSTIC TEST             #");
    Serial.println("#   Prueba completa de conexiones      #");
    Serial.println("########################################");
    Serial.println();
    Serial.println("Este test verifica todas las conexiones");
    Serial.println("necesarias para que funcione el OV7670.");
    Serial.println();
    
    Wire.begin();
    delay(100);
    
    // Ejecutar todos los tests
    testI2C();
    testRegisters();
    testXCLK();
    
    // Esperar un poco para que la cámara se estabilice con el clock
    delay(500);
    
    testVSYNC();
    testHREF();
    testPCLK();
    testDataBus();
    
    showSummary();
    
    digitalWrite(LED_PIN, LOW);
}

// ============================================================================
// LOOP
// ============================================================================

void loop() {
    // Parpadear LED para indicar que terminó
    digitalWrite(LED_PIN, (millis() / 1000) % 2);
    
    // Repetir tests cada 30 segundos
    static unsigned long lastTest = 0;
    if (millis() - lastTest > 30000) {
        lastTest = millis();
        Serial.println();
        Serial.println("=== REPITIENDO TESTS ===");
        Serial.println();
        
        vsyncCounter = 0;
        pclkCounter = 0;
        
        testVSYNC();
        testPCLK();
        showSummary();
    }
}
