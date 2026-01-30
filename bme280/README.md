# BMP280 Sensor Project (CanSat)

> **NOTA:** Este sensor es un **BMP280**, no un BME280.  
> El BMP280 mide temperatura, presión y altitud, pero **NO tiene sensor de humedad**.

## Estructura

- **arduino/**: Código Arduino (`bme280_arduino.ino`)
- **python/**: Scripts para dashboard y generación de reportes
- **data/**: Datos CSV y reportes HTML generados

---

## Cómo Ejecutar

### 1. Subir Código al Arduino

Abre PowerShell en la carpeta `interpretacion_datos` y ejecuta:

```powershell
# Ver placas conectadas
.\arduino-cli board list
```

```powershell
# Compilar el código
.\arduino-cli compile --fqbn arduino:renesas_uno:unor4wifi "c:\Users\alumno\Desktop\cansat\interpretacion_datos\bme280\arduino\bme280_arduino"
```

```powershell
# Subir al Arduino (cambia COM9 por tu puerto)
.\arduino-cli upload -p COM9 --fqbn arduino:renesas_uno:unor4wifi "c:\Users\alumno\Desktop\cansat\interpretacion_datos\bme280\arduino\bme280_arduino"
```

---

### 2. Ejecutar Dashboard (Recolección de Datos)

> ⚠️ **ADVERTENCIA:** Ejecutar el dashboard **sobrescribe** `bme280_data.csv`. Haz backup si es necesario.

Abre PowerShell en la carpeta `bme280` y ejecuta:

```powershell
py python/bme280_dashboard.py
```

El dashboard:
- Detecta automáticamente el puerto del Arduino
- Muestra gráficas en tiempo real de temperatura, presión y altitud
- Guarda datos en `data/bme280_data.csv`

**Cierra la ventana del dashboard** cuando termines de recolectar datos.

---

### 3. Generar Reporte HTML

Después de recolectar datos, genera el reporte visual:

```powershell
py python/generate_report.py
```

Abre `data/report.html` en tu navegador para ver los resultados.

---

## Herramientas de Diagnóstico

### Escanear I2C (verificar conexión del sensor)

```powershell
.\arduino-cli compile --fqbn arduino:renesas_uno:unor4wifi "c:\Users\alumno\Desktop\cansat\interpretacion_datos\bme280\arduino\i2c_scanner"
```

```powershell
.\arduino-cli upload -p COM9 --fqbn arduino:renesas_uno:unor4wifi "c:\Users\alumno\Desktop\cansat\interpretacion_datos\bme280\arduino\i2c_scanner"
```

El sensor BMP280 debe aparecer en la dirección **0x76** o **0x77**.
