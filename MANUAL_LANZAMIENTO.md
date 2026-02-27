# 🚀 Manual de Lanzamiento y Ejecución CanSat

Este documento centraliza todas las instrucciones de ejecución, posibles fallos y puntos de revisión crítica antes del lanzamiento para los diferentes módulos del proyecto CanSat (BME280/BMP280, LoRa SX1262, MQ2, y cámara OV7670).

---

## 📋 1. Módulo BMP280 / BME280 (Presión, Temperatura y Altitud)

### ⚙️ Ejecución
1. **Hardware:** Conectar el sensor por I2C (3.3V, GND, SDA, SCL) al Arduino R4 WiFi.
2. **Subir código:**
   ```powershell
   .\arduino-cli upload -p COMx --fqbn arduino:renesas_uno:unor4wifi "bme280\arduino\bme280_arduino"
   ```
3. **Estación Terrena (Dashboard en Vivo):**
   ```powershell
   py bme280/python/bme280_dashboard.py
   ```
4. **Post-misión (Reporte):**
   ```powershell
   py bme280/python/generate_report.py
   ```

### ⚠️ Posibles Fallos
- **El dashboard no conecta:** Puerto Serial ocupado por otra aplicación (ej: Arduino IDE) o cable desconectado.
- **Datos "Pico" o extraños:** Al arrancar pueden haber valores esporádicos. El de reporte automático de Python incluye filtro de "cribado" para estos casos.
- **Microcontrolador no lee:** La dirección I2C podría ser errónea (usualmente es `0x76` o `0x77`). Usar el script de escáner en `bme280/arduino/i2c_scanner`.

---

## 📡 2. Módulo de Comunicaciones LoRa SX1262 (868 MHz)

### ⚙️ Ejecución
1. **Hardware:** Conectar SX1262 (SPI + pines de control). ¡El LoRa **debe conectarse a 3.3V**, NUNCA a 5V directamente sin level-shifters!
2. **Subir códigos:** Subir `lora_emisor` al CanSat y `lora_receptor` a la estación de tierra.
3. **Estación Terrena (Dashboard):**
   ```powershell
   py lora/python/lora_dashboard.py
   ```
4. **Post-misión (Reporte):**
   ```powershell
   py lora/python/generate_lora_report.py
   ```

### ⚠️ Posibles Fallos
- **Error -2 al inicializar:** Falla la comunicación SPI. Verificar los cables MISO, MOSI, SCK, NSS y especialmente **RST** y **BUSY**.
- **No se reciben datos:** Asegurarse de que la "Sync Word", frecuencia (868 MHz) y los parámetros (SF7, BW125) son idénticos en emisor y receptor.
- **Antena no conectada:** No encender NUNCA el módulo LoRa sin la antena colocada; podría quemarse el amplificador (PA).

---

## 💨 3. Módulo MQ-2 (Calidad de Aire / Gases)

### ⚙️ Ejecución
1. **Hardware:** Conexión del sensor analógico y de alimentación (revisar pines analógicos asignados en el sketch).
2. **Subir código:**
   ```powershell
   .\arduino-cli upload -p COMx --fqbn arduino:renesas_uno:unor4wifi "mq2\arduino\mq2_pollution"
   ```
3. **Estación Terrena:**
   ```powershell
   py mq2/python/mq2_dashboard.py
   ```
4. **Post-misión:**
   ```powershell
   py mq2/python/generate_mq2_report.py
   ```

### ⚠️ Posibles Fallos
- **Falta de precalentamiento:** Este sensor contiene un calentador interno que requiere **estar encendido al menos de 3 a 5 minutos antes** de dar lecturas estables. Las lecturas inmediatas serán falsas.
- **Pico de corriente:** Al encenderse, consume bastante corriente. Asegurar que la batería/fuente del CanSat puede solventarlo sin reiniciar al Arduino R4 por caída de tensión.

---

## 📷 4. Módulo de Visión OV7670 (Detección de Incendios y Vegetación)

### ⚙️ Ejecución
1. **Hardware:** Muy estricto a **3.3V**. Conexiones I2C para configuración (SDA/SCL) y pines paralelos para datos, más señales VSYNC, HREF, PCLK y XCLK.
2. **Prueba Inicial:** Siempre ejecutar `ov7670_test` primero para verificar que el Arduino detecta la cámara en la red I2C (PID `0x76`).
3. **Subir código (Misión Principal):**
   ```powershell
   .\arduino-cli upload -p COMx --fqbn arduino:renesas_uno:unor4wifi "ov7670\arduino\ov7670_fire_detection"
   ```
4. **Estación Terrena:**
   ```powershell
   py ov7670/python/ov7670_dashboard.py
   ```

### ⚠️ Posibles Fallos
- **No se detecta la cámara por I2C:** Falta la señal de reloj principal (`XCLK`), la cual el Arduino debe generar por PWM, o el pin RESET no está atado a 3.3V / PWDN a GND.
- **Imágenes "basura" o parpadeantes:** Ocurre si `VSYNC` o `PCLK` están haciendo ruido EMI. Asegurar usar cables muy cortos, o bien es problema de la iluminación de donde se toma (contraluz).
- **El índice FDI de incendio marca alto en todo:** Calibración inadecuada del balance de blanco y umbrales frente a la luz directa del sol. 

---

## ✔️ Checklist Pre-Lanzamiento (GO / NO-GO)

*Realizar estos pasos 30 minutos antes del vuelo y bloquear después el sistema.*

- [ ] **Baterías al 100%:** Medir voltaje con multímetro. Un CanSat con carga baja puede apagar módulos al encender otros (ej. MQ2, que requiere mucha corriente).
- [ ] **LoRa - Antenas Colocadas:** Confirmar antenas apretadas en Emisor y Receptor. *Encender sin antena daña el módulo irrevocablemente.*
- [ ] **LoRa - Señal "Lock":** Verificada la recepción constante inyectando datos de prueba. Probar distancia alejándose 50-100 metros.
- [ ] **Sensores MQ2 - Precalentados:** Han pasado >3 mins desde el encendido. Lecturas estables en el Monitor/Dashboard.
- [ ] **BMP280 - Altitud Cero Relativa:** Calibrar o anotar la presión base a nivel de suelo para medir la altura relativa correctamente en caída libre (QNH).
- [ ] **OV7670 - Test I2C OK:** Se recibe confirmación en monitor serie del PID `0x76`.
- [ ] **OV7670 - Lentes limpias:** Limpiar el pequeño lente y quitar cualquier tapa protectora.
- [ ] **Almacenamiento Terrestre:** Dashboard y scripts Python iniciados en la laptop en una carpeta correcta y guardando logs. Verificar que se está escribiendo en el archivo CSV `data/`.
- [ ] **Tiro del pin / Paracaídas:** Sistema de recuperación desplegable revisado y no entrelazado.

¡Con todos los puntos en verde, **GO FOR LAUNCH**!
