# CanSat: Interpretación de Datos BMP280

Este directorio contiene todo el código necesario para la lectura, visualización en tiempo real y análisis posterior de los datos del sensor **BMP280** (Temperatura, Presión y Altitud) para la competición CanSat.

> **NOTA IMPORTANTE:** Aunque algunas carpetas se llamen `bme280`, el código está configurado específicamente para el sensor **BMP280**, el cual **NO tiene sensor de humedad**.

## 📂 Estructura del Proyecto

- **`arduino/`**: Sketches para el microcontrolador.
  - `bme280_arduino/`: **Código principal**. Lee el sensor, detecta anomalías y envía datos por Serial.
  - `i2c_scanner/`: Herramienta de diagnóstico para verificar conexiones.
- **`python/`**: Software de estación terrena.
  - `bme280_dashboard.py`: **Dashboard en tiempo real**. Visualiza datos y guarda el CSV.
  - `generate_report.py`: **Generador de Reportes**. Procesa el CSV, aplica **filtros de cribado** y genera un informe HTML.
- **`data/`**: Almacenamiento de datos.
  - `bme280_data.csv`: Registro bruto de datos de la misión.
  - `report.html`: Informe visual generado con gráficas limpias.

---

## 🚀 Guía de Uso

### 1. Preparación del Arduino (Hardware)

1. Conecta el sensor BMP280 al Arduino R4 WiFi (I2C):
   - **VCC** -> 3.3V
   - **GND** -> GND
   - **SDA** -> SDA
   - **SCL** -> SCL
2. Sube el código principal (`bme280_arduino.ino`) usando Arduino CLI o IDE.

```powershell
# Desde la carpeta 'interpretacion_datos'
.\arduino-cli upload -p COMx --fqbn arduino:renesas_uno:unor4wifi "bme280\arduino\bme280_arduino"
```
*(Reemplaza `COMx` por tu puerto, ej. `COM9`)*

### 2. Estación Terrena (Dashboard en Tiempo Real)

Este script recibe los datos del Arduino, los grafica en vivo y los guarda en `data/bme280_data.csv`.

```powershell
# Desde la carpeta 'bme280'
py python/bme280_dashboard.py
```

- **Funcionalidades:**
  - Detección automática de puerto.
  - Gráficas oscuras estilo "Misión Espacial".
  - **Detección de anomalías**: Alerta si hay saltos bruscos de altitud o temperatura.

### 3. Generación del Informe (Post-Misión)

Una vez finalizada la recolección de datos, ejecuta este script para crear el informe final. 

**✨ Característica Clave:** Este script incluye un **sistema de cribado** que elimina automáticamente los datos corruptos o valores imposibles (picos de ruido) que suelen aparecer al encender/apagar el sensor, garantizando gráficas limpias y profesionales.

```powershell
# Desde la carpeta 'bme280'
py python/generate_report.py
```

- El resultado se guardará en: `data/report.html`
- Abre este archivo en tu navegador para ver:
  - Estadísticas de la misión (Mín/Máx/Promedio).
  - Gráficas de Temperatura, Presión y Altitud.
  - Gráfica de Correlación Temperatura vs Altitud.

---

## 🛠️ Solución de Problemas

**¿El dashboard no conecta?**
1. Asegúrate de cerrar cualquier otra aplicación que use el puerto Serial (monitor serial de Arduino IDE, etc.).
2. Verifica que el LED del Arduino parpadee (indica que está leyendo datos).

**¿Datos extraños en las gráficas?**
- El código de Arduino tiene un sistema de auto-reset si detecta muchos fallos consecutivos.
- Usa `generate_report.py` para filtrar el "ruido" del CSV automáticamente.

**¿No detecta el sensor?**
Ejecuta el escáner I2C para confirmar la dirección (debe ser 0x76 o 0x77):
```powershell
.\arduino-cli compile --fqbn arduino:renesas_uno:unor4wifi "bme280\arduino\i2c_scanner"
.\arduino-cli upload -p COMx --fqbn arduino:renesas_uno:unor4wifi "bme280\arduino\i2c_scanner"
```
