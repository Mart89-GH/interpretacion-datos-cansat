# LoRa SX1262 868 MHz - CanSat España 2026

## 📡 Descripción

Códigos de prueba para comunicación LoRa **SX1262** entre el CanSat (emisor) y la estación terrestre (receptor) a **868 MHz**, cumpliendo las **regulaciones europeas ETSI EN 300 220**.

## 🔧 Hardware

- **Chip**: SX1262
- **Módulos compatibles**: Ra-01SH, E22-868T, EBYTE E22
- **Librería**: RadioLib

## 📌 Conexiones SX1262

| Pin LoRa | Pin Arduino | Función | Notas |
|----------|-------------|---------|-------|
| **VCC** | **3.3V** | Alimentación | ⚠️ NUNCA 5V |
| **GND** | **GND** | Tierra | - |
| **SCK** | **Pin 13** | SPI Clock | Level shifter si 5V |
| **MISO** | **Pin 12** | SPI Data Out | Directo OK |
| **MOSI** | **Pin 11** | SPI Data In | Level shifter si 5V |
| **NSS/CS** | **Pin 10** | Chip Select | Level shifter si 5V |
| **RST** | **Pin 9** | Reset | Level shifter si 5V |
| **DIO1** | **Pin 2** | Interrupción | Directo OK |
| **BUSY** | **Pin 3** | Estado ocupado | ⚠️ REQUERIDO |

### 🔌 Esquema Visual

```
        ARDUINO                          MÓDULO SX1262
     ┌──────────────┐                ┌──────────────┐
     │              │                │              │
     │    3.3V  ◄───┼────────────────┼──► VCC      │
     │     GND  ◄───┼────────────────┼──► GND      │
     │              │                │              │
     │  Pin 13  ◄───┼────────────────┼──► SCK      │
     │  Pin 12  ◄───┼────────────────┼──► MISO     │
     │  Pin 11  ◄───┼────────────────┼──► MOSI     │
     │  Pin 10  ◄───┼────────────────┼──► NSS/CS   │
     │   Pin 9  ◄───┼────────────────┼──► RST      │
     │   Pin 2  ◄───┼────────────────┼──► DIO1     │
     │   Pin 3  ◄───┼────────────────┼──► BUSY     │
     │              │                │              │
     └──────────────┘                └──────────────┘
```

> **Nota**: Con Arduino UNO (5V) usa level shifter para SCK, MOSI, NSS, RST.  
> Con Arduino R4 WiFi (3.3V): conexión directa.

## 📋 Regulaciones Europeas

| Parámetro | Valor |
|-----------|-------|
| Frecuencia | 868 MHz |
| Potencia TX | 14 dBm (25mW) |
| Duty Cycle | 1% |
| Spreading Factor | SF7 |
| Bandwidth | 125 kHz |

## 🚀 Instalación

### 1. Instalar Librería RadioLib

En Arduino IDE:
1. **Sketch → Include Library → Manage Libraries**
2. Buscar "**RadioLib**" por Jan Gromeš
3. Instalar versión más reciente

### 2. Cargar Códigos

- **CanSat**: `lora_emisor.ino`
- **Estación terrestre**: `lora_receptor.ino`

## 📁 Estructura

```
lora/
├── README.md
├── arduino/
│   ├── lora_emisor/
│   │   └── lora_emisor.ino
│   └── lora_receptor/
│       └── lora_receptor.ino
├── python/
│   ├── lora_dashboard.py         # Dashboard en tiempo real
│   └── generate_lora_report.py   # Generador de report HTML
└── data/
    ├── lora_data.csv             # Datos recopilados (auto-generado)
    └── report.html               # Report interactivo (auto-generado)
```

## 📊 Dashboard y Report Python

### Requisitos

```bash
pip install pyserial matplotlib numpy
```

### Paso 1: Recopilar datos con el Dashboard

1. Sube `lora_receptor.ino` al Arduino receptor
2. Ejecuta el dashboard:

```bash
cd python
python lora_dashboard.py
```

- Se abrirá una ventana con 6 gráficas en tiempo real:  
  **Temperatura**, **Presión**, **Altitud**, **Humedad**, **RSSI**, **SNR**
- Los datos se guardan automáticamente en `data/lora_data.csv`
- Cierra la ventana para finalizar la sesión

### Paso 2: Generar Report HTML

```bash
python generate_lora_report.py
```

- Genera `data/report.html` con gráficas interactivas Chart.js
- Abrir en cualquier navegador para ver los datos

## 🔍 Troubleshooting

| Problema | Solución |
|----------|----------|
| No inicializa | Verificar pin BUSY conectado |
| Error -2 | Chip no responde - revisar conexiones SPI |
| No recibe | Verificar sync word igual en ambos |
| No encuentra Arduino | Conectar USB y verificar driver |
