# bme280_dashboard.py
# Dashboard profesional para datos del BME280 - CanSat Competition Ready
# Cumple con todos los requisitos de visualización de datos de la ESA CanSat

import re
import time
from collections import deque
from datetime import datetime
import numpy as np

import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import matplotlib.patheffects as path_effects
import os

# ========= CONFIG =========
import csv

PORT = None  # Auto-detect
BAUD = 115200
WINDOW = 120  # 2 minutos de datos a 1 Hz
READ_TIMEOUT = 2.0

# ========= UMBRALES DE ANOMALÍAS =========
# Cambios máximos permitidos por segundo (entre lecturas consecutivas)
ANOMALY_THRESHOLDS = {
    "alt": 50.0,    # metros - si cambia más de 50m en 1 segundo, es anomalía
    "temp": 10.0,   # °C - cambio de más de 10°C en 1 segundo
    "hum": 30.0,    # % - cambio de más de 30% en 1 segundo
    "pres": 20.0,   # hPa - cambio de más de 20 hPa en 1 segundo
}

# Límites ABSOLUTOS de valores válidos (fuera de estos rangos = error de sensor)
# Ajusta BASELINE_ALTITUDE a tu ubicación real
BASELINE_ALTITUDE = 650.0  # Altitud aproximada de tu ubicación (metros sobre nivel del mar)
ALTITUDE_TOLERANCE = 500.0  # Tolerancia máxima respecto a la baseline (metros)

VALID_RANGES = {
    "alt": (BASELINE_ALTITUDE - ALTITUDE_TOLERANCE, BASELINE_ALTITUDE + ALTITUDE_TOLERANCE),  # metros
    "temp": (-40.0, 85.0),    # °C - rango del BME280
    "hum": (0.0, 100.0),      # % - rango físico
    "pres": (300.0, 1100.0),  # hPa - rango del BME280
}

# Tiempo mínimo entre resets (segundos) para evitar resets en bucle
MIN_RESET_INTERVAL = 5.0

# Máximo número de resets antes de marcar como error persistente
MAX_RESETS_BEFORE_ERROR = 3

# Mapeo de claves del sensor
KEYMAP = {
    "temp": {"temp", "t", "temperature"},
    "hum": {"hum", "h", "humidity"},
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
    "hum": "#4ecdc4",       # Turquesa - Humedad
    "hum_light": "#63e6be",
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
        if port.device in ["COM5", "COM6", "COM9"]:
            return port.device
    return None


def parse_line(line: str):
    """Parsea pares key=value."""
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
    
    # Evitar resets muy frecuentes
    if current_time - last_reset_time < MIN_RESET_INTERVAL:
        print(f"[WARN] Reset ignorado - muy pronto desde el último reset")
        return False
    
    print(f"[RESET] Reiniciando Arduino: {reason}")
    
    # Toggle DTR para resetear el Arduino
    ser.setDTR(False)
    time.sleep(0.1)
    ser.setDTR(True)
    time.sleep(2)  # Esperar a que el Arduino reinicie
    
    reset_count += 1
    last_reset_time = current_time
    
    # Limpiar buffer serial
    ser.reset_input_buffer()
    
    return True


# ========= DATA BUFFERS =========
t_data = deque(maxlen=WINDOW)
temp_data = deque(maxlen=WINDOW)
hum_data = deque(maxlen=WINDOW)
pres_data = deque(maxlen=WINDOW)
alt_data = deque(maxlen=WINDOW)

# Estadísticas
stats = {
    "temp": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
    "hum": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
    "pres": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
    "alt": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
}

packet_count = 0
last_packet_time = time.monotonic()
data_rate = 0.0

# Control de anomalías y resets
reset_count = 0
last_reset_time = 0
anomaly_log = []  # Lista de anomalías detectadas
last_values = {"temp": None, "hum": None, "pres": None, "alt": None}

# Estado de errores de sensor
sensor_error_state = {"temp": False, "hum": False, "pres": False, "alt": False}
out_of_range_count = {"temp": 0, "hum": 0, "pres": 0, "alt": 0}
CONSECUTIVE_ERRORS_FOR_ALERT = 5  # Lecturas consecutivas fuera de rango para marcar error

# Buffers de datos LIMPIOS (sin anomalías) para gráficas
t_clean = deque(maxlen=WINDOW)
temp_clean = deque(maxlen=WINDOW)
hum_clean = deque(maxlen=WINDOW)
pres_clean = deque(maxlen=WINDOW)
alt_clean = deque(maxlen=WINDOW)

# Estadísticas LIMPIAS (solo valores válidos)
stats_clean = {
    "temp": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
    "hum": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
    "pres": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
    "alt": {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0},
}

# ========= SERIAL CONNECTION =========
PORT = find_arduino_port()
if PORT is None:
    print("[ERROR] No se encontro Arduino. Conecta el dispositivo.")
    exit(1)

ser = serial.Serial(PORT, BAUD, timeout=READ_TIMEOUT)
print(f"[INFO] Conectado a {PORT}")
time.sleep(2)

# ========= CSV INIT =========
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CSV_FILE = os.path.join(DATA_DIR, "bme280_data.csv")
# Siempre reiniciar el archivo CSV al inicio de cada sesión
with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "temperature_C", "humidity_%", "pressure_hPa", "altitude_m"])
print(f"[INFO] Archivo CSV reiniciado para nueva sesión: {CSV_FILE}")

def log_data_to_csv(d):
    """Guarda una línea de datos en el CSV."""
    try:
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([
                ts,
                d.get("temp", ""),
                d.get("hum", ""),
                d.get("pres", ""),
                d.get("alt", "")
            ])
    except Exception as e:
        print(f"[ERROR] Error escribiendo CSV: {e}")


# ========= MATPLOTLIB SETUP =========
plt.style.use('dark_background')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Segoe UI', 'Arial', 'DejaVu Sans']
plt.rcParams['font.size'] = 10

fig = plt.figure(figsize=(16, 10))
fig.patch.set_facecolor(COLORS["bg_dark"])

# Grid layout: 4 filas x 4 columnas
gs = gridspec.GridSpec(4, 4, figure=fig, 
                       height_ratios=[0.8, 1.5, 1.5, 1.2],
                       hspace=0.4, wspace=0.35)

# ========= HEADER PANEL =========
ax_header = fig.add_subplot(gs[0, :])
ax_header.set_facecolor(COLORS["bg_panel"])
ax_header.axis('off')

# Título principal
title_text = ax_header.text(0.5, 0.75, "CANSAT BME280 MISSION DASHBOARD", 
                            fontsize=22, fontweight='bold', color=COLORS["text_primary"],
                            ha='center', va='center', transform=ax_header.transAxes)
title_text.set_path_effects([path_effects.withStroke(linewidth=2, foreground=COLORS["bg_dark"])])

# Info de misión
txt_mission_time = ax_header.text(0.15, 0.25, "MISSION TIME: 00:00:00", 
                                   fontsize=12, fontweight='bold', color=COLORS["text_secondary"],
                                   ha='center', va='center', transform=ax_header.transAxes,
                                   family='monospace')

txt_packets = ax_header.text(0.40, 0.25, "PACKETS: 0", 
                              fontsize=12, fontweight='bold', color=COLORS["text_secondary"],
                              ha='center', va='center', transform=ax_header.transAxes,
                              family='monospace')

txt_rate = ax_header.text(0.60, 0.25, "RATE: 0.0 Hz", 
                           fontsize=12, fontweight='bold', color=COLORS["text_secondary"],
                           ha='center', va='center', transform=ax_header.transAxes,
                           family='monospace')

txt_status = ax_header.text(0.78, 0.25, f"● CONNECTED ({PORT})", 
                             fontsize=12, fontweight='bold', color=COLORS["success"],
                             ha='center', va='center', transform=ax_header.transAxes)

txt_resets = ax_header.text(0.93, 0.25, "RESETS: 0", 
                             fontsize=12, fontweight='bold', color=COLORS["text_secondary"],
                             ha='center', va='center', transform=ax_header.transAxes,
                             family='monospace')

# Indicador de anomalía (oculto inicialmente)
txt_anomaly = ax_header.text(0.5, 0.5, "", 
                              fontsize=14, fontweight='bold', color=COLORS["error"],
                              ha='center', va='center', transform=ax_header.transAxes,
                              bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["bg_dark"], 
                                       edgecolor=COLORS["error"], alpha=0.9))

# ========= GRÁFICOS PRINCIPALES =========
# Fila 1: Temperatura y Humedad
ax_temp = fig.add_subplot(gs[1, 0:2])
ax_hum = fig.add_subplot(gs[1, 2:4])

# Fila 2: Presión y Altitud
ax_pres = fig.add_subplot(gs[2, 0:2])
ax_alt = fig.add_subplot(gs[2, 2:4])

# Fila 3: Temp vs Altitud y Panel de estadísticas
ax_temp_alt = fig.add_subplot(gs[3, 0:2])
ax_stats = fig.add_subplot(gs[3, 2:4])

def style_axis(ax, title, ylabel, color, show_xlabel=True):
    """Estiliza un eje con diseño profesional."""
    ax.set_facecolor(COLORS["bg_card"])
    
    # Título con icono
    ax.set_title(title, fontsize=13, fontweight='bold', color=color, 
                 pad=12, loc='left')
    
    if show_xlabel:
        ax.set_xlabel("Tiempo (s)", fontsize=10, color=COLORS["text_secondary"], labelpad=8)
    ax.set_ylabel(ylabel, fontsize=10, color=COLORS["text_secondary"], labelpad=8)
    
    ax.tick_params(colors=COLORS["text_secondary"], labelsize=9)
    ax.grid(True, alpha=0.3, color=COLORS["grid"], linestyle='--', linewidth=0.5)
    
    for spine in ax.spines.values():
        spine.set_color(COLORS["grid"])
        spine.set_linewidth(0.5)

# Aplicar estilos
style_axis(ax_temp, "TEMPERATURA", "°C", COLORS["temp"])
style_axis(ax_hum, "HUMEDAD", "%", COLORS["hum"])
style_axis(ax_pres, "PRESION ATMOSFERICA", "hPa", COLORS["pres"])
style_axis(ax_alt, "ALTITUD", "m", COLORS["alt"])
style_axis(ax_temp_alt, "TEMPERATURA vs ALTITUD", "Altitud (m)", COLORS["alt"])
ax_temp_alt.set_xlabel("Temperatura (°C)", fontsize=10, color=COLORS["text_secondary"], labelpad=8)

# Panel de estadísticas
ax_stats.set_facecolor(COLORS["bg_card"])
ax_stats.axis('off')
ax_stats.set_title("ESTADISTICAS EN TIEMPO REAL", fontsize=13, fontweight='bold', 
                   color=COLORS["text_primary"], pad=12, loc='left')

# ========= LÍNEAS DE DATOS =========
ln_temp, = ax_temp.plot([], [], color=COLORS["temp"], linewidth=2.5, alpha=0.95)
ln_hum, = ax_hum.plot([], [], color=COLORS["hum"], linewidth=2.5, alpha=0.95)
ln_pres, = ax_pres.plot([], [], color=COLORS["pres"], linewidth=2.5, alpha=0.95)
ln_alt, = ax_alt.plot([], [], color=COLORS["alt"], linewidth=2.5, alpha=0.95)
ln_temp_alt, = ax_temp_alt.plot([], [], color=COLORS["alt"], linewidth=2, alpha=0.8, 
                                 marker='o', markersize=3, linestyle='-')

# ========= TEXTOS DE ESTADÍSTICAS =========
stats_labels = {}
stats_values = {}

# Posiciones para la tabla de estadísticas
cols = [0.15, 0.40, 0.65, 0.90]
rows = [0.85, 0.65, 0.45, 0.25, 0.05]
headers = ["TEMP (°C)", "HUM (%)", "PRES (hPa)", "ALT (m)"]
row_labels = ["ACTUAL", "MIN", "MAX", "PROMEDIO"]
colors_list = [COLORS["temp"], COLORS["hum"], COLORS["pres"], COLORS["alt"]]

# Headers de columnas
for i, (header, col, color) in enumerate(zip(headers, cols, colors_list)):
    ax_stats.text(col, rows[0], header, fontsize=10, fontweight='bold', color=color,
                  ha='center', va='center', transform=ax_stats.transAxes)

# Labels de filas y valores
for j, (row_label, row_y) in enumerate(zip(row_labels, rows[1:])):
    # Label de fila (izquierda)
    ax_stats.text(0.02, row_y, row_label, fontsize=9, fontweight='bold', 
                  color=COLORS["text_muted"], ha='left', va='center', 
                  transform=ax_stats.transAxes)
    
    for i, (col, color) in enumerate(zip(cols, colors_list)):
        key = f"{['temp', 'hum', 'pres', 'alt'][i]}_{['cur', 'min', 'max', 'avg'][j]}"
        txt = ax_stats.text(col, row_y, "--", fontsize=11 if j == 0 else 10, 
                            fontweight='bold' if j == 0 else 'normal',
                            color=color if j == 0 else COLORS["text_secondary"],
                            ha='center', va='center', transform=ax_stats.transAxes,
                            family='monospace')
        stats_values[key] = txt

# ========= VALORES ACTUALES GRANDES =========
# Añadir valores actuales en cada gráfico
txt_temp_val = ax_temp.text(0.95, 0.95, "--", fontsize=24, fontweight='bold', 
                            color=COLORS["temp_light"], ha='right', va='top',
                            transform=ax_temp.transAxes, family='monospace',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["bg_panel"], 
                                     edgecolor=COLORS["temp"], alpha=0.8))

txt_hum_val = ax_hum.text(0.95, 0.95, "--", fontsize=24, fontweight='bold',
                          color=COLORS["hum_light"], ha='right', va='top',
                          transform=ax_hum.transAxes, family='monospace',
                          bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["bg_panel"],
                                   edgecolor=COLORS["hum"], alpha=0.8))

txt_pres_val = ax_pres.text(0.95, 0.95, "--", fontsize=24, fontweight='bold',
                            color=COLORS["pres_light"], ha='right', va='top',
                            transform=ax_pres.transAxes, family='monospace',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["bg_panel"],
                                     edgecolor=COLORS["pres"], alpha=0.8))

txt_alt_val = ax_alt.text(0.95, 0.95, "--", fontsize=24, fontweight='bold',
                          color=COLORS["alt_light"], ha='right', va='top',
                          transform=ax_alt.transAxes, family='monospace',
                          bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["bg_panel"],
                                   edgecolor=COLORS["alt"], alpha=0.8))

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
    
    try:
        raw = ser.readline().decode("utf-8", errors="ignore").strip()
    except Exception:
        return
    
    if not raw or "error=" in raw.lower():
        return
    
    if "info=" in raw.lower():
        # Limpiar mensaje de anomalía después de reset
        txt_anomaly.set_text("")
        return
    
    d = parse_line(raw)
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
    
    for key in ["temp", "hum", "pres", "alt"]:
        if key in d:
            new_val = d[key]
            old_val = last_values[key]
            
            # 1. Verificar cambio brusco (delta)
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
                
                # Log en consola
                units = {"temp": "°C", "hum": "%", "pres": "hPa", "alt": "m"}
                print(f"[ANOMALY] {key.upper()}: {old_val:.1f} -> {new_val:.1f} "
                      f"(Δ{delta:.1f}{units[key]}, umbral: {ANOMALY_THRESHOLDS[key]}{units[key]})")
            
            # 2. Verificar rango absoluto
            in_range, range_msg = is_value_in_valid_range(key, new_val)
            
            if not in_range:
                out_of_range_count[key] += 1
                range_errors.append(key)
                
                units = {"temp": "°C", "hum": "%", "pres": "hPa", "alt": "m"}
                print(f"[OUT OF RANGE] {key.upper()}: {new_val:.1f}{units[key]} - {range_msg} "
                      f"(consecutivos: {out_of_range_count[key]})")
                
                # Marcar como error persistente si supera el umbral
                if out_of_range_count[key] >= CONSECUTIVE_ERRORS_FOR_ALERT:
                    sensor_error_state[key] = True
                    print(f"[SENSOR ERROR] {key.upper()} marcado como ERROR PERSISTENTE")
            else:
                # Resetear contador si vuelve a estar en rango
                out_of_range_count[key] = 0
                sensor_error_state[key] = False
    
    # Actualizar últimos valores ANTES de cualquier reset
    for key in ["temp", "hum", "pres", "alt"]:
        if key in d:
            last_values[key] = d[key]
    
    # Guardar en CSV (siempre que llegue un paquete parseado)
    log_data_to_csv(d)

    # Guardar datos en buffers ANTES de reset (para que no se pierdan)
    t_data.append(now)
    
    # Push datos y actualizar estadísticas
    def push(buf, key):
        if key in d:
            val = d[key]
            buf.append(val)
            update_stats(key, val)
        else:
            buf.append(buf[-1] if len(buf) else float("nan"))
    
    # Push datos LIMPIOS (solo si están en rango válido)
    def push_clean(buf, buf_clean, key, t_now):
        if key in d:
            val = d[key]
            in_range, _ = is_value_in_valid_range(key, val)
            if in_range:
                buf_clean.append(val)
                # Actualizar estadísticas limpias
                stats_clean[key]["min"] = min(stats_clean[key]["min"], val)
                stats_clean[key]["max"] = max(stats_clean[key]["max"], val)
                stats_clean[key]["sum"] += val
                stats_clean[key]["count"] += 1
                return True
        return False
    
    push(temp_data, "temp")
    push(hum_data, "hum")
    push(pres_data, "pres")
    push(alt_data, "alt")
    
    # Añadir a buffers limpios solo si TODOS los valores son válidos
    all_valid = True
    for key in ["temp", "hum", "pres", "alt"]:
        if key in d:
            in_range, _ = is_value_in_valid_range(key, d[key])
            if not in_range:
                all_valid = False
                break
    
    if all_valid:
        t_clean.append(now)
        if "temp" in d: temp_clean.append(d["temp"])
        if "hum" in d: hum_clean.append(d["hum"])
        if "pres" in d: pres_clean.append(d["pres"])
        if "alt" in d: alt_clean.append(d["alt"])
        # Actualizar estadísticas limpias
        for key, buf in [("temp", temp_clean), ("hum", hum_clean), ("pres", pres_clean), ("alt", alt_clean)]:
            if buf:
                val = buf[-1]
                stats_clean[key]["min"] = min(stats_clean[key]["min"], val)
                stats_clean[key]["max"] = max(stats_clean[key]["max"], val)
                stats_clean[key]["sum"] += val
                stats_clean[key]["count"] += 1
    
    if len(t_clean) < 2:
        # Si no hay datos limpios suficientes, intentar con datos raw pero limitados
        if len(t_data) < 2:
            return
        # Usar datos raw temporalmente
        t_list = list(t_data)
        temp_list = list(temp_data)
        hum_list = list(hum_data)
        pres_list = list(pres_data)
        alt_list = list(alt_data)
    else:
        # Usar datos LIMPIOS para las gráficas
        t_list = list(t_clean)
        temp_list = list(temp_clean)
        hum_list = list(hum_clean)
        pres_list = list(pres_clean)
        alt_list = list(alt_clean)
    
    # Actualizar líneas principales con datos LIMPIOS
    ln_temp.set_data(t_list, temp_list)
    ln_hum.set_data(t_list, hum_list)
    ln_pres.set_data(t_list, pres_list)
    ln_alt.set_data(t_list, alt_list)
    
    # Actualizar Temp vs Altitud con datos LIMPIOS
    ln_temp_alt.set_data(temp_list, alt_list)
    
    # Actualizar fills (gradiente bajo la línea) con datos LIMPIOS
    for ax, buf, color in [
        (ax_temp, temp_list, COLORS["temp"]),
        (ax_hum, hum_list, COLORS["hum"]),
        (ax_pres, pres_list, COLORS["pres"]),
        (ax_alt, alt_list, COLORS["alt"]),
    ]:
        for coll in ax.collections[:]:
            coll.remove()
        if len(t_list) > 1:
            ax.fill_between(t_list, buf, alpha=0.15, color=color)
    
    # Auto-escalar gráficos temporales
    for ax in [ax_temp, ax_hum, ax_pres, ax_alt]:
        ax.relim()
        ax.autoscale_view()
    
    # Auto-escalar Temp vs Alt
    ax_temp_alt.relim()
    ax_temp_alt.autoscale_view()
    
    # Actualizar header
    txt_mission_time.set_text(f"MISSION TIME: {format_time(now)}")
    txt_packets.set_text(f"PACKETS: {packet_count}")
    txt_rate.set_text(f"RATE: {data_rate:.1f} Hz")
    
    # Actualizar valores actuales en gráficos (usar datos limpios si disponibles)
    if temp_clean:
        txt_temp_val.set_text(f"{temp_clean[-1]:.1f}°C")
    elif temp_data:
        # Si no hay limpios, mostrar raw con indicador
        txt_temp_val.set_text(f"{temp_data[-1]:.1f}°C*")
    
    if hum_clean:
        txt_hum_val.set_text(f"{hum_clean[-1]:.1f}%")
    elif hum_data:
        txt_hum_val.set_text(f"{hum_data[-1]:.1f}%*")
    
    if pres_clean:
        txt_pres_val.set_text(f"{pres_clean[-1]:.1f}")
    elif pres_data:
        txt_pres_val.set_text(f"{pres_data[-1]:.1f}*")
    
    if alt_clean:
        txt_alt_val.set_text(f"{alt_clean[-1]:.1f}m")
    elif alt_data:
        txt_alt_val.set_text(f"{alt_data[-1]:.1f}m*")
    
    # Actualizar tabla de estadísticas (usar estadísticas LIMPIAS)
    sensors = ["temp", "hum", "pres", "alt"]
    clean_bufs = {"temp": temp_clean, "hum": hum_clean, "pres": pres_clean, "alt": alt_clean}
    
    for sensor in sensors:
        buf = clean_bufs[sensor]
        
        # Valor actual (limpio)
        if buf:
            stats_values[f"{sensor}_cur"].set_text(f"{buf[-1]:.1f}")
        
        # Usar estadísticas LIMPIAS
        if stats_clean[sensor]["min"] != float("inf"):
            stats_values[f"{sensor}_min"].set_text(f"{stats_clean[sensor]['min']:.1f}")
        
        if stats_clean[sensor]["max"] != float("-inf"):
            stats_values[f"{sensor}_max"].set_text(f"{stats_clean[sensor]['max']:.1f}")
        
        # Avg limpio
        if stats_clean[sensor]["count"] > 0:
            avg = stats_clean[sensor]["sum"] / stats_clean[sensor]["count"]
            stats_values[f"{sensor}_avg"].set_text(f"{avg:.1f}")
    
    # Actualizar contador de resets
    txt_resets.set_text(f"RESETS: {reset_count}")
    if reset_count > 0:
        txt_resets.set_color(COLORS["warning"])
    if reset_count >= MAX_RESETS_BEFORE_ERROR:
        txt_resets.set_color(COLORS["error"])
    
    # ========= MOSTRAR ERRORES PERSISTENTES DE SENSORES =========
    persistent_errors = [k.upper() for k, v in sensor_error_state.items() if v]
    if persistent_errors:
        txt_anomaly.set_text(f"! ERROR SENSOR: {', '.join(persistent_errors)} - Verifica conexión/sensor")
        txt_anomaly.set_color(COLORS["error"])
    elif range_errors and not anomalies_detected:
        # Mostrar aviso de valores fuera de rango (sin reset)
        sensor_names = {"temp": "TEMP", "hum": "HUM", "pres": "PRES", "alt": "ALT"}
        error_sensors = [sensor_names[k] for k in range_errors]
        txt_anomaly.set_text(f"! VALOR FUERA DE RANGO: {', '.join(error_sensors)}")
        txt_anomaly.set_color(COLORS["warning"])
    
    # ========= MANEJAR ANOMALÍAS DETECTADAS (CAMBIOS BRUSCOS) =========
    if anomalies_detected:
        sensor_names = {"temp": "TEMP", "hum": "HUM", "pres": "PRES", "alt": "ALT"}
        anomaly_sensors = [sensor_names[a["sensor"]] for a in anomalies_detected]
        
        # Solo resetear si no hemos alcanzado el máximo de resets
        if reset_count < MAX_RESETS_BEFORE_ERROR:
            txt_anomaly.set_text(f"! ANOMALIA: {', '.join(anomaly_sensors)} - REINICIANDO... ({reset_count+1}/{MAX_RESETS_BEFORE_ERROR})")
            txt_anomaly.set_color(COLORS["error"])
            
            # Ejecutar reset del Arduino
            reason = f"Anomalía en: {', '.join(anomaly_sensors)}"
            reset_arduino(ser, reason)
            
            # Limpiar últimos valores para evitar falsos positivos después del reset
            for key in last_values:
                last_values[key] = None
        else:
            txt_anomaly.set_text(f"! MAX RESETS ALCANZADO - Sensor defectuoso: {', '.join(anomaly_sensors)}")
            txt_anomaly.set_color(COLORS["error"])
            print(f"[ERROR] Máximo de resets alcanzado ({MAX_RESETS_BEFORE_ERROR}). No se reiniciará más.")


def export_graphs():
    """Exporta todas las gráficas como archivos PNG al cerrar el programa."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
    
    # Crear directorio de exportación si no existe
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    
    print(f"\n[EXPORT] Exportando gráficas a {export_dir}...")
    
    # Usar datos LIMPIOS para las gráficas finales
    t_list = list(t_clean) if t_clean else list(t_data)
    
    # 1. Exportar gráfica principal (dashboard completo)
    try:
        main_path = os.path.join(export_dir, f"dashboard_{timestamp}.png")
        fig.savefig(main_path, dpi=150, facecolor=COLORS["bg_dark"], 
                    edgecolor='none', bbox_inches='tight')
        print(f"  ✓ Dashboard completo: {main_path}")
    except Exception as e:
        print(f"  ✗ Error exportando dashboard: {e}")
    
    # 2. Crear gráficas individuales con datos LIMPIOS
    if len(t_clean) > 1:
        # Temperatura
        try:
            fig_temp, ax = plt.subplots(figsize=(10, 6))
            ax.set_facecolor(COLORS["bg_card"])
            fig_temp.patch.set_facecolor(COLORS["bg_dark"])
            ax.plot(list(t_clean), list(temp_clean), color=COLORS["temp"], linewidth=2)
            ax.fill_between(list(t_clean), list(temp_clean), alpha=0.2, color=COLORS["temp"])
            ax.set_title("Temperatura vs Tiempo (Datos Limpios)", color=COLORS["text_primary"], fontsize=14)
            ax.set_xlabel("Tiempo (s)", color=COLORS["text_secondary"])
            ax.set_ylabel("Temperatura (°C)", color=COLORS["text_secondary"])
            ax.tick_params(colors=COLORS["text_secondary"])
            ax.grid(True, alpha=0.3, color=COLORS["grid"])
            temp_path = os.path.join(export_dir, f"temperatura_{timestamp}.png")
            fig_temp.savefig(temp_path, dpi=150, facecolor=COLORS["bg_dark"], bbox_inches='tight')
            plt.close(fig_temp)
            print(f"  ✓ Temperatura: {temp_path}")
        except Exception as e:
            print(f"  ✗ Error exportando temperatura: {e}")
        
        # Humedad
        try:
            fig_hum, ax = plt.subplots(figsize=(10, 6))
            ax.set_facecolor(COLORS["bg_card"])
            fig_hum.patch.set_facecolor(COLORS["bg_dark"])
            ax.plot(list(t_clean), list(hum_clean), color=COLORS["hum"], linewidth=2)
            ax.fill_between(list(t_clean), list(hum_clean), alpha=0.2, color=COLORS["hum"])
            ax.set_title("Humedad vs Tiempo (Datos Limpios)", color=COLORS["text_primary"], fontsize=14)
            ax.set_xlabel("Tiempo (s)", color=COLORS["text_secondary"])
            ax.set_ylabel("Humedad (%)", color=COLORS["text_secondary"])
            ax.tick_params(colors=COLORS["text_secondary"])
            ax.grid(True, alpha=0.3, color=COLORS["grid"])
            hum_path = os.path.join(export_dir, f"humedad_{timestamp}.png")
            fig_hum.savefig(hum_path, dpi=150, facecolor=COLORS["bg_dark"], bbox_inches='tight')
            plt.close(fig_hum)
            print(f"  ✓ Humedad: {hum_path}")
        except Exception as e:
            print(f"  ✗ Error exportando humedad: {e}")
        
        # Presión
        try:
            fig_pres, ax = plt.subplots(figsize=(10, 6))
            ax.set_facecolor(COLORS["bg_card"])
            fig_pres.patch.set_facecolor(COLORS["bg_dark"])
            ax.plot(list(t_clean), list(pres_clean), color=COLORS["pres"], linewidth=2)
            ax.fill_between(list(t_clean), list(pres_clean), alpha=0.2, color=COLORS["pres"])
            ax.set_title("Presión vs Tiempo (Datos Limpios)", color=COLORS["text_primary"], fontsize=14)
            ax.set_xlabel("Tiempo (s)", color=COLORS["text_secondary"])
            ax.set_ylabel("Presión (hPa)", color=COLORS["text_secondary"])
            ax.tick_params(colors=COLORS["text_secondary"])
            ax.grid(True, alpha=0.3, color=COLORS["grid"])
            pres_path = os.path.join(export_dir, f"presion_{timestamp}.png")
            fig_pres.savefig(pres_path, dpi=150, facecolor=COLORS["bg_dark"], bbox_inches='tight')
            plt.close(fig_pres)
            print(f"  ✓ Presión: {pres_path}")
        except Exception as e:
            print(f"  ✗ Error exportando presión: {e}")
        
        # Altitud
        try:
            fig_alt, ax = plt.subplots(figsize=(10, 6))
            ax.set_facecolor(COLORS["bg_card"])
            fig_alt.patch.set_facecolor(COLORS["bg_dark"])
            ax.plot(list(t_clean), list(alt_clean), color=COLORS["alt"], linewidth=2)
            ax.fill_between(list(t_clean), list(alt_clean), alpha=0.2, color=COLORS["alt"])
            ax.set_title("Altitud vs Tiempo (Datos Limpios)", color=COLORS["text_primary"], fontsize=14)
            ax.set_xlabel("Tiempo (s)", color=COLORS["text_secondary"])
            ax.set_ylabel("Altitud (m)", color=COLORS["text_secondary"])
            ax.tick_params(colors=COLORS["text_secondary"])
            ax.grid(True, alpha=0.3, color=COLORS["grid"])
            alt_path = os.path.join(export_dir, f"altitud_{timestamp}.png")
            fig_alt.savefig(alt_path, dpi=150, facecolor=COLORS["bg_dark"], bbox_inches='tight')
            plt.close(fig_alt)
            print(f"  ✓ Altitud: {alt_path}")
        except Exception as e:
            print(f"  ✗ Error exportando altitud: {e}")
        
        # Temperatura vs Altitud
        try:
            fig_ta, ax = plt.subplots(figsize=(10, 6))
            ax.set_facecolor(COLORS["bg_card"])
            fig_ta.patch.set_facecolor(COLORS["bg_dark"])
            ax.plot(list(temp_clean), list(alt_clean), color=COLORS["alt"], linewidth=2, marker='o', markersize=3)
            ax.set_title("Temperatura vs Altitud (Datos Limpios)", color=COLORS["text_primary"], fontsize=14)
            ax.set_xlabel("Temperatura (°C)", color=COLORS["text_secondary"])
            ax.set_ylabel("Altitud (m)", color=COLORS["text_secondary"])
            ax.tick_params(colors=COLORS["text_secondary"])
            ax.grid(True, alpha=0.3, color=COLORS["grid"])
            ta_path = os.path.join(export_dir, f"temp_vs_altitud_{timestamp}.png")
            fig_ta.savefig(ta_path, dpi=150, facecolor=COLORS["bg_dark"], bbox_inches='tight')
            plt.close(fig_ta)
            print(f"  ✓ Temp vs Altitud: {ta_path}")
        except Exception as e:
            print(f"  ✗ Error exportando temp vs altitud: {e}")
    
    # 3. Exportar estadísticas a archivo de texto
    try:
        stats_path = os.path.join(export_dir, f"estadisticas_{timestamp}.txt")
        with open(stats_path, 'w', encoding='utf-8') as f:
            f.write("ESTADÍSTICAS DE LA SESIÓN - DATOS LIMPIOS\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Paquetes totales: {packet_count}\n")
            f.write(f"Datos limpios: {len(t_clean)}\n")
            f.write(f"Resets del Arduino: {reset_count}\n\n")
            
            for sensor, name, unit in [("temp", "Temperatura", "°C"), 
                                        ("hum", "Humedad", "%"),
                                        ("pres", "Presión", "hPa"),
                                        ("alt", "Altitud", "m")]:
                f.write(f"{name}:\n")
                if stats_clean[sensor]["count"] > 0:
                    avg = stats_clean[sensor]["sum"] / stats_clean[sensor]["count"]
                    f.write(f"  Mínimo: {stats_clean[sensor]['min']:.2f} {unit}\n")
                    f.write(f"  Máximo: {stats_clean[sensor]['max']:.2f} {unit}\n")
                    f.write(f"  Promedio: {avg:.2f} {unit}\n")
                    f.write(f"  Lecturas válidas: {stats_clean[sensor]['count']}\n")
                else:
                    f.write("  Sin datos válidos\n")
                f.write("\n")
        print(f"  ✓ Estadísticas: {stats_path}")
    except Exception as e:
        print(f"  ✗ Error exportando estadísticas: {e}")
    
    print(f"\n[EXPORT] Exportación completada en: {export_dir}")


# Animación
ani = FuncAnimation(fig, update, interval=100, cache_frame_data=False)

fig.subplots_adjust(left=0.06, right=0.98, top=0.95, bottom=0.06, hspace=0.4, wspace=0.35)

try:
    plt.show()
finally:
    # Exportar gráficas al cerrar
    export_graphs()
    # Cerrar conexión serial
    if ser.is_open:
        ser.close()
        print("[INFO] Conexión serial cerrada")

    # Ejecutar generador de reporte automáticamente
    print("\n[INFO] Generando reporte HTML post-misión...")
    try:
        import subprocess
        # Ejecutar generate_report.py
        subprocess.run(["python", "generate_report.py"], check=True)
        
        # Intentar abrir el reporte automáticamente (opcional, pero útil)
        report_path = os.path.abspath("report.html")
        print(f"[SUCCESS] Reporte generado: {report_path}")
        
        # Abrir en navegador
        if os.name == 'nt':  # Windows
            os.startfile(report_path)
        else:
            subprocess.run(["xdg-open", report_path])
            
    except Exception as e:
        print(f"[ERROR] No se pudo generar/abrir el reporte automáticmante: {e}")
