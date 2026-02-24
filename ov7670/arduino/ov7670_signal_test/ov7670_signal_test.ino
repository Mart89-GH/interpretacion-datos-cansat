/*
 * OV7670 SIGNAL TEST - DIAGNÓSTICO DE SEÑALES
 * ============================================
 * Prueba cada señal individualmente para encontrar el problema.
 */

#include <Wire.h>

#define PIN_XCLK    9
#define PIN_PCLK    2
#define PIN_VSYNC   3
#define PIN_HREF    4

#define PIN_D0      A0
#define PIN_D1      A1
#define PIN_D2      A2
#define PIN_D3      A3
#define PIN_D4      10
#define PIN_D5      11
#define PIN_D6      5
#define PIN_D7      8

void setup() {
    Serial.begin(115200);
    while (!Serial) delay(10);
    
    Serial.println();
    Serial.println("================================");
    Serial.println("OV7670 SIGNAL TEST");
    Serial.println("================================");
    
    // Configurar pines
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
    
    // ===========================================
    // TEST 1: GENERAR XCLK
    // ===========================================
    Serial.println();
    Serial.println("[TEST 1] Generando XCLK en D9...");
    pinMode(PIN_XCLK, OUTPUT);
    analogWrite(PIN_XCLK, 128);
    Serial.println("   XCLK activo. Si el LED de la camara parpadea, esta funcionando.");
    delay(500);
    
    // ===========================================
    // TEST 2: I2C SIMPLE
    // ===========================================
    Serial.println();
    Serial.println("[TEST 2] Escaneando I2C...");
    Wire.begin();
    Wire.setClock(100000);  // Velocidad baja para mayor compatibilidad
    delay(100);
    
    bool found = false;
    for (uint8_t addr = 0x20; addr <= 0x22; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.print("   ENCONTRADO en 0x");
            Serial.println(addr, HEX);
            found = true;
        }
    }
    // También probar 0x42 (7-bit: 0x21)
    Wire.beginTransmission(0x42);
    if (Wire.endTransmission() == 0) {
        Serial.println("   ENCONTRADO en 0x42");
        found = true;
    }
    
    if (!found) {
        Serial.println("   NO SE ENCONTRO CAMARA POR I2C");
        Serial.println("   -> Verifica: VCC=3.3V, GND, SDA, SCL");
    }
    
    Serial.println();
    Serial.println("================================");
    Serial.println("MONITOREANDO SENALES en tiempo real");
    Serial.println("(Si todo esta en 0, las senales no llegan)");
    Serial.println("================================");
}

void loop() {
    static unsigned long lastPrint = 0;
    static int vsyncCount = 0;
    static int vsyncLast = 0;
    static int hrefCount = 0;
    static int hrefLast = 0;
    static int pclkCount = 0;
    static int pclkLast = 0;
    
    // Contar transiciones de VSYNC
    int vsyncNow = digitalRead(PIN_VSYNC);
    if (vsyncNow != vsyncLast && vsyncNow == HIGH) {
        vsyncCount++;
    }
    vsyncLast = vsyncNow;
    
    // Contar transiciones de HREF
    int hrefNow = digitalRead(PIN_HREF);
    if (hrefNow != hrefLast && hrefNow == HIGH) {
        hrefCount++;
    }
    hrefLast = hrefNow;
    
    // Contar transiciones de PCLK (muy rápido, solo muestreo)
    int pclkNow = digitalRead(PIN_PCLK);
    if (pclkNow != pclkLast) {
        pclkCount++;
    }
    pclkLast = pclkNow;
    
    // Leer bus de datos
    uint8_t dataByte = 0;
    dataByte |= digitalRead(PIN_D0);
    dataByte |= digitalRead(PIN_D1) << 1;
    dataByte |= digitalRead(PIN_D2) << 2;
    dataByte |= digitalRead(PIN_D3) << 3;
    dataByte |= digitalRead(PIN_D4) << 4;
    dataByte |= digitalRead(PIN_D5) << 5;
    dataByte |= digitalRead(PIN_D6) << 6;
    dataByte |= digitalRead(PIN_D7) << 7;
    
    // Imprimir cada segundo
    if (millis() - lastPrint >= 1000) {
        Serial.print("VSYNC: ");
        Serial.print(vsyncCount);
        Serial.print("/s | HREF: ");
        Serial.print(hrefCount);
        Serial.print("/s | PCLK: ");
        Serial.print(pclkCount);
        Serial.print("/s | DATA: 0x");
        if (dataByte < 16) Serial.print("0");
        Serial.print(dataByte, HEX);
        
        // Diagnóstico
        if (vsyncCount == 0 && hrefCount == 0 && pclkCount == 0) {
            Serial.print(" <- SIN SENALES!");
        } else if (vsyncCount > 0 && vsyncCount < 50) {
            Serial.print(" <- OK (");
            Serial.print(vsyncCount);
            Serial.print(" FPS)");
        }
        
        Serial.println();
        
        vsyncCount = 0;
        hrefCount = 0;
        pclkCount = 0;
        lastPrint = millis();
    }
}
