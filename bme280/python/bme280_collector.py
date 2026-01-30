# bme280_collector.py
# Script para recolectar datos del sensor BME280 desde Arduino R4 WiFi
import re
import csv
import time
from datetime import datetime

import serial
import serial.tools.list_ports

import os

# ========= CONFIG =========
PORT = None  # Auto-detect si es None, o especificar "COM5", "COM6", etc.
BAUD = 115200
READ_TIMEOUT = 2.0
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CSV_FILE = os.path.join(DATA_DIR, "bme280_data.csv")

# Mapeo de claves del sensor
KEYMAP = {
    "temp": {"temp", "t", "temperature"},
    "hum": {"hum", "h", "humidity"},
    "pres": {"pres", "p", "pressure"},
    "alt": {"alt", "altitude", "height"},
}

 
def find_arduino_port():
    """Intenta encontrar automáticamente el puerto del Arduino."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        # Arduino R4 WiFi suele identificarse con estos strings
        if "Arduino" in port.description or "USB" in port.description:
            print(f"[INFO] Arduino detectado en: {port.device}")
            return port.device
    # Si no se detecta, intentar COM5 o COM6
    for port in ports:
        if port.device in ["COM5", "COM6"]:
            print(f"[INFO] Usando puerto: {port.device}")
            return port.device
    return None


def parse_line(line: str):
    """Parsea pares key=value con valores float."""
    out = {}
    pairs = re.findall(r"([A-Za-z_]+)\s*=\s*([-+]?\d+(?:\.\d+)?)", line)
    if not pairs:
        return out

    raw = {k.strip().lower(): float(v) for k, v in pairs}

    for std_key, aliases in KEYMAP.items():
        for a in aliases:
            if a in raw:
                out[std_key] = raw[a]
                break
    return out


def init_csv(filename):
    """Inicializa el archivo CSV con encabezados."""
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "temperature_C", "humidity_%", "pressure_hPa", "altitude_m"])
    print(f"[INFO] Archivo CSV inicializado: {filename}")


def append_csv(filename, data):
    """Añade una fila de datos al CSV."""
    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            data.get("timestamp", ""),
            data.get("temp", ""),
            data.get("hum", ""),
            data.get("pres", ""),
            data.get("alt", ""),
        ])


def main():
    global PORT

    print("=" * 60)
    print("  BME280 Data Collector with Safeguards - Arduino R4 WiFi")
    print("=" * 60)

    # Inicializar CSV
    init_csv(CSV_FILE)

    while True:
        # Detectar puerto si no está especificado
        if PORT is None:
            PORT = find_arduino_port()
        
        if PORT is None:
            print("[ERROR] No se encontró ningún Arduino. Reintentando en 5s...")
            time.sleep(5)
            continue

        # Conectar al puerto serial
        try:
            ser = serial.Serial(PORT, BAUD, timeout=READ_TIMEOUT)
            print(f"[INFO] Conectado a {PORT} @ {BAUD} baud")
            time.sleep(2) # Esperar inicialización
        except serial.SerialException as e:
            print(f"[ERROR] No se pudo conectar al puerto {PORT}: {e}")
            print("[INFO] Reintentando en 5s...")
            time.sleep(5)
            PORT = None # Forzar re-detección
            continue

        print("\n[INFO] Recolectando datos (Ctrl+C para detener)...\n")
        print(f"{'Timestamp':<25} {'Temp (°C)':<12} {'Hum (%)':<12} {'Pres (hPa)':<14} {'Alt (m)':<10}")
        print("-" * 75)

        last_data_time = time.time()
        
        try:
            while True:
                try:
                    if not ser.is_open:
                        raise serial.SerialException("Puerto cerrado inesperadamente")
                        
                    raw = ser.readline().decode("utf-8", errors="ignore").strip()
                except (serial.SerialException, OSError) as e:
                    print(f"\n[ERROR] Error de conexión: {e}")
                    break # Salir del bucle interno para reintentar conexión

                if not raw:
                    # Verificar timeout de datos (5 segundos sin recibir nada)
                    if time.time() - last_data_time > 5:
                        print("\n[WARNING] No se reciben datos del Arduino (Timeout). Verificando...")
                        last_data_time = time.time() # Reset para no spamear
                    continue

                # Reset timeout al recibir cualquier cosa
                last_data_time = time.time()

                # Manejo de errores reportados por Arduino
                if "error=" in raw:
                    error_msg = raw.split("error=")[1]
                    print(f"\n[CRITICAL] Error del sensor: {error_msg}")
                    continue
                
                if "info=" in raw:
                    info_msg = raw.split("info=")[1]
                    print(f"[INFO] Arduino: {info_msg}")
                    continue

                data = parse_line(raw)
                if not data:
                    continue

                # Añadir timestamp
                data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Mostrar en terminal
                temp = data.get("temp", "-")
                hum = data.get("hum", "-")
                pres = data.get("pres", "-")
                alt = data.get("alt", "-")

                print(f"{data['timestamp']:<25} {temp:<12} {hum:<12} {pres:<14} {alt:<10}")

                # Guardar en CSV
                append_csv(CSV_FILE, data)

        except KeyboardInterrupt:
            print("\n\n[INFO] Recolección detenida por el usuario.")
            ser.close()
            return # Salir completamente
        except Exception as e:
            print(f"\n[ERROR] Error inesperado: {e}")
        finally:
            if ser.is_open:
                ser.close()
            print("[INFO] Intentando reconectar...")
            time.sleep(2)


if __name__ == "__main__":
    main()
