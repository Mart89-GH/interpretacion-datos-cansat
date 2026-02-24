# CanSat: Sistema de Detección de Incendios y Análisis de Vegetación con OV7670

Este directorio contiene todo el código necesario para la captura de imágenes aéreas, detección de incendios forestales y análisis de vegetación usando el módulo de cámara **OV7670** para la competición CanSat.

> **🔥 SISTEMA DE VISIÓN AÉREA**
> Este sistema está optimizado para captura desde altitud (100-1000m), incluyendo:
> - Filtrado automático de cielo y nubes
> - Detección de humo (más visible que el fuego desde el aire)
> - Índices de vegetación para agricultura de precisión
> - Clasificación de 9 tipos de terreno

---

## 📂 Estructura del Proyecto

```
ov7670/
├── README.md                        # Este archivo
├── arduino/
│   ├── ov7670_fire_detection/       # 🔥 Sketch principal (FDI general)
│   │   └── ov7670_fire_detection.ino
│   ├── vegetation_fire_analyzer/    # 🌲 Especializado en tipos de vegetación
│   │   └── vegetation_fire_analyzer.ino
│   └── ov7670_test/                 # 🔧 Test de conexión
│       └── ov7670_test.ino
├── python/
│   ├── ov7670_dashboard.py          # 📊 Dashboard general
│   ├── vegetation_fire_dashboard.py # 🌲 Dashboard de vegetación
│   ├── generate_report.py           # 📄 Generador de reportes HTML
│   └── exports/                     # 📁 Gráficas exportadas
└── data/
    ├── ov7670_data.csv              # 📈 Datos generales
    ├── vegetation_fire_data.csv     # 🌲 Datos de vegetación
    └── report.html                  # 📋 Informe generado
```

---

## 🌲 NUEVO: Analizador de Tipos de Vegetación

El sketch `vegetation_fire_analyzer.ino` es un **código especializado** que:

### Detecta 9 Tipos de Vegetación:

| Tipo | Descripción | Riesgo de Incendio |
|------|-------------|-------------------|
| 🌲 **Bosque Denso** | Coníferas, caducifolios densos | Alto (acumulación combustible) |
| 🌳 **Bosque Abierto** | Arbolado disperso | Moderado-Alto |
| 🌿 **Matorral** | Mediterráneo, chaparral | **Muy Alto** (aceites esenciales) |
| 🌾 **Pastizal** | Praderas, herbazales | Alto (propaga rápido) |
| 🌱 **Cultivos** | Campos agrícolas | Moderado |
| 💧 **Riparia** | Junto a ríos/agua | Bajo (alta humedad) |
| ⚠️ **Estresada** | Falta de agua | Alto |
| 🔥 **Muerta/Seca** | Vegetación seca | **Muy Alto** |
| 🪨 **Sin Vegetación** | Suelo, roca, agua | Bajo |

### Cálculo de Probabilidad de Incendio (5 Factores):

| Factor | Peso | Descripción |
|--------|------|-------------|
| **Tipo de Vegetación** | 30% | Combustibilidad inherente |
| **Sequedad** | 25% | Índice de humedad |
| **Biomasa** | 20% | Cantidad de combustible |
| **Continuidad** | 15% | Facilidad de propagación |
| **Estrés** | 10% | Estado de salud vegetal |
| D0 | A0 | Datos bit 0 |
| D1 | A1 | Datos bit 1 |
| D2 | A2 | Datos bit 2 |
| D3 | A3 | Datos bit 3 |
| D4 | A4 | Datos bit 4 |
| D5 | A5 | Datos bit 5 |
| D6 | D6 | Datos bit 6 |
| D7 | D7 | Datos bit 7 |
| RESET | 3.3V | Tied high |
| PWDN | GND | Tied low |

> **⚠️ IMPORTANTE:** El OV7670 funciona a 3.3V. Conectar a 5V puede dañarlo permanentemente.

---

## 🚀 Guía de Uso

### 1. Verificar Conexión del OV7670

Primero, sube el sketch de prueba para verificar que el sensor responde:

```powershell
# Desde la carpeta 'interpretacion_datos'
.\arduino-cli compile --fqbn arduino:renesas_uno:unor4wifi "ov7670\arduino\ov7670_test"
.\arduino-cli upload -p COMx --fqbn arduino:renesas_uno:unor4wifi "ov7670\arduino\ov7670_test"
```

Abre el monitor serial (115200 baud). Deberías ver:
```
OV7670 CONNECTION TEST
Dispositivo encontrado en 0x21 <- Posible OV7670!
Product ID (PID): 0x76 ✓ (OV7670 confirmado)
```

### 2. Subir Código Principal

```powershell
.\arduino-cli compile --fqbn arduino:renesas_uno:unor4wifi "ov7670\arduino\ov7670_fire_detection"
.\arduino-cli upload -p COMx --fqbn arduino:renesas_uno:unor4wifi "ov7670\arduino\ov7670_fire_detection"
```

### 3. Ejecutar Dashboard (Estación Terrena)

```powershell
# Desde la carpeta 'ov7670'
py python/ov7670_dashboard.py
```

El dashboard muestra:
- 🔥 **Fire Detection Index (FDI)**: Índice combinado de riesgo de incendio (0-100)
- ⚠️ **Nivel de Riesgo**: Indicador visual (0-4)
- 🗺️ **Clasificación de Terreno**: Barras con % de cada tipo
- 🌱 **Índices de Vegetación**: ExG y VARI en tiempo real
- 💨 **Detección de Humo**: Gráfica temporal
- 🌿 **Salud de Vegetación**: Estado de los cultivos

### 4. Generar Informe Post-Misión

```powershell
py python/generate_report.py
```

Se abrirá automáticamente `data/report.html` con:
- Resumen ejecutivo
- Distribución de terreno
- Estadísticas de índices
- Recomendaciones automatizadas

---

## 🔥 Fire Detection Index (FDI)

El FDI combina **8 variables** para calcular la probabilidad de incendio:

| Variable | Peso | Descripción |
|----------|------|-------------|
| Fire Color Ratio | 20% | Píxeles rojo/naranja |
| Smoke Detection | 20% | Humo gris detectado |
| Burn Scar Index | 15% | Zonas quemadas |
| Red Dominance | 15% | Canal rojo dominante |
| Thermal Anomaly | 10% | Calor en zonas verdes |
| Edge Irregularity | 10% | Bordes irregulares |
| Spatial Clustering | 5% | Agrupación de píxeles |
| Temporal Change | 5% | Cambio entre frames |

### Niveles de Riesgo

| FDI | Nivel | Indicación |
|-----|-------|------------|
| 0-15 | 🟢 Sin riesgo | Normal |
| 15-35 | 🟡 Bajo | Vigilancia |
| 35-55 | 🟠 Moderado | Alerta temprana |
| 55-75 | 🔴 Alto | Posible incendio |
| 75-100 | 🔥 Crítico | ¡EMERGENCIA! |

---

## 🌱 Índices de Vegetación

### Excess Green Index (ExG)
```
ExG = 2×G - R - B (normalizado)
```
- **< 0.1**: Suelo desnudo
- **0.1 - 0.25**: Vegetación estresada
- **> 0.25**: Vegetación sana

### VARI (Visible Atmospherically Resistant Index)
```
VARI = (G - R) / (G + R - B)
```
Mejor para condiciones atmosféricas variables (ideal para CanSat).

### Clasificación de Salud

| Índice | Estado | Recomendación |
|--------|--------|---------------|
| < 40% | 🥀 Estresada | Riego urgente |
| 40-60% | 🌿 Moderada | Monitorear |
| > 60% | 🌳 Saludable | Óptimo |

---

## 🗺️ Clasificación de Terreno

El sistema detecta **9 tipos de superficie**:

| Tipo | Color | Descripción |
|------|-------|-------------|
| 🌊 Cielo | Azul claro | Filtrado automáticamente |
| ☁️ Nubes | Blanco | Filtrado automáticamente |
| 🌲 Vegetación | Verde | Bosque/cultivos sanos |
| 🌾 Veg. Seca | Amarillo | Riesgo de incendio |
| 🟤 Suelo | Marrón | Tierra sin vegetación |
| 💧 Agua | Azul oscuro | Ríos/lagos |
| 💨 Humo | Gris | ¡Alerta! |
| 🔥 Fuego | Rojo/naranja | ¡Crítico! |
| ⬛ Quemado | Negro | Daño confirmado |

---

## 🛠️ Solución de Problemas

### ¿No detecta el OV7670?

1. **Verifica el voltaje**: Debe ser 3.3V, NO 5V
2. **Comprueba las conexiones I2C** (SDA/SCL)
3. **El XCLK debe estar activo** (pin 9 generando PWM)
4. **RESET debe estar a 3.3V**, PWDN a GND
5. Ejecuta el sketch `ov7670_test` para diagnóstico

### ¿Datos extraños en el dashboard?

- El sistema tiene **modo simulación** automático si no detecta la cámara
- Verifica que el Arduino esté transmitiendo datos correctamente
- Asegúrate de cerrar otros monitores serial

### ¿El FDI es siempre alto?

- Calibrar umbrales de color según la iluminación
- Ajustar `SKY_REGION_FRACTION` si hay mucho cielo
- Verificar que no haya reflejos solares

### ¿No detecta vegetación?

- Los índices ExG/VARI funcionan mejor con buena iluminación
- Evitar capturar a contraluz
- Ajustar balance de blancos del OV7670

---

## 📊 Formato de Datos Serial

El Arduino envía 4 tipos de líneas:

```
terrain=sky:12.5,cloud:3.2,veg:45.3,dryveg:8.1,soil:15.2,water:2.1,smoke:5.3,fire:0.8,burned:7.5
fire=fdi:67.5,smoke:45.2,color:12.3,burn:7.5,risk:3
veg=exg:0.350,vari:0.280,grvi:0.320,ngbdi:0.150,health:72.5
alert=SMOKE_DETECTED,HIGH_FIRE_RISK
```

---

## 📚 Referencias

- [OV7670 Datasheet](https://www.voti.nl/docs/OV7670.pdf)
- [Excess Green Index (ExG)](https://www.sciencedirect.com/topics/agricultural-and-biological-sciences/excess-green-index)
- [VARI Index](https://www.indexdatabase.de/db/i-single.php?id=356)
- [Fire Detection from Remote Sensing](https://www.mdpi.com/journal/remotesensing/special_issues/fire_detection)

---

## ✨ Créditos

Desarrollado para la competición **CanSat** por el equipo de estudiantes.

*Sistema de detección de incendios y análisis de vegetación v1.0 - Enero 2026*
