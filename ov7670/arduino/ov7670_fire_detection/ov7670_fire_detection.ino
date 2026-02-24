/*
 * ============================================================================
 * OV7670 FIRE DETECTION & VEGETATION INDEX SYSTEM FOR CANSAT
 * ============================================================================
 * 
 * Sistema avanzado de detección de incendios forestales y análisis de 
 * vegetación desde perspectiva aérea para misiones CanSat.
 * 
 * CARACTERÍSTICAS:
 * - Detección de incendios con 8 variables combinadas
 * - Filtrado automático de cielo y nubes
 * - Detección de humo (clave desde el aire)
 * - Índices de vegetación: ExG, VARI, GRVI, NGBDI
 * - Clasificación de 9 tipos de terreno
 * - Optimizado para Arduino R4 WiFi
 * 
 * CONEXIONES OV7670 -> Arduino R4 WiFi:
 *   VCC    -> 3.3V (¡IMPORTANTE: Solo 3.3V!)
 *   GND    -> GND
 *   SIOD   -> SDA (I2C Data)
 *   SIOC   -> SCL (I2C Clock)
 *   XCLK   -> D9 (PWM para generar 8MHz)
 *   PCLK   -> D2 (Pixel Clock - Interrupción)
 *   VSYNC  -> D3 (Frame Sync)
 *   HREF   -> D4 (Line Valid)
 *   D0-D7  -> A0-A7 (Datos paralelos)
 *   RESET  -> 3.3V (tied high)
 *   PWDN   -> GND (tied low)
 * 
 * Autor: CanSat Team
 * Fecha: Enero 2026
 * ============================================================================
 */

#include <Wire.h>

// ============================================================================
// CONFIGURACIÓN DE HARDWARE
// ============================================================================

// Dirección I2C del OV7670 (puede ser 0x21 o 0x42 dependiendo del módulo)
#define OV7670_I2C_ADDR   0x21

// Pines de control
#define PIN_XCLK    9     // Salida PWM para clock del sensor
#define PIN_PCLK    2     // Pixel clock (entrada con interrupción)
#define PIN_VSYNC   3     // Frame sync
#define PIN_HREF    4     // Line valid

// Pines de datos D0-D7 (usando pines analógicos como digitales)
#define PIN_D0      A0
#define PIN_D1      A1
#define PIN_D2      A2
#define PIN_D3      A3
#define PIN_D4      A4    // NOTA: Compartido con SDA si se usa I2C adicional
#define PIN_D5      A5    // NOTA: Compartido con SCL si se usa I2C adicional
#define PIN_D6      6
#define PIN_D7      7

// LED de estado
#define STATUS_LED  LED_BUILTIN

// ============================================================================
// CONFIGURACIÓN DEL ANÁLISIS
// ============================================================================

// Intervalo de muestreo (ms)
#define ANALYSIS_INTERVAL     500

// Número de píxeles a muestrear por frame (limitado por RAM)
#define SAMPLE_SIZE           200

// Resolución simulada para análisis (el OV7670 real es 640x480)
#define IMAGE_WIDTH           320
#define IMAGE_HEIGHT          240

// Umbral mínimo de píxeles válidos (excluyendo cielo)
#define MIN_VALID_PIXELS      50

// ============================================================================
// UMBRALES DE DETECCIÓN - CIELO Y NUBES
// ============================================================================

// Cielo azul
#define SKY_BLUE_MIN          150   // Canal B mínimo
#define SKY_BLUE_DIFF         30    // B debe ser > R + este valor
#define SKY_RED_MAX           200   // Canal R máximo

// Nubes
#define CLOUD_BRIGHTNESS_MIN  200   // Brillo mínimo
#define CLOUD_MAX_DIFF        30    // Máxima diferencia entre canales

// Fracción de imagen considerada "parte superior" para cielo
#define SKY_REGION_FRACTION   0.25

// ============================================================================
// UMBRALES DE DETECCIÓN - FUEGO
// ============================================================================

// Fuego activo (rojo/naranja brillante)
#define FIRE_RED_MIN          200   // R mínimo para fuego
#define FIRE_RG_DIFF          80    // R debe ser > G + este valor
#define FIRE_BRIGHTNESS_MIN   150   // Brillo mínimo

// ============================================================================
// UMBRALES DE DETECCIÓN - HUMO
// ============================================================================

// Humo (gris difuso)
#define SMOKE_BRIGHTNESS_MIN  120
#define SMOKE_BRIGHTNESS_MAX  220
#define SMOKE_MAX_DIFF        40    // Canales similares

// ============================================================================
// UMBRALES DE DETECCIÓN - ZONA QUEMADA
// ============================================================================

#define BURNED_BRIGHTNESS_MAX 60
#define BURNED_MAX_DIFF       20

// ============================================================================
// UMBRALES DE DETECCIÓN - AGUA
// ============================================================================

#define WATER_BLUE_DIFF       40    // B > R + este valor
#define WATER_GREEN_DIFF      20    // B > G + este valor
#define WATER_BRIGHTNESS_MAX  120

// ============================================================================
// UMBRALES DE VEGETACIÓN
// ============================================================================

#define VEG_EXG_HEALTHY       0.25  // ExG > esto = vegetación sana
#define VEG_EXG_STRESSED      0.10  // ExG entre 0.10-0.25 = estresada
#define VEG_DROUGHT_THRESHOLD 0.08  // ExG < esto en zona verde = sequía

// ============================================================================
// PESOS DEL FIRE DETECTION INDEX (FDI) - SUMAN 1.0
// ============================================================================

#define WEIGHT_FIRE_COLOR     0.20
#define WEIGHT_SMOKE          0.20
#define WEIGHT_BURN_SCAR      0.15
#define WEIGHT_RED_DOMINANCE  0.15
#define WEIGHT_THERMAL_ANOM   0.10
#define WEIGHT_EDGE_IRREG     0.10
#define WEIGHT_CLUSTERING     0.05
#define WEIGHT_TEMPORAL       0.05

// ============================================================================
// ENUMS Y ESTRUCTURAS
// ============================================================================

// Tipos de terreno detectables desde el aire
enum TerrainType {
    TERRAIN_SKY = 0,
    TERRAIN_CLOUD,
    TERRAIN_WATER,
    TERRAIN_VEGETATION,
    TERRAIN_DRY_VEG,
    TERRAIN_BARE_SOIL,
    TERRAIN_URBAN,
    TERRAIN_SMOKE,
    TERRAIN_FIRE,
    TERRAIN_BURNED,
    TERRAIN_UNKNOWN
};

// Niveles de riesgo de incendio
enum RiskLevel {
    RISK_NONE = 0,      // 0-15  FDI
    RISK_LOW,           // 15-35 FDI
    RISK_MODERATE,      // 35-55 FDI
    RISK_HIGH,          // 55-75 FDI
    RISK_CRITICAL       // 75-100 FDI
};

// Estructura para almacenar el análisis de un frame
struct FrameAnalysis {
    // Porcentajes de clasificación de terreno
    float pctSky;
    float pctCloud;
    float pctVegetation;
    float pctDryVeg;
    float pctBareGround;
    float pctWater;
    float pctSmoke;
    float pctFire;
    float pctBurned;
    float pctUrban;
    float pctUnknown;
    
    // Componentes del Fire Detection Index
    float fireColorRatio;
    float smokeIndex;
    float burnScarIndex;
    float redDominance;
    float thermalAnomaly;
    float edgeIrregularity;
    float spatialClustering;
    float temporalChange;
    
    // Índice combinado de fuego
    float fireDetectionIndex;
    
    // Índices de vegetación
    float avgExG;
    float avgVARI;
    float avgGRVI;
    float avgNGBDI;
    float vegetationHealth;
    
    // Alertas y estado
    RiskLevel riskLevel;
    bool smokeDetected;
    bool fireDetected;
    bool droughtRisk;
    
    // Metadatos
    unsigned long timestamp;
    int totalPixels;
    int validPixels;    // Excluyendo cielo
    bool frameValid;
};

// ============================================================================
// VARIABLES GLOBALES
// ============================================================================

// Estado del sensor
bool sensorInitialized = false;
bool sensorConnected = false;

// Análisis actual y anterior (para cambio temporal)
FrameAnalysis currentAnalysis;
FrameAnalysis previousAnalysis;
bool hasPreviousFrame = false;

// Contadores
unsigned long frameCount = 0;
unsigned long lastAnalysisTime = 0;
int consecutiveErrors = 0;

// Buffers para píxeles muestreados
uint8_t sampleR[SAMPLE_SIZE];
uint8_t sampleG[SAMPLE_SIZE];
uint8_t sampleB[SAMPLE_SIZE];
uint16_t sampleY[SAMPLE_SIZE];  // Posición Y del píxel (para filtro de cielo)
int sampleCount = 0;

// Promedios RGB del frame anterior (para detección temporal)
float prevAvgR = 0, prevAvgG = 0, prevAvgB = 0;

// ============================================================================
// REGISTROS DEL OV7670
// ============================================================================

// Registros principales del OV7670 para configuración
#define REG_GAIN        0x00
#define REG_BLUE        0x01
#define REG_RED         0x02
#define REG_VREF        0x03
#define REG_COM1        0x04
#define REG_BAVE        0x05
#define REG_GbAVE       0x06
#define REG_AECHH       0x07
#define REG_RAVE        0x08
#define REG_COM2        0x09
#define REG_PID         0x0A
#define REG_VER         0x0B
#define REG_COM3        0x0C
#define REG_COM4        0x0D
#define REG_COM5        0x0E
#define REG_COM6        0x0F
#define REG_AECH        0x10
#define REG_CLKRC       0x11
#define REG_COM7        0x12
#define REG_COM8        0x13
#define REG_COM9        0x14
#define REG_COM10       0x15
#define REG_HSTART      0x17
#define REG_HSTOP       0x18
#define REG_VSTART      0x19
#define REG_VSTOP       0x1A
#define REG_PSHFT       0x1B
#define REG_MIDH        0x1C
#define REG_MIDL        0x1D
#define REG_MVFP        0x1E
#define REG_LAEC        0x1F
#define REG_ADCCTR0     0x20
#define REG_ADCCTR1     0x21
#define REG_ADCCTR2     0x22
#define REG_ADCCTR3     0x23
#define REG_AEW         0x24
#define REG_AEB         0x25
#define REG_VPT         0x26
#define REG_BBIAS       0x27
#define REG_GbBIAS      0x28
#define REG_EXHCH       0x2A
#define REG_EXHCL       0x2B
#define REG_RBIAS       0x2C
#define REG_ADVFL       0x2D
#define REG_ADVFH       0x2E
#define REG_YAVE        0x2F
#define REG_HSYST       0x30
#define REG_HSYEN       0x31
#define REG_HREF        0x32
#define REG_CHLF        0x33
#define REG_ARBLM       0x34
#define REG_ADC         0x37
#define REG_ACOM        0x38
#define REG_OFON        0x39
#define REG_TSLB        0x3A
#define REG_COM11       0x3B
#define REG_COM12       0x3C
#define REG_COM13       0x3D
#define REG_COM14       0x3E
#define REG_EDGE        0x3F
#define REG_COM15       0x40
#define REG_COM16       0x41
#define REG_COM17       0x42
#define REG_AWBC1       0x43
#define REG_AWBC2       0x44
#define REG_AWBC3       0x45
#define REG_AWBC4       0x46
#define REG_AWBC5       0x47
#define REG_AWBC6       0x48
#define REG_REG4B       0x4B
#define REG_DNSTH       0x4C
#define REG_MTX1        0x4F
#define REG_MTX2        0x50
#define REG_MTX3        0x51
#define REG_MTX4        0x52
#define REG_MTX5        0x53
#define REG_MTX6        0x54
#define REG_BRIGHT      0x55
#define REG_CONTRAS     0x56
#define REG_CONTRAS_CTR 0x57
#define REG_MTXS        0x58
#define REG_LCC1        0x62
#define REG_LCC2        0x63
#define REG_LCC3        0x64
#define REG_LCC4        0x65
#define REG_LCC5        0x66
#define REG_MANU        0x67
#define REG_MANV        0x68
#define REG_GFIX        0x69
#define REG_GGAIN       0x6A
#define REG_DBLV        0x6B
#define REG_AWBCTR3     0x6C
#define REG_AWBCTR2     0x6D
#define REG_AWBCTR1     0x6E
#define REG_AWBCTR0     0x6F
#define REG_SCALING_XSC 0x70
#define REG_SCALING_YSC 0x71
#define REG_SCALING_DCWCTR 0x72
#define REG_SCALING_PCLK_DIV 0x73
#define REG_REG74       0x74
#define REG_REG75       0x75
#define REG_REG76       0x76
#define REG_REG77       0x77
#define REG_SLOP        0x7A
#define REG_GAM1        0x7B
#define REG_GAM2        0x7C
#define REG_GAM3        0x7D
#define REG_GAM4        0x7E
#define REG_GAM5        0x7F
#define REG_GAM6        0x80
#define REG_GAM7        0x81
#define REG_GAM8        0x82
#define REG_GAM9        0x83
#define REG_GAM10       0x84
#define REG_GAM11       0x85
#define REG_GAM12       0x86
#define REG_GAM13       0x87
#define REG_GAM14       0x88
#define REG_GAM15       0x89
#define REG_RGB444      0x8C
#define REG_DM_LNL      0x92
#define REG_DM_LNH      0x93
#define REG_LCC6        0x94
#define REG_LCC7        0x95
#define REG_BD50ST      0x9D
#define REG_BD60ST      0x9E
#define REG_HAECC1      0x9F
#define REG_HAECC2      0xA0
#define REG_SCALING_PCLK_DELAY 0xA2
#define REG_NT_CTRL     0xA4
#define REG_BD50MAX     0xA5
#define REG_HAECC3      0xA6
#define REG_HAECC4      0xA7
#define REG_HAECC5      0xA8
#define REG_HAECC6      0xA9
#define REG_HAECC7      0xAA
#define REG_BD60MAX     0xAB
#define REG_STR_OPT     0xAC
#define REG_STR_R       0xAD
#define REG_STR_G       0xAE
#define REG_STR_B       0xAF
#define REG_ABLC1       0xB1
#define REG_THL_ST      0xB3
#define REG_THL_DLT     0xB5
#define REG_AD_CHB      0xBE
#define REG_AD_CHR      0xBF
#define REG_AD_CHGb     0xC0
#define REG_AD_CHGr     0xC1
#define REG_SATCTR      0xC9

// ============================================================================
// FUNCIONES DE COMUNICACIÓN I2C CON OV7670
// ============================================================================

/**
 * Escribe un valor en un registro del OV7670
 */
bool writeRegister(uint8_t reg, uint8_t value) {
    Wire.beginTransmission(OV7670_I2C_ADDR);
    Wire.write(reg);
    Wire.write(value);
    byte error = Wire.endTransmission();
    delay(1);  // Pequeña espera para estabilidad
    return (error == 0);
}

/**
 * Lee un valor de un registro del OV7670
 */
uint8_t readRegister(uint8_t reg) {
    Wire.beginTransmission(OV7670_I2C_ADDR);
    Wire.write(reg);
    Wire.endTransmission();
    
    Wire.requestFrom((uint8_t)OV7670_I2C_ADDR, (uint8_t)1);
    if (Wire.available()) {
        return Wire.read();
    }
    return 0xFF;  // Error
}

/**
 * Verifica la conexión con el OV7670 leyendo el PID
 */
bool checkConnection() {
    uint8_t pid = readRegister(REG_PID);
    uint8_t ver = readRegister(REG_VER);
    
    // El OV7670 debe retornar PID=0x76 y VER=0x73
    if (pid == 0x76 && ver == 0x73) {
        Serial.println("info=OV7670_DETECTED,pid=0x76,ver=0x73");
        return true;
    }
    
    // Algunos módulos pueden tener valores diferentes
    if (pid != 0xFF && ver != 0xFF) {
        Serial.print("warning=UNKNOWN_CAMERA,pid=0x");
        Serial.print(pid, HEX);
        Serial.print(",ver=0x");
        Serial.println(ver, HEX);
        return true;  // Intentar continuar
    }
    
    return false;
}

// ============================================================================
// CONFIGURACIÓN DEL OV7670
// ============================================================================

/**
 * Genera el clock XCLK necesario para el OV7670 usando PWM
 * Arduino R4 WiFi puede generar hasta 48MHz, necesitamos ~8MHz
 */
void startXCLK() {
    // Configurar pin 9 como salida PWM a 8MHz
    // En Arduino R4 WiFi, usamos la frecuencia más alta posible
    pinMode(PIN_XCLK, OUTPUT);
    
    // Generar señal de reloj con analogWrite a máxima frecuencia
    // Nota: La frecuencia real dependerá del timer del R4
    analogWrite(PIN_XCLK, 128);  // 50% duty cycle
    
    Serial.println("info=XCLK_STARTED");
}

/**
 * Configura el OV7670 para captura RGB565
 */
bool configureCamera() {
    Serial.println("info=CONFIGURING_OV7670");
    
    // Reset del sensor
    if (!writeRegister(REG_COM7, 0x80)) {
        Serial.println("error=RESET_FAILED");
        return false;
    }
    delay(100);
    
    // Configuración básica para RGB565
    // COM7: Output format RGB
    writeRegister(REG_COM7, 0x04);
    
    // COM15: RGB565
    writeRegister(REG_COM15, 0xD0);
    
    // CLKRC: Prescaler (divide clock)
    writeRegister(REG_CLKRC, 0x01);
    
    // COM3: Enable scaling
    writeRegister(REG_COM3, 0x04);
    
    // COM14: PCLK scaling
    writeRegister(REG_COM14, 0x19);
    
    // Scaling para QVGA (320x240)
    writeRegister(REG_SCALING_XSC, 0x3A);
    writeRegister(REG_SCALING_YSC, 0x35);
    writeRegister(REG_SCALING_DCWCTR, 0x11);
    writeRegister(REG_SCALING_PCLK_DIV, 0xF1);
    writeRegister(REG_SCALING_PCLK_DELAY, 0x02);
    
    // Configuración de ventana de captura
    writeRegister(REG_HSTART, 0x16);
    writeRegister(REG_HSTOP, 0x04);
    writeRegister(REG_HREF, 0x24);
    writeRegister(REG_VSTART, 0x02);
    writeRegister(REG_VSTOP, 0x7A);
    writeRegister(REG_VREF, 0x0A);
    
    // Configuración de color
    // Matrix para colores naturales
    writeRegister(REG_MTX1, 0x80);
    writeRegister(REG_MTX2, 0x80);
    writeRegister(REG_MTX3, 0x00);
    writeRegister(REG_MTX4, 0x22);
    writeRegister(REG_MTX5, 0x5E);
    writeRegister(REG_MTX6, 0x80);
    writeRegister(REG_MTXS, 0x9E);
    
    // Brillo y contraste
    writeRegister(REG_BRIGHT, 0x00);
    writeRegister(REG_CONTRAS, 0x40);
    
    // Auto White Balance
    writeRegister(REG_COM8, 0x8F);  // AWB, AEC, AGC enabled
    
    // Gamma curve
    writeRegister(REG_SLOP, 0x20);
    writeRegister(REG_GAM1, 0x1C);
    writeRegister(REG_GAM2, 0x28);
    writeRegister(REG_GAM3, 0x3C);
    writeRegister(REG_GAM4, 0x55);
    writeRegister(REG_GAM5, 0x68);
    writeRegister(REG_GAM6, 0x76);
    writeRegister(REG_GAM7, 0x80);
    writeRegister(REG_GAM8, 0x88);
    writeRegister(REG_GAM9, 0x8F);
    writeRegister(REG_GAM10, 0x96);
    writeRegister(REG_GAM11, 0xA3);
    writeRegister(REG_GAM12, 0xAF);
    writeRegister(REG_GAM13, 0xC4);
    writeRegister(REG_GAM14, 0xD7);
    writeRegister(REG_GAM15, 0xE8);
    
    Serial.println("info=OV7670_CONFIGURED");
    return true;
}

// ============================================================================
// FUNCIONES DE CAPTURA DE PÍXELES
// ============================================================================

/**
 * Lee un byte de los pines de datos D0-D7
 */
uint8_t readPixelByte() {
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

/**
 * Espera a que comience un nuevo frame (flanco de bajada de VSYNC)
 */
bool waitForFrame(unsigned long timeout_ms) {
    unsigned long start = millis();
    
    // Esperar a que VSYNC esté alto
    while (digitalRead(PIN_VSYNC) == LOW) {
        if (millis() - start > timeout_ms) return false;
    }
    
    // Esperar flanco de bajada
    while (digitalRead(PIN_VSYNC) == HIGH) {
        if (millis() - start > timeout_ms) return false;
    }
    
    return true;
}

/**
 * Captura una muestra de píxeles del frame actual
 * Debido a limitaciones de RAM, solo muestreamos algunos píxeles
 */
bool capturePixelSamples() {
    sampleCount = 0;
    
    // Esperar inicio de frame
    if (!waitForFrame(100)) {
        Serial.println("error=FRAME_TIMEOUT");
        return false;
    }
    
    // Muestrear píxeles distribuidos por la imagen
    int lineCount = 0;
    int sampleInterval = (IMAGE_HEIGHT * IMAGE_WIDTH) / SAMPLE_SIZE;
    int pixelCounter = 0;
    
    // Procesar líneas
    while (sampleCount < SAMPLE_SIZE) {
        // Esperar HREF alto (línea válida)
        if (digitalRead(PIN_HREF) == HIGH) {
            int colCount = 0;
            
            while (digitalRead(PIN_HREF) == HIGH && sampleCount < SAMPLE_SIZE) {
                // Esperar flanco de subida de PCLK
                while (digitalRead(PIN_PCLK) == LOW);
                
                // Leer primer byte (RGB565 high byte)
                uint8_t byte1 = readPixelByte();
                
                // Esperar siguiente PCLK
                while (digitalRead(PIN_PCLK) == HIGH);
                while (digitalRead(PIN_PCLK) == LOW);
                
                // Leer segundo byte (RGB565 low byte)
                uint8_t byte2 = readPixelByte();
                while (digitalRead(PIN_PCLK) == HIGH);
                
                pixelCounter++;
                colCount++;
                
                // Muestrear cada N píxeles
                if (pixelCounter % sampleInterval == 0) {
                    // Convertir RGB565 a RGB888
                    uint16_t rgb565 = (byte1 << 8) | byte2;
                    
                    uint8_t r = ((rgb565 >> 11) & 0x1F) << 3;  // 5 bits -> 8 bits
                    uint8_t g = ((rgb565 >> 5) & 0x3F) << 2;   // 6 bits -> 8 bits
                    uint8_t b = (rgb565 & 0x1F) << 3;          // 5 bits -> 8 bits
                    
                    sampleR[sampleCount] = r;
                    sampleG[sampleCount] = g;
                    sampleB[sampleCount] = b;
                    sampleY[sampleCount] = lineCount;
                    sampleCount++;
                }
            }
            lineCount++;
        }
        
        // Verificar fin de frame
        if (digitalRead(PIN_VSYNC) == HIGH) {
            break;
        }
    }
    
    return (sampleCount >= MIN_VALID_PIXELS);
}

// ============================================================================
// FUNCIONES DE CLASIFICACIÓN DE PÍXELES
// ============================================================================

/**
 * Determina si un píxel es cielo
 */
bool isSkyPixel(uint8_t r, uint8_t g, uint8_t b, uint16_t y) {
    // El cielo suele estar en la parte superior de la imagen
    bool inSkyRegion = (y < IMAGE_HEIGHT * SKY_REGION_FRACTION);
    
    // Cielo azul: B dominante
    bool isBlueSky = (b > SKY_BLUE_MIN) && 
                     (b > r + SKY_BLUE_DIFF) && 
                     (b > g) && 
                     (r < SKY_RED_MAX);
    
    return inSkyRegion && isBlueSky;
}

/**
 * Determina si un píxel es nube
 */
bool isCloudPixel(uint8_t r, uint8_t g, uint8_t b, uint16_t y) {
    int brightness = (r + g + b) / 3;
    int maxDiff = max(max(abs((int)r - (int)g), abs((int)g - (int)b)), abs((int)r - (int)b));
    
    // Nubes: muy brillantes y colores uniformes
    bool isCloud = (brightness > CLOUD_BRIGHTNESS_MIN) && (maxDiff < CLOUD_MAX_DIFF);
    
    // Más probable en parte superior
    bool inUpperHalf = (y < IMAGE_HEIGHT * 0.5);
    
    return isCloud && inUpperHalf;
}

/**
 * Determina si un píxel es agua
 */
bool isWaterPixel(uint8_t r, uint8_t g, uint8_t b) {
    int brightness = (r + g + b) / 3;
    
    return (b > r + WATER_BLUE_DIFF) && 
           (b > g + WATER_GREEN_DIFF) && 
           (brightness < WATER_BRIGHTNESS_MAX);
}

/**
 * Determina si un píxel es fuego activo
 */
bool isFirePixel(uint8_t r, uint8_t g, uint8_t b) {
    int brightness = (r + g + b) / 3;
    
    return (r > FIRE_RED_MIN) && 
           (r > g + FIRE_RG_DIFF) && 
           (g > b) && 
           (brightness > FIRE_BRIGHTNESS_MIN);
}

/**
 * Calcula el índice de humo para un píxel (0-100)
 */
float calculateSmokeIndex(uint8_t r, uint8_t g, uint8_t b) {
    int brightness = (r + g + b) / 3;
    int maxDiff = max(max(abs((int)r - (int)g), abs((int)g - (int)b)), abs((int)r - (int)b));
    
    // Humo: brillo medio, colores uniformes pero no blancos puros
    bool isSmokeRange = (brightness >= SMOKE_BRIGHTNESS_MIN && brightness <= SMOKE_BRIGHTNESS_MAX);
    bool isGrayish = (maxDiff < SMOKE_MAX_DIFF);
    
    if (isSmokeRange && isGrayish) {
        // Score basado en qué tan "perfecto" es el gris
        return 100.0 - (maxDiff * 2.5);
    }
    return 0.0;
}

/**
 * Determina si un píxel es zona quemada
 */
bool isBurnedPixel(uint8_t r, uint8_t g, uint8_t b) {
    int brightness = (r + g + b) / 3;
    int maxDiff = max(max(abs((int)r - (int)g), abs((int)g - (int)b)), abs((int)r - (int)b));
    
    // Zonas quemadas: muy oscuras y uniformes (negro/marrón oscuro)
    return (brightness < BURNED_BRIGHTNESS_MAX) && (maxDiff < BURNED_MAX_DIFF);
}

/**
 * Calcula el Excess Green Index (ExG) normalizado
 */
float calculateExG(uint8_t r, uint8_t g, uint8_t b) {
    float sum = (float)r + g + b;
    if (sum < 1.0) return 0.0;
    
    float rn = r / sum;
    float gn = g / sum;
    float bn = b / sum;
    
    // ExG = 2*G - R - B, pero normalizado
    float exg = 2.0 * gn - rn - bn;
    
    // Normalizar a rango 0-1 (originalmente -1 a +1)
    return (exg + 1.0) / 2.0;
}

/**
 * Calcula el VARI (Visible Atmospherically Resistant Index)
 * Mejor para condiciones atmosféricas variables
 */
float calculateVARI(uint8_t r, uint8_t g, uint8_t b) {
    float denominator = (float)g + r - b;
    if (abs(denominator) < 1.0) return 0.5;  // Neutral
    
    float vari = ((float)g - r) / denominator;
    
    // Normalizar a 0-1
    return constrain((vari + 1.0) / 2.0, 0.0, 1.0);
}

/**
 * Calcula el GRVI (Green-Red Vegetation Index)
 */
float calculateGRVI(uint8_t r, uint8_t g, uint8_t b) {
    float sum = (float)g + r;
    if (sum < 1.0) return 0.5;
    
    float grvi = ((float)g - r) / sum;
    
    // Normalizar a 0-1
    return (grvi + 1.0) / 2.0;
}

/**
 * Calcula el NGBDI (Normalized Green-Blue Difference Index)
 * Distingue vegetación de agua
 */
float calculateNGBDI(uint8_t r, uint8_t g, uint8_t b) {
    float sum = (float)g + b;
    if (sum < 1.0) return 0.5;
    
    float ngbdi = ((float)g - b) / sum;
    
    // Normalizar a 0-1
    return (ngbdi + 1.0) / 2.0;
}

/**
 * Clasifica un píxel en su tipo de terreno
 */
TerrainType classifyPixel(uint8_t r, uint8_t g, uint8_t b, uint16_t y) {
    // Primero verificar cielo (filtrar)
    if (isSkyPixel(r, g, b, y)) {
        return TERRAIN_SKY;
    }
    
    // Nubes
    if (isCloudPixel(r, g, b, y)) {
        return TERRAIN_CLOUD;
    }
    
    // Fuego activo (alta prioridad)
    if (isFirePixel(r, g, b)) {
        return TERRAIN_FIRE;
    }
    
    // Humo
    if (calculateSmokeIndex(r, g, b) > 50.0) {
        return TERRAIN_SMOKE;
    }
    
    // Zona quemada
    if (isBurnedPixel(r, g, b)) {
        return TERRAIN_BURNED;
    }
    
    // Agua
    if (isWaterPixel(r, g, b)) {
        return TERRAIN_WATER;
    }
    
    // Vegetación
    float exg = calculateExG(r, g, b);
    if (exg > 0.5 + VEG_EXG_HEALTHY) {  // Ajuste por normalización
        return TERRAIN_VEGETATION;
    }
    if (exg > 0.5 + VEG_EXG_STRESSED) {
        return TERRAIN_DRY_VEG;
    }
    
    // Suelo desnudo vs urbano
    int brightness = (r + g + b) / 3;
    if (r > g && g > b && brightness > 80 && brightness < 180) {
        return TERRAIN_BARE_SOIL;
    }
    
    // Por defecto
    return TERRAIN_URBAN;
}

// ============================================================================
// FUNCIONES DE ANÁLISIS DE FRAME
// ============================================================================

/**
 * Analiza todos los píxeles muestreados y genera el análisis del frame
 */
void analyzeFrame() {
    // Inicializar contadores
    int countSky = 0, countCloud = 0, countWater = 0;
    int countVeg = 0, countDryVeg = 0, countBare = 0;
    int countUrban = 0, countSmoke = 0, countFire = 0, countBurned = 0;
    
    float sumExG = 0, sumVARI = 0, sumGRVI = 0, sumNGBDI = 0;
    float sumSmokeIdx = 0;
    float sumR = 0, sumG = 0, sumB = 0;
    int fireColorCount = 0;
    int validVegPixels = 0;
    
    // Analizar cada píxel muestreado
    for (int i = 0; i < sampleCount; i++) {
        uint8_t r = sampleR[i];
        uint8_t g = sampleG[i];
        uint8_t b = sampleB[i];
        uint16_t y = sampleY[i];
        
        // Clasificar píxel
        TerrainType terrain = classifyPixel(r, g, b, y);
        
        switch (terrain) {
            case TERRAIN_SKY:     countSky++; break;
            case TERRAIN_CLOUD:   countCloud++; break;
            case TERRAIN_WATER:   countWater++; break;
            case TERRAIN_VEGETATION: countVeg++; break;
            case TERRAIN_DRY_VEG: countDryVeg++; break;
            case TERRAIN_BARE_SOIL: countBare++; break;
            case TERRAIN_URBAN:   countUrban++; break;
            case TERRAIN_SMOKE:   countSmoke++; break;
            case TERRAIN_FIRE:    countFire++; break;
            case TERRAIN_BURNED:  countBurned++; break;
            default: break;
        }
        
        // Calcular índices solo para píxeles terrestres (no cielo/nubes)
        if (terrain != TERRAIN_SKY && terrain != TERRAIN_CLOUD) {
            sumR += r;
            sumG += g;
            sumB += b;
            
            sumExG += calculateExG(r, g, b);
            sumVARI += calculateVARI(r, g, b);
            sumGRVI += calculateGRVI(r, g, b);
            sumNGBDI += calculateNGBDI(r, g, b);
            
            sumSmokeIdx += calculateSmokeIndex(r, g, b);
            
            // Contar píxeles con colores de fuego
            if (r > 150 && r > g && g > b) {
                fireColorCount++;
            }
            
            // Contar vegetación para promedios
            if (terrain == TERRAIN_VEGETATION || terrain == TERRAIN_DRY_VEG) {
                validVegPixels++;
            }
        }
    }
    
    // Calcular píxeles válidos (terrestres)
    int validPixels = sampleCount - countSky - countCloud;
    if (validPixels < MIN_VALID_PIXELS) {
        validPixels = MIN_VALID_PIXELS;  // Evitar división por cero
    }
    
    // Calcular porcentajes
    float total = (float)sampleCount;
    currentAnalysis.pctSky = (countSky / total) * 100.0;
    currentAnalysis.pctCloud = (countCloud / total) * 100.0;
    currentAnalysis.pctWater = (countWater / total) * 100.0;
    currentAnalysis.pctVegetation = (countVeg / total) * 100.0;
    currentAnalysis.pctDryVeg = (countDryVeg / total) * 100.0;
    currentAnalysis.pctBareGround = (countBare / total) * 100.0;
    currentAnalysis.pctUrban = (countUrban / total) * 100.0;
    currentAnalysis.pctSmoke = (countSmoke / total) * 100.0;
    currentAnalysis.pctFire = (countFire / total) * 100.0;
    currentAnalysis.pctBurned = (countBurned / total) * 100.0;
    
    // Calcular índices de vegetación promedio
    currentAnalysis.avgExG = sumExG / validPixels;
    currentAnalysis.avgVARI = sumVARI / validPixels;
    currentAnalysis.avgGRVI = sumGRVI / validPixels;
    currentAnalysis.avgNGBDI = sumNGBDI / validPixels;
    
    // Calcular salud de vegetación (0-100)
    // Basado en proporción de vegetación sana vs seca
    float vegTotal = countVeg + countDryVeg;
    if (vegTotal > 0) {
        currentAnalysis.vegetationHealth = (countVeg / vegTotal) * 100.0;
    } else {
        currentAnalysis.vegetationHealth = 0.0;
    }
    
    // ========================================
    // CALCULAR COMPONENTES DEL FIRE DETECTION INDEX
    // ========================================
    
    // 1. Fire Color Ratio (% de píxeles con colores de fuego)
    currentAnalysis.fireColorRatio = (fireColorCount / (float)validPixels) * 100.0;
    
    // 2. Smoke Index
    currentAnalysis.smokeIndex = (sumSmokeIdx / validPixels);
    
    // 3. Burn Scar Index
    currentAnalysis.burnScarIndex = currentAnalysis.pctBurned;
    
    // 4. Red Dominance (promedio de dominancia roja)
    float avgR = sumR / validPixels;
    float avgG = sumG / validPixels;
    float avgB = sumB / validPixels;
    float redDom = 0;
    if (avgR + avgG + avgB > 0) {
        redDom = (avgR / (avgR + avgG + avgB)) * 100.0;
    }
    currentAnalysis.redDominance = redDom;
    
    // 5. Thermal Anomaly (fuego en zonas verdes)
    float thermalAnom = 0;
    if (currentAnalysis.pctVegetation > 20 && currentAnalysis.pctFire > 0) {
        thermalAnom = currentAnalysis.pctFire * 5.0;  // Amplificar
    }
    currentAnalysis.thermalAnomaly = constrain(thermalAnom, 0, 100);
    
    // 6. Edge Irregularity (simplificado - basado en varianza)
    // El fuego tiene bordes irregulares
    currentAnalysis.edgeIrregularity = 0;  // Requiere más procesamiento
    
    // 7. Spatial Clustering (simplificado)
    currentAnalysis.spatialClustering = (countFire > 3) ? 50.0 : 0.0;
    
    // 8. Temporal Change
    if (hasPreviousFrame) {
        float deltaR = abs(avgR - prevAvgR);
        float deltaG = abs(avgG - prevAvgG);
        float deltaB = abs(avgB - prevAvgB);
        currentAnalysis.temporalChange = constrain((deltaR + deltaG + deltaB) / 3.0, 0, 100);
    } else {
        currentAnalysis.temporalChange = 0;
    }
    
    // Guardar promedios para próximo frame
    prevAvgR = avgR;
    prevAvgG = avgG;
    prevAvgB = avgB;
    
    // ========================================
    // CALCULAR FIRE DETECTION INDEX COMBINADO
    // ========================================
    
    currentAnalysis.fireDetectionIndex = 
        (WEIGHT_FIRE_COLOR * currentAnalysis.fireColorRatio) +
        (WEIGHT_SMOKE * currentAnalysis.smokeIndex) +
        (WEIGHT_BURN_SCAR * currentAnalysis.burnScarIndex) +
        (WEIGHT_RED_DOMINANCE * (currentAnalysis.redDominance - 33.0)) + // Normalizado
        (WEIGHT_THERMAL_ANOM * currentAnalysis.thermalAnomaly) +
        (WEIGHT_EDGE_IRREG * currentAnalysis.edgeIrregularity) +
        (WEIGHT_CLUSTERING * currentAnalysis.spatialClustering) +
        (WEIGHT_TEMPORAL * currentAnalysis.temporalChange);
    
    currentAnalysis.fireDetectionIndex = constrain(currentAnalysis.fireDetectionIndex, 0, 100);
    
    // ========================================
    // DETERMINAR NIVEL DE RIESGO Y ALERTAS
    // ========================================
    
    float fdi = currentAnalysis.fireDetectionIndex;
    if (fdi < 15) {
        currentAnalysis.riskLevel = RISK_NONE;
    } else if (fdi < 35) {
        currentAnalysis.riskLevel = RISK_LOW;
    } else if (fdi < 55) {
        currentAnalysis.riskLevel = RISK_MODERATE;
    } else if (fdi < 75) {
        currentAnalysis.riskLevel = RISK_HIGH;
    } else {
        currentAnalysis.riskLevel = RISK_CRITICAL;
    }
    
    // Alertas
    currentAnalysis.smokeDetected = (currentAnalysis.pctSmoke > 5.0);
    currentAnalysis.fireDetected = (currentAnalysis.pctFire > 0.5);
    currentAnalysis.droughtRisk = (currentAnalysis.pctDryVeg > 30.0 && currentAnalysis.vegetationHealth < 50.0);
    
    // Metadatos
    currentAnalysis.timestamp = millis();
    currentAnalysis.totalPixels = sampleCount;
    currentAnalysis.validPixels = validPixels;
    currentAnalysis.frameValid = true;
}

// ============================================================================
// FUNCIONES DE SALIDA SERIAL
// ============================================================================

/**
 * Envía los datos del análisis por Serial en formato parseable
 */
void sendAnalysisData() {
    // Línea 1: Clasificación de terreno
    Serial.print("terrain=");
    Serial.print("sky:"); Serial.print(currentAnalysis.pctSky, 1);
    Serial.print(",cloud:"); Serial.print(currentAnalysis.pctCloud, 1);
    Serial.print(",veg:"); Serial.print(currentAnalysis.pctVegetation, 1);
    Serial.print(",dryveg:"); Serial.print(currentAnalysis.pctDryVeg, 1);
    Serial.print(",soil:"); Serial.print(currentAnalysis.pctBareGround, 1);
    Serial.print(",water:"); Serial.print(currentAnalysis.pctWater, 1);
    Serial.print(",smoke:"); Serial.print(currentAnalysis.pctSmoke, 1);
    Serial.print(",fire:"); Serial.print(currentAnalysis.pctFire, 1);
    Serial.print(",burned:"); Serial.print(currentAnalysis.pctBurned, 1);
    Serial.print(",urban:"); Serial.println(currentAnalysis.pctUrban, 1);
    
    // Línea 2: Índices de fuego
    Serial.print("fire=");
    Serial.print("fdi:"); Serial.print(currentAnalysis.fireDetectionIndex, 1);
    Serial.print(",smoke:"); Serial.print(currentAnalysis.smokeIndex, 1);
    Serial.print(",color:"); Serial.print(currentAnalysis.fireColorRatio, 1);
    Serial.print(",burn:"); Serial.print(currentAnalysis.burnScarIndex, 1);
    Serial.print(",risk:"); Serial.println(currentAnalysis.riskLevel);
    
    // Línea 3: Índices de vegetación
    Serial.print("veg=");
    Serial.print("exg:"); Serial.print(currentAnalysis.avgExG, 3);
    Serial.print(",vari:"); Serial.print(currentAnalysis.avgVARI, 3);
    Serial.print(",grvi:"); Serial.print(currentAnalysis.avgGRVI, 3);
    Serial.print(",ngbdi:"); Serial.print(currentAnalysis.avgNGBDI, 3);
    Serial.print(",health:"); Serial.println(currentAnalysis.vegetationHealth, 1);
    
    // Línea 4: Alertas (solo si hay alguna)
    if (currentAnalysis.smokeDetected || currentAnalysis.fireDetected || currentAnalysis.droughtRisk) {
        Serial.print("alert=");
        if (currentAnalysis.fireDetected) Serial.print("FIRE_DETECTED,");
        if (currentAnalysis.smokeDetected) Serial.print("SMOKE_DETECTED,");
        if (currentAnalysis.droughtRisk) Serial.print("DROUGHT_RISK,");
        if (currentAnalysis.riskLevel >= RISK_HIGH) Serial.print("HIGH_FIRE_RISK,");
        Serial.println();
    }
    
    // Línea 5: Metadatos
    Serial.print("meta=");
    Serial.print("time:"); Serial.print(currentAnalysis.timestamp);
    Serial.print(",pixels:"); Serial.print(currentAnalysis.validPixels);
    Serial.print(",frame:"); Serial.println(frameCount);
}

/**
 * Muestra indicación visual del nivel de riesgo
 */
void showRiskLED() {
    switch (currentAnalysis.riskLevel) {
        case RISK_NONE:
            // LED apagado o parpadeo lento
            digitalWrite(STATUS_LED, (millis() / 2000) % 2);
            break;
            
        case RISK_LOW:
            // Parpadeo lento
            digitalWrite(STATUS_LED, (millis() / 1000) % 2);
            break;
            
        case RISK_MODERATE:
            // Parpadeo medio
            digitalWrite(STATUS_LED, (millis() / 500) % 2);
            break;
            
        case RISK_HIGH:
            // Parpadeo rápido
            digitalWrite(STATUS_LED, (millis() / 200) % 2);
            break;
            
        case RISK_CRITICAL:
            // LED siempre encendido + patrón triple
            if ((millis() / 100) % 10 < 3) {
                digitalWrite(STATUS_LED, (millis() / 50) % 2);
            } else {
                digitalWrite(STATUS_LED, HIGH);
            }
            break;
    }
}

// ============================================================================
// MODO SIMULACIÓN (cuando no hay cámara conectada)
// ============================================================================

/**
 * Genera datos simulados para pruebas sin hardware
 */
void generateSimulatedData() {
    // Generar píxeles simulados con distribución realista
    sampleCount = SAMPLE_SIZE;
    
    for (int i = 0; i < SAMPLE_SIZE; i++) {
        // Posición Y simulada
        sampleY[i] = (i * IMAGE_HEIGHT) / SAMPLE_SIZE;
        
        // Simular diferentes zonas
        float yFrac = (float)sampleY[i] / IMAGE_HEIGHT;
        
        if (yFrac < 0.15) {
            // Cielo (parte superior)
            sampleR[i] = 100 + random(30);
            sampleG[i] = 150 + random(30);
            sampleB[i] = 220 + random(35);
        } else if (yFrac < 0.2 && random(100) < 30) {
            // Nubes ocasionales
            sampleR[i] = 230 + random(25);
            sampleG[i] = 230 + random(25);
            sampleB[i] = 230 + random(25);
        } else if (random(100) < 60) {
            // Vegetación (mayoritaria)
            if (random(100) < 70) {
                // Vegetación sana
                sampleR[i] = 50 + random(40);
                sampleG[i] = 100 + random(50);
                sampleB[i] = 40 + random(30);
            } else {
                // Vegetación seca
                sampleR[i] = 120 + random(40);
                sampleG[i] = 110 + random(30);
                sampleB[i] = 60 + random(30);
            }
        } else if (random(100) < 5) {
            // Simular humo ocasional
            uint8_t gray = 140 + random(40);
            sampleR[i] = gray + random(10) - 5;
            sampleG[i] = gray + random(10) - 5;
            sampleB[i] = gray + random(10) - 5;
        } else if (random(100) < 2) {
            // Simular fuego muy ocasional
            sampleR[i] = 220 + random(35);
            sampleG[i] = 100 + random(50);
            sampleB[i] = 30 + random(30);
        } else {
            // Suelo
            sampleR[i] = 140 + random(40);
            sampleG[i] = 120 + random(30);
            sampleB[i] = 90 + random(30);
        }
    }
}

// ============================================================================
// SETUP
// ============================================================================

void setup() {
    // Inicializar LED de estado
    pinMode(STATUS_LED, OUTPUT);
    digitalWrite(STATUS_LED, HIGH);
    
    // Inicializar Serial
    Serial.begin(115200);
    while (!Serial) {
        delay(10);
    }
    
    Serial.println();
    Serial.println("============================================");
    Serial.println("OV7670 FIRE DETECTION & VEGETATION ANALYSIS");
    Serial.println("CanSat Aerial Imaging System v1.0");
    Serial.println("============================================");
    Serial.println();
    
    // Inicializar pines de datos como entrada
    pinMode(PIN_D0, INPUT);
    pinMode(PIN_D1, INPUT);
    pinMode(PIN_D2, INPUT);
    pinMode(PIN_D3, INPUT);
    pinMode(PIN_D4, INPUT);
    pinMode(PIN_D5, INPUT);
    pinMode(PIN_D6, INPUT);
    pinMode(PIN_D7, INPUT);
    
    // Pines de control como entrada
    pinMode(PIN_PCLK, INPUT);
    pinMode(PIN_VSYNC, INPUT);
    pinMode(PIN_HREF, INPUT);
    
    // Inicializar I2C
    Wire.begin();
    delay(100);
    
    // Generar clock para el OV7670
    startXCLK();
    delay(500);
    
    // Verificar conexión con el sensor
    Serial.println("info=SEARCHING_OV7670");
    
    if (checkConnection()) {
        sensorConnected = true;
        
        // Configurar el sensor
        if (configureCamera()) {
            sensorInitialized = true;
            Serial.println("info=CAMERA_READY");
        } else {
            Serial.println("error=CAMERA_CONFIG_FAILED");
            Serial.println("info=USING_SIMULATION_MODE");
        }
    } else {
        Serial.println("warning=OV7670_NOT_FOUND");
        Serial.println("info=USING_SIMULATION_MODE");
        sensorConnected = false;
    }
    
    // Inicializar estructuras
    memset(&currentAnalysis, 0, sizeof(FrameAnalysis));
    memset(&previousAnalysis, 0, sizeof(FrameAnalysis));
    
    Serial.println();
    Serial.println("info=SYSTEM_READY");
    Serial.println("--------------------------------------------");
    
    digitalWrite(STATUS_LED, LOW);
    delay(1000);
}

// ============================================================================
// LOOP PRINCIPAL
// ============================================================================

void loop() {
    unsigned long currentTime = millis();
    
    // Ejecutar análisis cada ANALYSIS_INTERVAL ms
    if (currentTime - lastAnalysisTime >= ANALYSIS_INTERVAL) {
        lastAnalysisTime = currentTime;
        frameCount++;
        
        // Capturar o simular píxeles
        bool captureSuccess = false;
        
        if (sensorInitialized && sensorConnected) {
            // Intentar captura real
            captureSuccess = capturePixelSamples();
            
            if (!captureSuccess) {
                consecutiveErrors++;
                Serial.print("warning=CAPTURE_FAILED,errors=");
                Serial.println(consecutiveErrors);
                
                if (consecutiveErrors > 5) {
                    Serial.println("error=TOO_MANY_ERRORS,SWITCHING_TO_SIMULATION");
                    sensorInitialized = false;
                }
            } else {
                consecutiveErrors = 0;
            }
        }
        
        if (!captureSuccess) {
            // Usar datos simulados
            generateSimulatedData();
        }
        
        // Guardar análisis anterior
        if (currentAnalysis.frameValid) {
            memcpy(&previousAnalysis, &currentAnalysis, sizeof(FrameAnalysis));
            hasPreviousFrame = true;
        }
        
        // Analizar frame
        analyzeFrame();
        
        // Enviar datos por Serial
        sendAnalysisData();
        
        // Mostrar estado en LED
        showRiskLED();
    }
    
    // Actualizar LED de riesgo durante la espera
    showRiskLED();
}
