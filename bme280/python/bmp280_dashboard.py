# bmp280_dashboard.py
# Dashboard profesional para datos del BMP280 - CanSat Competition Ready
# BMP280 = Temperatura + Presión + Altitud (SIN HUMEDAD)

import re
import time
from collections import deque
from datetime import datetime
import numpy as np

import serial
import serial.tools.list_ports
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import matplotlib.patheffects as path_effects
import os
import csv

# ========= CONFIG =========
PORT = None  # Auto-detect
BAUD = 115200  # Debe coincidir con Serial.begin() del receptor
WINDOW = 120  # 2 minutos de datos a 1 Hz
READ_TIMEOUT = 0.1  # Timeout corto para no bloquear la UI

# ========= UMBRALES DE ANOMALÍAS =========
ANOMALY_THRESHOLDS = {
    "alt": 50.0,    # metros
    "temp": 10.0,   # °C
    "pres": 20.0,   # hPa
}

# Límites ABSOLUTOS de valores válidos
BASELINE_ALTITUDE = 650.0  # Ajusta a tu ubicación
ALTITUDE_TOLERANCE = 500.0

VALID_RANGES = {
    "alt": (BASELINE_ALTITUDE - ALTITUDE_TOLERANCE, BASELINE_ALTITUDE + ALTITUDE_TOLERANCE),
    "temp": (-40.0, 85.0),    # Rango del BMP280
    "pres": (300.0, 1100.0),  # Rango del BMP280
}

MIN_RESET_INTERVAL = 5.0
MAX_RESETS_BEFORE_ERROR = 3

# Mapeo de claves del sensor
KEYMAP = {
    "temp": {"temp", "t", "temperature"},
    "pres": {"pres", "p", "pressure"},
    "alt": {"alt", "altitude", "height"},
}

# ========= PALETA DE COLORES PROFESIONAL =========
COLORS = {
    # Fondos
    "bg_dark": "#0d1117",
    "bg_panel": "#161b22",
    "bg_card": "#21262d",
    
    # Acentos vibrantes
    "temp": "#ff6b6b",      # Rojo coral - Temperatura
    "temp_light": "#ff8787",
    "pres": "#ffd93d",      # Amarillo dorado - Presión
    "pres_light": "#ffe066",
    "alt": "#6c5ce7",       # Púrpura vibrante - Altitud
    "alt_light": "#a29bfe",
    
    # Texto
    "text_primary": "#f0f6fc",
    "text_secondary": "#8b949e",
    "text_muted": "#484f58",
    
    # Estados
    "success": "#3fb950",
    "warning": "#d29922",
    "error": "#f85149",
    
    # Grid y bordes
    "grid": "#30363d",
    "border": "#21262d",
}

# ========= FUNCIONES AUXILIARES =========
def find_arduino_port():
    """Detecta automáticamente el puerto del Arduino."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "Arduino" in port.description or "USB" in port.description:
            return port.device
    for port in ports:
        if port.device in ["COM3", "COM4", "COM5", "COM6", "COM9"]:
            return port.device
    return None


# Estado del parseo LoRa: guardamos RSSI/SNR hasta que llegue la linea CANSAT
current_rssi = None
current_snr = None

def parse_line(line: str):
    """Parsea datos del serial. Soporta multiples formatos de receptor LoRa."""
    global current_rssi, current_snr
    out = {}
    
    if not line:
        return out
    
    # Capturar RSSI - formato limpio: "RSSI: -34.0"
    m = re.match(r"RSSI:\s*([-+]?[\d.]+)", line)
    if m:
        current_rssi = float(m.group(1))
        return out
    
    # Capturar RSSI - formato verbose: "RSSI (Fuerza): -34.00 dBm"
    m = re.match(r"RSSI\s*\(.*?\):\s*([-+]?[\d.]+)", line)
    if m:
        current_rssi = float(m.group(1))
        return out
    
    # Capturar SNR - formato limpio: "SNR: 10.75"
    m = re.match(r"SNR:\s*([-+]?[\d.]+)", line)
    if m:
        current_snr = float(m.group(1))
        return out
    
    # Capturar SNR - formato verbose: "SNR (Calidad): 10.75 dB"
    m = re.match(r"SNR\s*\(.*?\):\s*([-+]?[\d.]+)", line)
    if m:
        current_snr = float(m.group(1))
        return out
    
    # Ignorar líneas informativas del receptor
    if line.startswith("[RX") or line.startswith("[") or line.startswith("===") or line.startswith("---"):
        return out
    if line.startswith("Iniciando") or line.startswith("Escuchando") or line.startswith("Módulo") or line.startswith("Error"):
        return out
    
    # Extraer datos CANSAT de cualquier formato:
    #   "CANSAT,655,19.98,932.57,694.48,0.00,655000"
    #   "Mensaje recibido: CANSAT,655,19.98,932.57,694.48,0.00,655000"
    cansat_match = re.search(r"CANSAT,(\S+)", line)
    if cansat_match:
        cansat_str = "CANSAT," + cansat_match.group(1)
        parts = cansat_str.split(",")
        if len(parts) >= 5:
            try:
                out["temp"] = float(parts[2])
                out["pres"] = float(parts[3])
                out["alt"] = float(parts[4])
                return out
            except (ValueError, IndexError):
                pass
        return out
    
    # Formato key=value original (conexión directa al sensor)
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


def format_time(seconds):
    """Formatea segundos a HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def check_anomaly(key, new_value, old_value):
    """Verifica si hay un cambio anómalo en un valor."""
    if old_value is None or new_value is None:
        return False, 0, "delta"
    if np.isnan(new_value) or np.isnan(old_value):
        return False, 0, "delta"
    
    delta = abs(new_value - old_value)
    threshold = ANOMALY_THRESHOLDS.get(key, float("inf"))
    
    if delta > threshold:
        return True, delta, "delta"
    return False, delta, "delta"


def is_value_in_valid_range(key, value):
    """Verifica si un valor está dentro del rango físico válido."""
    if value is None or np.isnan(value):
        return False, "invalid"
    
    if key in VALID_RANGES:
        min_val, max_val = VALID_RANGES[key]
        if value < min_val or value > max_val:
            return False, f"fuera de rango [{min_val:.0f}, {max_val:.0f}]"
    
    return True, "ok"


def reset_arduino(ser, reason=""):
    """Resetea el Arduino usando la señal DTR."""
    global reset_count, last_reset_time
    
    current_time = time.monotonic()
    
    if current_time - last_reset_time < MIN_RESET_INTERVAL:
        print(f"[WARN] Reset ignorado - muy pronto desde el último reset")
        return False
    
    print(f"[RESET] Reiniciando Arduino: {reason}")
    
    ser.setDTR(False)
    time.sleep(0.1)
    ser.setDTR(True)
    time.sleep(2)
    
    reset_count += 1
    last_reset_time = current_time
    
    ser.reset_input_buffer()
    
    return True


# ========= DATA BUFFERS =========
t_data = deque(maxlen=WINDOW)
temp_data = deque(maxlen=WINDOW)
pres_data = deque(maxlen=WINDOW)
alt_data = deque(maxlen=WINDOW)

# Estadísticas
stats = {
    "temp": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
    "pres": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
    "alt": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
}

packet_count = 0
last_packet_time = time.monotonic()
data_rate = 0.0

# Control de anomalías y resets
reset_count = 0
last_reset_time = 0
anomaly_log = []
last_values = {"temp": None, "pres": None, "alt": None}

# Estado de errores de sensor
sensor_error_state = {"temp": False, "pres": False, "alt": False}
out_of_range_count = {"temp": 0, "pres": 0, "alt": 0}
CONSECUTIVE_ERRORS_FOR_ALERT = 5

# Buffers de datos LIMPIOS
t_clean = deque(maxlen=WINDOW)
temp_clean = deque(maxlen=WINDOW)
pres_clean = deque(maxlen=WINDOW)
alt_clean = deque(maxlen=WINDOW)

# Estadísticas LIMPIAS
stats_clean = {
    "temp": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
    "pres": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
    "alt": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
}

# ========= SERIAL CONNECTION =========
PORT = find_arduino_port()
if PORT is None:
    print("[ERROR] No se encontro Arduino. Conecta el dispositivo.")
    exit(1)

ser = serial.Serial(PORT, BAUD, timeout=READ_TIMEOUT)
print(f"[INFO] Conectado a {PORT} @ {BAUD} baudios")
time.sleep(2)

# ========= CSV INIT =========
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
CSV_FILE = os.path.join(DATA_DIR, "bmp280_data.csv")

with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "temperature_C", "pressure_hPa", "altitude_m"])
print(f"[INFO] Archivo CSV: {CSV_FILE}")

def log_data_to_csv(d):
    """Guarda una línea de datos en el CSV."""
    try:
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([
                ts,
                d.get("temp", ""),
                d.get("pres", ""),
                d.get("alt", "")
            ])
    except Exception as e:
        print(f"[ERROR] Error escribiendo CSV: {e}")


# ========= MATPLOTLIB SETUP =========
plt.style.use('dark_background')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans']
plt.rcParams['font.size'] = 10

fig = plt.figure(figsize=(14, 9))
fig.patch.set_facecolor(COLORS["bg_dark"])

# Grid layout: 3 filas x 2 columnas
gs = gridspec.GridSpec(3, 2, figure=fig, 
                       height_ratios=[0.6, 1.5, 1.5],
                       hspace=0.4, wspace=0.35)

# ========= HEADER PANEL =========
ax_header = fig.add_subplot(gs[0, :])
ax_header.set_facecolor(COLORS["bg_panel"])
ax_header.axis('off')

# Título principal
title_text = ax_header.text(0.5, 0.75, "CANSAT BMP280 MISSION DASHBOARD", 
                            fontsize=22, fontweight='bold', color=COLORS["text_primary"],
                            ha='center', va='center', transform=ax_header.transAxes)
title_text.set_path_effects([path_effects.withStroke(linewidth=2, foreground=COLORS["bg_dark"])])

# Subtítulo
ax_header.text(0.5, 0.45, "Temperatura | Presión | Altitud (sin sensor de humedad)", 
               fontsize=11, color=COLORS["text_secondary"],
               ha='center', va='center', transform=ax_header.transAxes)

# Info de misión
txt_mission_time = ax_header.text(0.12, 0.15, "MISSION TIME: 00:00:00", 
                                   fontsize=11, fontweight='bold', color=COLORS["text_secondary"],
                                   ha='center', va='center', transform=ax_header.transAxes,
                                   family='monospace')

txt_packets = ax_header.text(0.35, 0.15, "PACKETS: 0", 
                              fontsize=11, fontweight='bold', color=COLORS["text_secondary"],
                              ha='center', va='center', transform=ax_header.transAxes,
                              family='monospace')

txt_rate = ax_header.text(0.55, 0.15, "RATE: 0.0 Hz", 
                           fontsize=11, fontweight='bold', color=COLORS["text_secondary"],
                           ha='center', va='center', transform=ax_header.transAxes,
                           family='monospace')

txt_status = ax_header.text(0.75, 0.15, f"● CONNECTED ({PORT})", 
                             fontsize=11, fontweight='bold', color=COLORS["success"],
                             ha='center', va='center', transform=ax_header.transAxes)

txt_resets = ax_header.text(0.92, 0.15, "RESETS: 0", 
                             fontsize=11, fontweight='bold', color=COLORS["text_secondary"],
                             ha='center', va='center', transform=ax_header.transAxes,
                             family='monospace')

# Indicador de anomalía
txt_anomaly = ax_header.text(0.5, 0.5, "", 
                              fontsize=12, fontweight='bold', color=COLORS["error"],
                              ha='center', va='center', transform=ax_header.transAxes,
                              bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["bg_dark"], 
                                       edgecolor=COLORS["error"], alpha=0.9))

# ========= GRÁFICOS PRINCIPALES =========
ax_temp = fig.add_subplot(gs[1, 0])
ax_pres = fig.add_subplot(gs[1, 1])
ax_alt = fig.add_subplot(gs[2, 0])
ax_temp_alt = fig.add_subplot(gs[2, 1])

def style_axis(ax, title, ylabel, color, show_xlabel=True):
    """Estiliza un eje con diseño profesional."""
    ax.set_facecolor(COLORS["bg_card"])
    ax.set_title(title, fontsize=13, fontweight='bold', color=color, pad=12, loc='left')
    
    if show_xlabel:
        ax.set_xlabel("Tiempo (s)", fontsize=10, color=COLORS["text_secondary"], labelpad=8)
    ax.set_ylabel(ylabel, fontsize=10, color=COLORS["text_secondary"], labelpad=8)
    
    ax.tick_params(colors=COLORS["text_secondary"], labelsize=9)
    ax.grid(True, alpha=0.3, color=COLORS["grid"], linestyle='--', linewidth=0.5)
    
    for spine in ax.spines.values():
        spine.set_color(COLORS["grid"])
        spine.set_linewidth(0.5)

# Aplicar estilos
style_axis(ax_temp, "[T] TEMPERATURA", "°C", COLORS["temp"])
style_axis(ax_pres, "[P] PRESION ATMOSFERICA", "hPa", COLORS["pres"])
style_axis(ax_alt, "[A] ALTITUD", "m", COLORS["alt"])
style_axis(ax_temp_alt, "[T/A] TEMPERATURA vs ALTITUD", "Altitud (m)", COLORS["alt"])
ax_temp_alt.set_xlabel("Temperatura (°C)", fontsize=10, color=COLORS["text_secondary"], labelpad=8)

# ========= LÍNEAS DE DATOS =========
ln_temp, = ax_temp.plot([], [], color=COLORS["temp"], linewidth=2.5, alpha=0.95)
ln_pres, = ax_pres.plot([], [], color=COLORS["pres"], linewidth=2.5, alpha=0.95)
ln_alt, = ax_alt.plot([], [], color=COLORS["alt"], linewidth=2.5, alpha=0.95)
ln_temp_alt, = ax_temp_alt.plot([], [], color=COLORS["alt"], linewidth=2, alpha=0.8, 
                                 marker='o', markersize=3, linestyle='-')

# ========= VALORES ACTUALES GRANDES =========
txt_temp_val = ax_temp.text(0.95, 0.95, "--", fontsize=26, fontweight='bold', 
                            color=COLORS["temp_light"], ha='right', va='top',
                            transform=ax_temp.transAxes, family='monospace',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["bg_panel"], 
                                     edgecolor=COLORS["temp"], alpha=0.8))

txt_pres_val = ax_pres.text(0.95, 0.95, "--", fontsize=26, fontweight='bold',
                            color=COLORS["pres_light"], ha='right', va='top',
                            transform=ax_pres.transAxes, family='monospace',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["bg_panel"],
                                     edgecolor=COLORS["pres"], alpha=0.8))

txt_alt_val = ax_alt.text(0.95, 0.95, "--", fontsize=26, fontweight='bold',
                          color=COLORS["alt_light"], ha='right', va='top',
                          transform=ax_alt.transAxes, family='monospace',
                          bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["bg_panel"],
                                   edgecolor=COLORS["alt"], alpha=0.8))

# Stats en Temp vs Alt panel
txt_stats = ax_temp_alt.text(0.02, 0.98, "", fontsize=9, color=COLORS["text_secondary"],
                              ha='left', va='top', transform=ax_temp_alt.transAxes,
                              family='monospace',
                              bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["bg_panel"], alpha=0.8))

t0 = time.monotonic()


def update_stats(key, value):
    """Actualiza las estadísticas de un sensor."""
    if value is None or np.isnan(value):
        return
    stats[key]["min"] = min(stats[key]["min"], value)
    stats[key]["max"] = max(stats[key]["max"], value)
    stats[key]["sum"] += value
    stats[key]["count"] += 1


def get_avg(key):
    """Calcula el promedio de un sensor."""
    if stats[key]["count"] == 0:
        return float("nan")
    return stats[key]["sum"] / stats[key]["count"]


def update(_frame):
    global packet_count, last_packet_time, data_rate, last_values, reset_count
    
    # Leer TODAS las líneas disponibles sin bloquear
    lines_read = 0
    d = {}
    while ser.in_waiting > 0 and lines_read < 20:
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
        except Exception:
            break
        lines_read += 1
        if not line:
            continue
        print(f"[SER] {line}")
        
        if "error=" in line.lower():
            continue
        if "info=" in line.lower():
            txt_anomaly.set_text("")
            continue
        
        # Parsear cada línea (RSSI/SNR actualizan globals, CANSAT retorna datos)
        parsed = parse_line(line)
        if parsed:
            d = parsed  # Nos quedamos con los últimos datos válidos
    
    if not d:
        return
    
    # Actualizar contadores
    packet_count += 1
    current_time = time.monotonic()
    if current_time - last_packet_time > 0:
        data_rate = 0.7 * data_rate + 0.3 * (1.0 / (current_time - last_packet_time))
    last_packet_time = current_time
    
    now = current_time - t0
    
    # ========= DETECCIÓN DE ANOMALÍAS =========
    anomalies_detected = []
    range_errors = []
    
    for key in ["temp", "pres", "alt"]:
        if key in d:
            new_val = d[key]
            old_val = last_values[key]
            
            is_anomaly, delta, _ = check_anomaly(key, new_val, old_val)
            
            if is_anomaly:
                anomaly_info = {
                    "time": now,
                    "sensor": key,
                    "old_value": old_val,
                    "new_value": new_val,
                    "delta": delta,
                    "threshold": ANOMALY_THRESHOLDS[key],
                    "type": "delta"
                }
                anomalies_detected.append(anomaly_info)
                anomaly_log.append(anomaly_info)
                
                units = {"temp": "°C", "pres": "hPa", "alt": "m"}
                print(f"[ANOMALY] {key.upper()}: {old_val:.1f} -> {new_val:.1f} "
                      f"(Δ{delta:.1f}{units[key]}, umbral: {ANOMALY_THRESHOLDS[key]}{units[key]})")
            
            in_range, range_msg = is_value_in_valid_range(key, new_val)
            
            if not in_range:
                out_of_range_count[key] += 1
                range_errors.append(key)
                
                units = {"temp": "°C", "pres": "hPa", "alt": "m"}
                print(f"[OUT OF RANGE] {key.upper()}: {new_val:.1f}{units[key]} - {range_msg}")
                
                if out_of_range_count[key] >= CONSECUTIVE_ERRORS_FOR_ALERT:
                    sensor_error_state[key] = True
            else:
                out_of_range_count[key] = 0
                sensor_error_state[key] = False
    
    # Actualizar últimos valores
    for key in ["temp", "pres", "alt"]:
        if key in d:
            last_values[key] = d[key]
    
    # Guardar en CSV
    log_data_to_csv(d)

    # Guardar datos en buffers
    t_data.append(now)
    
    def push(buf, key):
        if key in d:
            val = d[key]
            buf.append(val)
            update_stats(key, val)
        else:
            buf.append(buf[-1] if len(buf) else float("nan"))
    
    push(temp_data, "temp")
    push(pres_data, "pres")
    push(alt_data, "alt")
    
    # Datos limpios
    all_valid = True
    for key in ["temp", "pres", "alt"]:
        if key in d:
            in_range, _ = is_value_in_valid_range(key, d[key])
            if not in_range:
                all_valid = False
                break
    
    if all_valid:
        t_clean.append(now)
        if "temp" in d: temp_clean.append(d["temp"])
        if "pres" in d: pres_clean.append(d["pres"])
        if "alt" in d: alt_clean.append(d["alt"])
        
        for key, buf in [("temp", temp_clean), ("pres", pres_clean), ("alt", alt_clean)]:
            if buf:
                val = buf[-1]
                stats_clean[key]["min"] = min(stats_clean[key]["min"], val)
                stats_clean[key]["max"] = max(stats_clean[key]["max"], val)
                stats_clean[key]["sum"] += val
                stats_clean[key]["count"] += 1
    
    if len(t_clean) < 2:
        if len(t_data) < 2:
            return
        t_list = list(t_data)
        temp_list = list(temp_data)
        pres_list = list(pres_data)
        alt_list = list(alt_data)
    else:
        t_list = list(t_clean)
        temp_list = list(temp_clean)
        pres_list = list(pres_clean)
        alt_list = list(alt_clean)
    
    # Actualizar líneas
    ln_temp.set_data(t_list, temp_list)
    ln_pres.set_data(t_list, pres_list)
    ln_alt.set_data(t_list, alt_list)
    ln_temp_alt.set_data(temp_list, alt_list)
    
    # Actualizar fills
    for ax, buf, color in [
        (ax_temp, temp_list, COLORS["temp"]),
        (ax_pres, pres_list, COLORS["pres"]),
        (ax_alt, alt_list, COLORS["alt"]),
    ]:
        for coll in ax.collections[:]:
            coll.remove()
        if len(t_list) > 1:
            ax.fill_between(t_list, buf, alpha=0.15, color=color)
    
    # Auto-escalar
    for ax in [ax_temp, ax_pres, ax_alt]:
        ax.relim()
        ax.autoscale_view()
    
    ax_temp_alt.relim()
    ax_temp_alt.autoscale_view()
    
    # Actualizar header
    txt_mission_time.set_text(f"MISSION TIME: {format_time(now)}")
    txt_packets.set_text(f"PACKETS: {packet_count}")
    txt_rate.set_text(f"RATE: {data_rate:.1f} Hz")
    
    # Valores actuales
    if temp_clean:
        txt_temp_val.set_text(f"{temp_clean[-1]:.1f}°C")
    elif temp_data:
        txt_temp_val.set_text(f"{temp_data[-1]:.1f}°C*")
    
    if pres_clean:
        txt_pres_val.set_text(f"{pres_clean[-1]:.1f}")
    elif pres_data:
        txt_pres_val.set_text(f"{pres_data[-1]:.1f}*")
    
    if alt_clean:
        txt_alt_val.set_text(f"{alt_clean[-1]:.1f}m")
    elif alt_data:
        txt_alt_val.set_text(f"{alt_data[-1]:.1f}m*")
    
    # Stats text
    stats_text = "ESTADÍSTICAS (limpias)\n"
    for key, name in [("temp", "Temp"), ("pres", "Pres"), ("alt", "Alt")]:
        if stats_clean[key]["count"] > 0:
            avg = stats_clean[key]["sum"] / stats_clean[key]["count"]
            stats_text += f"{name}: {stats_clean[key]['min']:.1f}/{avg:.1f}/{stats_clean[key]['max']:.1f}\n"
    txt_stats.set_text(stats_text.strip())
    
    # Actualizar resets
    txt_resets.set_text(f"RESETS: {reset_count}")
    if reset_count > 0:
        txt_resets.set_color(COLORS["warning"])
    if reset_count >= MAX_RESETS_BEFORE_ERROR:
        txt_resets.set_color(COLORS["error"])
    
    # Errores persistentes
    persistent_errors = [k.upper() for k, v in sensor_error_state.items() if v]
    if persistent_errors:
        txt_anomaly.set_text(f"! ERROR SENSOR: {', '.join(persistent_errors)}")
        txt_anomaly.set_color(COLORS["error"])
    elif range_errors and not anomalies_detected:
        sensor_names = {"temp": "TEMP", "pres": "PRES", "alt": "ALT"}
        error_sensors = [sensor_names[k] for k in range_errors]
        txt_anomaly.set_text(f"! FUERA DE RANGO: {', '.join(error_sensors)}")
        txt_anomaly.set_color(COLORS["warning"])
    
    # Manejar anomalías
    if anomalies_detected:
        sensor_names = {"temp": "TEMP", "pres": "PRES", "alt": "ALT"}
        anomaly_sensors = [sensor_names[a["sensor"]] for a in anomalies_detected]
        
        if reset_count < MAX_RESETS_BEFORE_ERROR:
            txt_anomaly.set_text(f"! ANOMALIA: {', '.join(anomaly_sensors)} - REINICIANDO...")
            txt_anomaly.set_color(COLORS["error"])
            
            reason = f"Anomalía en: {', '.join(anomaly_sensors)}"
            reset_arduino(ser, reason)
            
            for key in last_values:
                last_values[key] = None
        else:
            txt_anomaly.set_text(f"! MAX RESETS - Sensor defectuoso")
            txt_anomaly.set_color(COLORS["error"])


# ========= MAIN =========
print("\n" + "="*50)
print("  BMP280 DASHBOARD - Arduino Uno")
print("  Temperatura | Presión | Altitud")
print("  (Cerrar ventana para guardar datos)")
print("="*50 + "\n")

ani = FuncAnimation(fig, update, interval=200, cache_frame_data=False)
fig.subplots_adjust(top=0.95, bottom=0.06, left=0.08, right=0.97)
plt.show()

print(f"\n[INFO] Sesión terminada. Datos guardados en: {CSV_FILE}")
print(f"[INFO] Total de paquetes recibidos: {packet_count}")
print(f"[INFO] Total de resets: {reset_count}")
