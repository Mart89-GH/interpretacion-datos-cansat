/*
 * ============================================================================
 * VEGETATION TYPE CLASSIFICATION & FIRE PROBABILITY ANALYZER
 * ============================================================================
 * 
 * Código especializado para la clasificación precisa de tipos de vegetación
 * y cálculo de probabilidad de incendio basado en características de la zona.
 * 
 * TIPOS DE VEGETACIÓN DETECTADOS:
 * - Bosque denso (coníferas, caducifolios)
 * - Matorral mediterráneo
 * - Pastizal/Pradera
 * - Cultivos agrícolas
 * - Vegetación riparia (junto a ríos)
 * - Vegetación estresada/seca
 * - Suelo desnudo
 * 
 * FACTORES DE PROBABILIDAD DE INCENDIO:
 * 1. Tipo de vegetación (combustibilidad)
 * 2. Estado hídrico (sequedad)
 * 3. Densidad de biomasa
 * 4. Continuidad horizontal del combustible
 * 5. Presencia de material seco
 * 6. Indicadores de estrés vegetal
 * 
 * Autor: CanSat Team
 * Fecha: Febrero 2026
 * ============================================================================
 */

#include <Wire.h>

// ============================================================================
// CONFIGURACIÓN DE HARDWARE
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

// ============================================================================
// CONFIGURACIÓN DEL ANÁLISIS
// ============================================================================

#define ANALYSIS_INTERVAL     500
#define SAMPLE_SIZE           250   // Más muestras para mejor precisión
#define IMAGE_HEIGHT          240

// ============================================================================
// TIPOS DE VEGETACIÓN
// ============================================================================

enum VegetationType {
    VEG_NONE = 0,           // Sin vegetación (suelo, roca, agua)
    VEG_DENSE_FOREST,       // Bosque denso (alto riesgo si seco)
    VEG_OPEN_FOREST,        // Bosque abierto
    VEG_SHRUBLAND,          // Matorral mediterráneo (muy inflamable)
    VEG_GRASSLAND,          // Pastizal/pradera (propaga rápido)
    VEG_CROPLAND,           // Cultivos agrícolas
    VEG_RIPARIAN,           // Vegetación junto a agua (bajo riesgo)
    VEG_STRESSED,           // Vegetación estresada (alto riesgo)
    VEG_DEAD,               // Vegetación muerta/seca (muy alto riesgo)
    VEG_MIXED               // Mezcla de tipos
};

// Nombres para output serial
const char* VEG_TYPE_NAMES[] = {
    "SIN_VEGETACION",
    "BOSQUE_DENSO",
    "BOSQUE_ABIERTO",
    "MATORRAL",
    "PASTIZAL",
    "CULTIVO",
    "RIPARIA",
    "ESTRESADA",
    "MUERTA_SECA",
    "MIXTA"
};

// ============================================================================
// CARACTERÍSTICAS DE COMBUSTIBILIDAD POR TIPO
// ============================================================================

// Índice de inflamabilidad base (0-100) por tipo de vegetación
const uint8_t BASE_FLAMMABILITY[] = {
    5,    // VEG_NONE - Muy bajo
    70,   // VEG_DENSE_FOREST - Alto (acumulación de combustible)
    55,   // VEG_OPEN_FOREST - Moderado-Alto
    85,   // VEG_SHRUBLAND - Muy alto (aceites esenciales)
    75,   // VEG_GRASSLAND - Alto (seco = propaga muy rápido)
    45,   // VEG_CROPLAND - Moderado (depende del cultivo)
    15,   // VEG_RIPARIAN - Bajo (humedad alta)
    80,   // VEG_STRESSED - Alto
    95,   // VEG_DEAD - Muy alto
    60    // VEG_MIXED - Promedio
};

// Velocidad de propagación relativa (1-10) por tipo
const uint8_t SPREAD_RATE[] = {
    1,    // VEG_NONE
    5,    // VEG_DENSE_FOREST - Lento pero intenso
    6,    // VEG_OPEN_FOREST
    8,    // VEG_SHRUBLAND - Rápido
    10,   // VEG_GRASSLAND - Muy rápido
    7,    // VEG_CROPLAND
    2,    // VEG_RIPARIAN - Muy lento
    8,    // VEG_STRESSED
    9,    // VEG_DEAD
    6     // VEG_MIXED
};

// Intensidad potencial del fuego (1-10) por tipo
const uint8_t FIRE_INTENSITY[] = {
    1,    // VEG_NONE
    10,   // VEG_DENSE_FOREST - Muy intenso
    7,    // VEG_OPEN_FOREST
    8,    // VEG_SHRUBLAND
    4,    // VEG_GRASSLAND - Bajo pero rápido
    5,    // VEG_CROPLAND
    2,    // VEG_RIPARIAN
    7,    // VEG_STRESSED
    6,    // VEG_DEAD
    6     // VEG_MIXED
};

// ============================================================================
// UMBRALES DE CLASIFICACIÓN DE VEGETACIÓN
// ============================================================================

// Índices de vegetación
#define THRESHOLD_EXG_NO_VEG      0.05   // < esto = sin vegetación
#define THRESHOLD_EXG_SPARSE      0.12   // < esto = vegetación escasa
#define THRESHOLD_EXG_MODERATE    0.22   // < esto = moderada
#define THRESHOLD_EXG_DENSE       0.35   // > esto = muy densa

// Detección de estrés (VARI bajo con ExG presente)
#define THRESHOLD_STRESS_VARI     0.10   // VARI < esto con vegetación = estrés

// Detección de sequedad
#define THRESHOLD_DRY_RATIO       0.55   // R/(R+G) > esto = seco
#define THRESHOLD_YELLOW_INDEX    0.40   // Amarillamiento

// Detección de bosque vs matorral vs pastizal
#define THRESHOLD_DARK_GREEN      80     // G < esto = bosque oscuro
#define THRESHOLD_BRIGHT_GREEN    150    // G > esto = pastizal brillante
#define THRESHOLD_UNIFORMITY      20     // Variación de color baja = uniforme

// ============================================================================
// ESTRUCTURA DE ANÁLISIS
// ============================================================================

struct VegetationAnalysis {
    // Tipo dominante de vegetación
    VegetationType dominantType;
    float confidence;               // 0-100% confianza en clasificación
    
    // Distribución de tipos (% de cada uno)
    float pctNoVegetation;
    float pctDenseForest;
    float pctOpenForest;
    float pctShrubland;
    float pctGrassland;
    float pctCropland;
    float pctRiparian;
    float pctStressed;
    float pctDead;
    
    // Índices de vegetación promedio
    float avgExG;                   // Excess Green Index
    float avgVARI;                  // Visible Atmospherically Resistant Index
    float avgGLI;                   // Green Leaf Index
    float avgNDI;                   // Normalized Difference Index (G-R)/(G+R)
    
    // Indicadores de estado
    float stressIndex;              // 0-100 (100 = muy estresada)
    float drynessIndex;             // 0-100 (100 = muy seca)
    float biomassIndex;             // 0-100 (100 = alta biomasa)
    float continuityIndex;          // 0-100 (100 = muy continua)
    
    // Características de color
    float avgBrightness;
    float avgGreenness;
    float colorVariation;
    
    // PROBABILIDAD DE INCENDIO
    float fireProbability;          // 0-100%
    float spreadPotential;          // 0-100 potencial de propagación
    float intensityPotential;       // 0-100 intensidad potencial
    
    // Componentes del cálculo de probabilidad
    float factorVegType;            // Contribución del tipo de vegetación
    float factorDryness;            // Contribución de la sequedad
    float factorBiomass;            // Contribución de la biomasa
    float factorContinuity;         // Contribución de la continuidad
    float factorStress;             // Contribución del estrés
    
    // Metadatos
    unsigned long timestamp;
    int sampledPixels;
    bool analysisValid;
};

// ============================================================================
// VARIABLES GLOBALES
// ============================================================================

VegetationAnalysis analysis;
VegetationAnalysis prevAnalysis;
bool hasPrevAnalysis = false;

// Buffers de muestreo
uint8_t sampleR[SAMPLE_SIZE];
uint8_t sampleG[SAMPLE_SIZE];
uint8_t sampleB[SAMPLE_SIZE];
int sampleCount = 0;

// Estado del sensor
bool sensorOK = false;
unsigned long lastAnalysis = 0;
unsigned long frameCount = 0;

// ============================================================================
// FUNCIONES DE CÁLCULO DE ÍNDICES
// ============================================================================

/**
 * Calcula el Excess Green Index (ExG)
 * Valores altos = vegetación verde activa
 */
float calculateExG(uint8_t r, uint8_t g, uint8_t b) {
    float sum = (float)(r + g + b);
    if (sum < 10) return 0;
    
    float rn = r / sum;
    float gn = g / sum;
    float bn = b / sum;
    
    return (2.0 * gn - rn - bn);  // Rango: -1 a +1
}

/**
 * Calcula el VARI (Visible Atmospherically Resistant Index)
 * Menos sensible a condiciones atmosféricas
 */
float calculateVARI(uint8_t r, uint8_t g, uint8_t b) {
    float denom = (float)(g + r - b);
    if (abs(denom) < 1) return 0;
    
    return ((float)(g - r)) / denom;  // Rango: -1 a +1
}

/**
 * Calcula el Green Leaf Index (GLI)
 * Mejor para detectar hojas verdes específicamente
 */
float calculateGLI(uint8_t r, uint8_t g, uint8_t b) {
    float sum = (float)(2 * g + r + b);
    if (sum < 10) return 0;
    
    return (2.0 * g - r - b) / sum;  // Rango: -1 a +1
}

/**
 * Calcula el Normalized Difference Index (NDI) verde-rojo
 */
float calculateNDI(uint8_t r, uint8_t g, uint8_t b) {
    float sum = (float)(g + r);
    if (sum < 10) return 0;
    
    return ((float)(g - r)) / sum;  // Rango: -1 a +1
}

/**
 * Calcula el índice de sequedad basado en color
 * Valores altos = vegetación más seca/amarilla
 */
float calculateDrynessFromColor(uint8_t r, uint8_t g, uint8_t b) {
    // Vegetación seca tiende a ser más amarilla/marrón
    // R aumenta, G disminuye respecto a vegetación sana
    
    float brightness = (r + g + b) / 3.0;
    if (brightness < 20) return 0;  // Muy oscuro, no calculable
    
    // Ratio rojo/verde (seco = más rojo)
    float rgRatio = (g > 0) ? (float)r / g : 2.0;
    
    // Índice de amarillamiento
    float yellowIndex = 0;
    if (r > b && g > b) {
        yellowIndex = (float)(r + g - 2 * b) / (r + g + b);
    }
    
    // Combinar factores
    float dryness = 0;
    
    // Ratio R/G alto = seco
    if (rgRatio > 0.7) {
        dryness += (rgRatio - 0.7) * 150;  // Escalar a 0-50
    }
    
    // Amarillamiento
    dryness += yellowIndex * 50;
    
    return constrain(dryness, 0, 100);
}

/**
 * Calcula el índice de estrés de la vegetación
 */
float calculateStressIndex(float exg, float vari, float dryness) {
    float stress = 0;
    
    // ExG bajo pero positivo = estrés
    if (exg > 0.02 && exg < 0.15) {
        stress += (0.15 - exg) / 0.13 * 40;  // 0-40 puntos
    }
    
    // VARI bajo = estrés
    if (vari < 0.1) {
        stress += (0.1 - vari) / 0.2 * 30;  // 0-30 puntos
    }
    
    // Sequedad contribuye al estrés
    stress += dryness * 0.3;  // 0-30 puntos
    
    return constrain(stress, 0, 100);
}

// ============================================================================
// CLASIFICACIÓN DE TIPO DE VEGETACIÓN
// ============================================================================

/**
 * Clasifica el tipo de vegetación de un píxel individual
 */
VegetationType classifyPixelVegetation(uint8_t r, uint8_t g, uint8_t b) {
    float exg = calculateExG(r, g, b);
    float vari = calculateVARI(r, g, b);
    int brightness = (r + g + b) / 3;
    
    // ==========================================
    // SIN VEGETACIÓN
    // ==========================================
    if (exg < THRESHOLD_EXG_NO_VEG) {
        // Verificar si es agua (azul dominante)
        if (b > r + 30 && b > g && brightness < 120) {
            return VEG_NONE;  // Agua
        }
        // Suelo o roca
        return VEG_NONE;
    }
    
    // ==========================================
    // VEGETACIÓN PRESENTE
    // ==========================================
    
    // Calcular indicadores adicionales
    float dryness = calculateDrynessFromColor(r, g, b);
    float rgRatio = (g > 0) ? (float)r / g : 1.0;
    
    // ==========================================
    // VEGETACIÓN MUERTA/SECA
    // ==========================================
    if (dryness > 70 || (rgRatio > 0.9 && exg < 0.1)) {
        return VEG_DEAD;
    }
    
    // ==========================================
    // VEGETACIÓN ESTRESADA
    // ==========================================
    if (vari < THRESHOLD_STRESS_VARI && exg > 0.05 && exg < 0.2) {
        return VEG_STRESSED;
    }
    
    // ==========================================
    // VEGETACIÓN RIPARIA (junto a agua)
    // ==========================================
    // Detectada por verde muy saturado + azul moderado
    if (exg > 0.25 && b > 80 && g > 100 && brightness > 80) {
        return VEG_RIPARIAN;
    }
    
    // ==========================================
    // CLASIFICAR POR DENSIDAD Y COLOR
    // ==========================================
    
    // BOSQUE DENSO: Verde oscuro, alta densidad
    if (exg > THRESHOLD_EXG_DENSE && g < THRESHOLD_DARK_GREEN && brightness < 100) {
        return VEG_DENSE_FOREST;
    }
    
    // BOSQUE ABIERTO: Verde moderado-oscuro
    if (exg > THRESHOLD_EXG_MODERATE && g < 120 && brightness < 130) {
        return VEG_OPEN_FOREST;
    }
    
    // PASTIZAL: Verde brillante, uniforme
    if (exg > THRESHOLD_EXG_SPARSE && g > THRESHOLD_BRIGHT_GREEN && brightness > 130) {
        return VEG_GRASSLAND;
    }
    
    // CULTIVOS: Verde medio, patrones regulares
    // (difícil de detectar sin análisis de textura, usar heurística)
    if (exg > 0.15 && exg < 0.3 && brightness > 100 && brightness < 170) {
        // Podría ser cultivo o matorral
        if (dryness < 30) {
            return VEG_CROPLAND;
        }
    }
    
    // MATORRAL: ExG moderado, variedad de tonos
    if (exg > THRESHOLD_EXG_SPARSE && exg < THRESHOLD_EXG_DENSE) {
        if (dryness > 30 && dryness < 70) {
            return VEG_SHRUBLAND;
        }
    }
    
    // Por defecto: mezcla
    return VEG_MIXED;
}

/**
 * Determina el tipo dominante de vegetación basado en conteos
 */
VegetationType getDominantType(int* counts, int total) {
    int maxCount = 0;
    VegetationType dominant = VEG_NONE;
    
    for (int i = 0; i < 10; i++) {
        if (counts[i] > maxCount) {
            maxCount = counts[i];
            dominant = (VegetationType)i;
        }
    }
    
    return dominant;
}

// ============================================================================
// CÁLCULO DE PROBABILIDAD DE INCENDIO
// ============================================================================

/**
 * Calcula la probabilidad de incendio basada en todos los factores
 */
void calculateFireProbability() {
    // ==========================================
    // FACTOR 1: TIPO DE VEGETACIÓN (30%)
    // ==========================================
    float vegTypeScore = BASE_FLAMMABILITY[analysis.dominantType];
    
    // Ajustar por distribución de tipos
    float weightedFlammability = 0;
    float weights[] = {
        analysis.pctNoVegetation,
        analysis.pctDenseForest,
        analysis.pctOpenForest,
        analysis.pctShrubland,
        analysis.pctGrassland,
        analysis.pctCropland,
        analysis.pctRiparian,
        analysis.pctStressed,
        analysis.pctDead
    };
    
    for (int i = 0; i < 9; i++) {
        weightedFlammability += (weights[i] / 100.0) * BASE_FLAMMABILITY[i];
    }
    
    analysis.factorVegType = weightedFlammability;
    
    // ==========================================
    // FACTOR 2: SEQUEDAD (25%)
    // ==========================================
    analysis.factorDryness = analysis.drynessIndex;
    
    // ==========================================
    // FACTOR 3: BIOMASA/DENSIDAD (20%)
    // ==========================================
    // Alta biomasa = más combustible
    analysis.factorBiomass = analysis.biomassIndex;
    
    // ==========================================
    // FACTOR 4: CONTINUIDAD (15%)
    // ==========================================
    // Alta continuidad = propagación fácil
    analysis.factorContinuity = analysis.continuityIndex;
    
    // ==========================================
    // FACTOR 5: ESTRÉS VEGETAL (10%)
    // ==========================================
    analysis.factorStress = analysis.stressIndex;
    
    // ==========================================
    // CÁLCULO FINAL DE PROBABILIDAD
    // ==========================================
    float probability = 
        (analysis.factorVegType * 0.30) +
        (analysis.factorDryness * 0.25) +
        (analysis.factorBiomass * 0.20) +
        (analysis.factorContinuity * 0.15) +
        (analysis.factorStress * 0.10);
    
    analysis.fireProbability = constrain(probability, 0, 100);
    
    // ==========================================
    // POTENCIAL DE PROPAGACIÓN
    // ==========================================
    float spreadPot = 0;
    for (int i = 0; i < 9; i++) {
        spreadPot += (weights[i] / 100.0) * SPREAD_RATE[i] * 10;
    }
    // Ajustar por continuidad y sequedad
    spreadPot = spreadPot * (0.5 + 0.3 * (analysis.continuityIndex / 100.0) + 0.2 * (analysis.drynessIndex / 100.0));
    analysis.spreadPotential = constrain(spreadPot, 0, 100);
    
    // ==========================================
    // POTENCIAL DE INTENSIDAD
    // ==========================================
    float intensityPot = 0;
    for (int i = 0; i < 9; i++) {
        intensityPot += (weights[i] / 100.0) * FIRE_INTENSITY[i] * 10;
    }
    // Ajustar por biomasa
    intensityPot = intensityPot * (0.6 + 0.4 * (analysis.biomassIndex / 100.0));
    analysis.intensityPotential = constrain(intensityPot, 0, 100);
}

// ============================================================================
// ANÁLISIS COMPLETO DE FRAME
// ============================================================================

/**
 * Lee un byte del bus de datos de la cámara
 */
uint8_t readDataByte() {
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
 * Espera con timeout para evitar bucles infinitos
 */
bool waitForPCLK(bool state, unsigned long timeoutUs) {
    unsigned long start = micros();
    while (digitalRead(PIN_PCLK) != state) {
        if (micros() - start > timeoutUs) return false;
    }
    return true;
}

/**
 * Captura píxeles reales de la cámara OV7670
 */
void captureRealPixels() {
    sampleCount = 0;
    
    // Timeout de 100ms para toda la captura
    unsigned long timeout = millis() + 100;
    
    // Esperar flanco de VSYNC (inicio de frame)
    while (digitalRead(PIN_VSYNC) == HIGH && millis() < timeout);
    while (digitalRead(PIN_VSYNC) == LOW && millis() < timeout);
    while (digitalRead(PIN_VSYNC) == HIGH && millis() < timeout);
    
    if (millis() >= timeout) {
        Serial.println("warning=VSYNC_TIMEOUT");
        return;
    }
    
    int pixelNum = 0;
    int targetInterval = 50;  // Capturar cada 50 píxeles
    unsigned long captureTimeout = millis() + 150;
    int failedReads = 0;
    
    while (sampleCount < SAMPLE_SIZE && millis() < captureTimeout) {
        if (digitalRead(PIN_HREF) == HIGH) {
            // Esperar flanco ascendente de PCLK con timeout
            if (!waitForPCLK(HIGH, 10)) {
                failedReads++;
                if (failedReads > 100) break;
                continue;
            }
            uint8_t b1 = readDataByte();
            
            if (!waitForPCLK(LOW, 10)) continue;
            if (!waitForPCLK(HIGH, 10)) continue;
            uint8_t b2 = readDataByte();
            if (!waitForPCLK(LOW, 10)) continue;
            
            pixelNum++;
            
            if (pixelNum % targetInterval == 0) {
                // RGB565 -> RGB888
                uint16_t rgb565 = (b1 << 8) | b2;
                sampleR[sampleCount] = ((rgb565 >> 11) & 0x1F) << 3;
                sampleG[sampleCount] = ((rgb565 >> 5) & 0x3F) << 2;
                sampleB[sampleCount] = (rgb565 & 0x1F) << 3;
                sampleCount++;
            }
        }
        
        if (digitalRead(PIN_VSYNC) == HIGH) break;
    }
    
    // Debug si hay problemas
    if (sampleCount < 20) {
        Serial.print("debug=pixels:");
        Serial.print(pixelNum);
        Serial.print(",samples:");
        Serial.print(sampleCount);
        Serial.print(",fails:");
        Serial.println(failedReads);
    }
}

/**
 * Simula captura de píxeles (para pruebas sin hardware)
 */
void simulatePixelCapture() {
    sampleCount = SAMPLE_SIZE;
    
    for (int i = 0; i < SAMPLE_SIZE; i++) {
        int zone = random(100);
        
        if (zone < 40) {
            // Bosque/vegetación densa
            sampleR[i] = 40 + random(30);
            sampleG[i] = 80 + random(50);
            sampleB[i] = 30 + random(25);
        } else if (zone < 60) {
            // Matorral
            sampleR[i] = 80 + random(40);
            sampleG[i] = 90 + random(40);
            sampleB[i] = 50 + random(30);
        } else if (zone < 75) {
            // Pastizal
            sampleR[i] = 120 + random(40);
            sampleG[i] = 160 + random(40);
            sampleB[i] = 80 + random(30);
        } else if (zone < 85) {
            // Vegetación seca/estresada
            sampleR[i] = 140 + random(40);
            sampleG[i] = 120 + random(30);
            sampleB[i] = 70 + random(30);
        } else if (zone < 92) {
            // Cultivos
            sampleR[i] = 100 + random(30);
            sampleG[i] = 130 + random(40);
            sampleB[i] = 70 + random(25);
        } else {
            // Suelo desnudo
            sampleR[i] = 150 + random(40);
            sampleG[i] = 130 + random(30);
            sampleB[i] = 100 + random(30);
        }
    }
}

/**
 * Analiza todos los píxeles y genera el análisis completo
 */
void analyzeVegetation() {
    // Contadores por tipo
    int typeCounts[10] = {0};
    
    // Acumuladores de índices
    float sumExG = 0, sumVARI = 0, sumGLI = 0, sumNDI = 0;
    float sumBrightness = 0, sumGreenness = 0;
    float sumDryness = 0;
    float minBrightness = 255, maxBrightness = 0;
    float sumColorVar = 0;
    
    int vegPixelCount = 0;  // Píxeles con vegetación
    
    // Analizar cada píxel
    for (int i = 0; i < sampleCount; i++) {
        uint8_t r = sampleR[i];
        uint8_t g = sampleG[i];
        uint8_t b = sampleB[i];
        
        // Calcular índices
        float exg = calculateExG(r, g, b);
        float vari = calculateVARI(r, g, b);
        float gli = calculateGLI(r, g, b);
        float ndi = calculateNDI(r, g, b);
        float dryness = calculateDrynessFromColor(r, g, b);
        
        sumExG += exg;
        sumVARI += vari;
        sumGLI += gli;
        sumNDI += ndi;
        sumDryness += dryness;
        
        float brightness = (r + g + b) / 3.0;
        sumBrightness += brightness;
        sumGreenness += g;
        
        if (brightness < minBrightness) minBrightness = brightness;
        if (brightness > maxBrightness) maxBrightness = brightness;
        
        // Clasificar tipo de vegetación
        VegetationType type = classifyPixelVegetation(r, g, b);
        typeCounts[type]++;
        
        if (type != VEG_NONE) {
            vegPixelCount++;
        }
    }
    
    // Calcular promedios
    float n = (float)sampleCount;
    analysis.avgExG = sumExG / n;
    analysis.avgVARI = sumVARI / n;
    analysis.avgGLI = sumGLI / n;
    analysis.avgNDI = sumNDI / n;
    analysis.avgBrightness = sumBrightness / n;
    analysis.avgGreenness = sumGreenness / n;
    analysis.drynessIndex = sumDryness / n;
    
    // Variación de color (indicador de uniformidad)
    analysis.colorVariation = maxBrightness - minBrightness;
    
    // Calcular porcentajes de cada tipo
    analysis.pctNoVegetation = (typeCounts[VEG_NONE] / n) * 100.0;
    analysis.pctDenseForest = (typeCounts[VEG_DENSE_FOREST] / n) * 100.0;
    analysis.pctOpenForest = (typeCounts[VEG_OPEN_FOREST] / n) * 100.0;
    analysis.pctShrubland = (typeCounts[VEG_SHRUBLAND] / n) * 100.0;
    analysis.pctGrassland = (typeCounts[VEG_GRASSLAND] / n) * 100.0;
    analysis.pctCropland = (typeCounts[VEG_CROPLAND] / n) * 100.0;
    analysis.pctRiparian = (typeCounts[VEG_RIPARIAN] / n) * 100.0;
    analysis.pctStressed = (typeCounts[VEG_STRESSED] / n) * 100.0;
    analysis.pctDead = (typeCounts[VEG_DEAD] / n) * 100.0;
    
    // Determinar tipo dominante
    analysis.dominantType = getDominantType(typeCounts, sampleCount);
    
    // Calcular confianza (basada en cuánto domina el tipo principal)
    int maxCount = typeCounts[analysis.dominantType];
    analysis.confidence = (maxCount / n) * 100.0;
    
    // Calcular índice de biomasa (basado en ExG y densidad)
    float vegCoverage = (vegPixelCount / n);
    analysis.biomassIndex = constrain((analysis.avgExG + 1.0) / 2.0 * vegCoverage * 150, 0, 100);
    
    // Calcular índice de continuidad (inverso de variación)
    analysis.continuityIndex = constrain(100 - analysis.colorVariation / 2.0, 0, 100);
    
    // Calcular índice de estrés
    analysis.stressIndex = calculateStressIndex(analysis.avgExG, analysis.avgVARI, analysis.drynessIndex);
    
    // Calcular probabilidad de incendio
    calculateFireProbability();
    
    // Metadatos
    analysis.timestamp = millis();
    analysis.sampledPixels = sampleCount;
    analysis.analysisValid = (sampleCount >= 50);
}

// ============================================================================
// OUTPUT SERIAL
// ============================================================================

/**
 * Envía el análisis de vegetación por Serial
 */
void sendVegetationAnalysis() {
    // Línea 1: Tipo de vegetación dominante
    Serial.print("vegtype=");
    Serial.print(VEG_TYPE_NAMES[analysis.dominantType]);
    Serial.print(",conf:");
    Serial.print(analysis.confidence, 1);
    Serial.println("%");
    
    // Línea 2: Distribución de tipos
    Serial.print("vegtypes=");
    Serial.print("bosque_d:"); Serial.print(analysis.pctDenseForest, 1);
    Serial.print(",bosque_a:"); Serial.print(analysis.pctOpenForest, 1);
    Serial.print(",matorral:"); Serial.print(analysis.pctShrubland, 1);
    Serial.print(",pastizal:"); Serial.print(analysis.pctGrassland, 1);
    Serial.print(",cultivo:"); Serial.print(analysis.pctCropland, 1);
    Serial.print(",riparia:"); Serial.print(analysis.pctRiparian, 1);
    Serial.print(",estres:"); Serial.print(analysis.pctStressed, 1);
    Serial.print(",seca:"); Serial.print(analysis.pctDead, 1);
    Serial.print(",sinveg:"); Serial.println(analysis.pctNoVegetation, 1);
    
    // Línea 3: Índices de vegetación
    Serial.print("vegindex=");
    Serial.print("exg:"); Serial.print(analysis.avgExG, 3);
    Serial.print(",vari:"); Serial.print(analysis.avgVARI, 3);
    Serial.print(",gli:"); Serial.print(analysis.avgGLI, 3);
    Serial.print(",ndi:"); Serial.println(analysis.avgNDI, 3);
    
    // Línea 4: Estado de la vegetación
    Serial.print("vegstate=");
    Serial.print("sequia:"); Serial.print(analysis.drynessIndex, 1);
    Serial.print(",estres:"); Serial.print(analysis.stressIndex, 1);
    Serial.print(",biomasa:"); Serial.print(analysis.biomassIndex, 1);
    Serial.print(",continuidad:"); Serial.println(analysis.continuityIndex, 1);
    
    // Línea 5: PROBABILIDAD DE INCENDIO
    Serial.print("FIRE_PROB=");
    Serial.print(analysis.fireProbability, 1);
    Serial.print("%,propagacion:");
    Serial.print(analysis.spreadPotential, 1);
    Serial.print(",intensidad:");
    Serial.println(analysis.intensityPotential, 1);
    
    // Línea 6: Factores de riesgo
    Serial.print("fire_factors=");
    Serial.print("f_vegtype:"); Serial.print(analysis.factorVegType, 1);
    Serial.print(",f_sequia:"); Serial.print(analysis.factorDryness, 1);
    Serial.print(",f_biomasa:"); Serial.print(analysis.factorBiomass, 1);
    Serial.print(",f_conti:"); Serial.print(analysis.factorContinuity, 1);
    Serial.print(",f_estres:"); Serial.println(analysis.factorStress, 1);
    
    // Línea 7: Alertas
    if (analysis.fireProbability >= 70) {
        Serial.println("ALERTA=RIESGO_MUY_ALTO_INCENDIO");
    } else if (analysis.fireProbability >= 50) {
        Serial.println("ALERTA=RIESGO_ALTO_INCENDIO");
    } else if (analysis.drynessIndex > 60) {
        Serial.println("ALERTA=VEGETACION_MUY_SECA");
    } else if (analysis.stressIndex > 60) {
        Serial.println("ALERTA=VEGETACION_ESTRESADA");
    }
    
    Serial.println("---");
}

/**
 * Muestra estado en LED según probabilidad de incendio
 */
void updateStatusLED() {
    // Parpadeo basado en riesgo
    unsigned long blinkRate;
    
    if (analysis.fireProbability >= 70) {
        blinkRate = 100;  // Muy rápido
    } else if (analysis.fireProbability >= 50) {
        blinkRate = 250;  // Rápido
    } else if (analysis.fireProbability >= 30) {
        blinkRate = 500;  // Medio
    } else {
        blinkRate = 2000; // Lento (normal)
    }
    
    digitalWrite(STATUS_LED, (millis() / blinkRate) % 2);
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
    Serial.println("================================================");
    Serial.println("VEGETATION TYPE & FIRE PROBABILITY ANALYZER");
    Serial.println("CanSat Aerial Analysis System v1.0");
    Serial.println("================================================");
    Serial.println();
    
    // Configurar pines de datos como entrada
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
    
    // Generar clock para OV7670
    pinMode(PIN_XCLK, OUTPUT);
    analogWrite(PIN_XCLK, 128);
    delay(500);
    
    // Intentar detectar cámara
    Wire.beginTransmission(OV7670_I2C_ADDR);
    if (Wire.endTransmission() == 0) {
        Serial.println("info=OV7670_DETECTADO");
        sensorOK = true;
    } else {
        Serial.println("warning=OV7670_NO_DETECTADO");
        Serial.println("info=USANDO_MODO_SIMULACION");
        sensorOK = false;
    }
    
    // Inicializar análisis
    memset(&analysis, 0, sizeof(VegetationAnalysis));
    
    Serial.println();
    Serial.println("info=SISTEMA_LISTO");
    Serial.println("================================================");
    
    digitalWrite(STATUS_LED, LOW);
    delay(1000);
}

// ============================================================================
// LOOP
// ============================================================================

void loop() {
    unsigned long now = millis();
    
    if (now - lastAnalysis >= ANALYSIS_INTERVAL) {
        lastAnalysis = now;
        frameCount++;
        
        // Capturar píxeles - usar cámara real si está disponible
        if (sensorOK) {
            captureRealPixels();
            // Si la captura real falla, usar simulación
            if (sampleCount < 20) {
                Serial.println("info=FALLBACK_SIMULACION");
                simulatePixelCapture();
            }
        } else {
            simulatePixelCapture();
        }
        
        // Guardar análisis anterior
        if (analysis.analysisValid) {
            memcpy(&prevAnalysis, &analysis, sizeof(VegetationAnalysis));
            hasPrevAnalysis = true;
        }
        
        // Realizar análisis
        analyzeVegetation();
        
        // Enviar resultados
        sendVegetationAnalysis();
    }
    
    // Actualizar LED
    updateStatusLED();
}
