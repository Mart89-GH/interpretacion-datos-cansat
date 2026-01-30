# interpretador.py
# Interpretador de datos del CanSat con filtrado de anomalías y exportación
import re
import time
import os
from collections import deque
from math import radians, cos, sin, asin, sqrt
from datetime import datetime

import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ========= CONFIG =========
PORT = None  # Auto-detect
BAUD = 115200
WINDOW = 600  # puntos en ventana (p.ej. 600 ~ 10 min si 1 Hz)
READ_TIMEOUT = 1.0

# Rangos válidos (fuera de estos rangos = dato inválido, no se grafica)
BASELINE_ALTITUDE = 650.0
ALTITUDE_TOLERANCE = 500.0

VALID_RANGES = {
    "temp": (-40.0, 85.0),
    "hum": (0.0, 100.0),
    "pres": (300.0, 1100.0),
    "alt": (BASELINE_ALTITUDE - ALTITUDE_TOLERANCE, BASELINE_ALTITUDE + ALTITUDE_TOLERANCE),
}

# Acepta varias claves típicas (por si tu Arduino usa nombres distintos)
KEYMAP = {
    "temp": {"temp", "t", "temperature"},
    "hum": {"hum", "h", "humidity"},
    "pres": {"pres", "p", "pressure"},
    "alt": {"alt", "altitude", "height"},
    "lat": {"lat", "latitude"},
    "lon": {"lon", "lng", "long", "longitude"},
}


# ========= UTILS =========
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


def haversine_m(lat1, lon1, lat2, lon2):
    # distancia en metros
    R = 6371000.0
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return R * c


def parse_line(line: str):
    # Parsea pares key=value con float (permite - y .)
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


def is_value_valid(key, value):
    """Verifica si un valor está en rango válido."""
    if value is None or value != value:  # NaN check
        return False
    if key in VALID_RANGES:
        min_val, max_val = VALID_RANGES[key]
        return min_val <= value <= max_val
    return True


# ========= DATA BUFFERS =========
# Datos RAW (todos)
t_raw = deque(maxlen=WINDOW)
temp_raw = deque(maxlen=WINDOW)
hum_raw = deque(maxlen=WINDOW)
pres_raw = deque(maxlen=WINDOW)
alt_raw = deque(maxlen=WINDOW)

# Datos LIMPIOS (solo válidos)
t_clean = deque(maxlen=WINDOW)
temp_clean = deque(maxlen=WINDOW)
hum_clean = deque(maxlen=WINDOW)
pres_clean = deque(maxlen=WINDOW)
alt_clean = deque(maxlen=WINDOW)

lat = deque(maxlen=WINDOW)
lon = deque(maxlen=WINDOW)
speed = deque(maxlen=WINDOW)  # m/s (desde GPS)
speed_alt = deque(maxlen=WINDOW)  # para scatter velocidad-altura

last_gps = {"lat": None, "lon": None, "time": None}

# Contadores
packet_count = 0
valid_count = 0
invalid_count = 0


# ========= SERIAL =========
PORT = find_arduino_port()
if PORT is None:
    print("[ERROR] No se encontró Arduino. Conecta el dispositivo.")
    exit(1)

ser = serial.Serial(PORT, BAUD, timeout=READ_TIMEOUT)
print(f"[INFO] Conectado a {PORT}")
time.sleep(2)


# ========= FIGURES (independientes) =========
def make_fig(title, y_label, color='#1f77b4'):
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#16213e')
    ax.set_title(title, color='white', fontsize=14)
    ax.set_xlabel("Tiempo (s)", color='#cccccc')
    ax.set_ylabel(y_label, color='#cccccc')
    ax.tick_params(colors='#cccccc')
    ax.grid(True, alpha=0.3, color='#444')
    (ln,) = ax.plot([], [], linewidth=2, color=color)
    return fig, ax, ln


figT, axT, lnT = make_fig("Temperatura (Datos Limpios)", "°C", '#ff6b6b')
figH, axH, lnH = make_fig("Humedad (Datos Limpios)", "%", '#4ecdc4')
figP, axP, lnP = make_fig("Presión (Datos Limpios)", "hPa", '#ffd93d')
figA, axA, lnA = make_fig("Altitud (Datos Limpios)", "m", '#6c5ce7')

t0 = time.monotonic()


def update(_frame):
    global packet_count, valid_count, invalid_count
    
    # 1) leer una línea
    try:
        raw = ser.readline().decode("utf-8", errors="ignore").strip()
    except Exception:
        return

    if not raw:
        return
    
    # Ignorar mensajes de info/error
    if "info=" in raw.lower() or "error=" in raw.lower() or "warning=" in raw.lower():
        return

    d = parse_line(raw)
    if not d:
        return

    packet_count += 1
    now = time.monotonic() - t0
    t_raw.append(now)

    # 2) push valores RAW
    def push_raw(buf, key):
        if key in d:
            buf.append(d[key])
        else:
            buf.append(buf[-1] if len(buf) else float("nan"))

    push_raw(temp_raw, "temp")
    push_raw(hum_raw, "hum")
    push_raw(pres_raw, "pres")
    push_raw(alt_raw, "alt")
    push_raw(lat, "lat")
    push_raw(lon, "lon")

    # 3) Verificar si TODOS los valores principales son válidos
    all_valid = True
    for key in ["temp", "hum", "pres", "alt"]:
        if key in d:
            if not is_value_valid(key, d[key]):
                all_valid = False
                print(f"[FILTERED] {key.upper()}={d[key]:.1f} fuera de rango")
                break

    # 4) Push a buffers LIMPIOS solo si todo es válido
    if all_valid:
        valid_count += 1
        t_clean.append(now)
        if "temp" in d: temp_clean.append(d["temp"])
        if "hum" in d: hum_clean.append(d["hum"])
        if "pres" in d: pres_clean.append(d["pres"])
        if "alt" in d: alt_clean.append(d["alt"])
    else:
        invalid_count += 1

    # 5) GPS speed calculation
    cur_lat = d.get("lat", None)
    cur_lon = d.get("lon", None)
    cur_time = now

    v = float("nan")
    if cur_lat is not None and cur_lon is not None:
        if last_gps["lat"] is not None and last_gps["lon"] is not None and last_gps["time"] is not None:
            dt = cur_time - last_gps["time"]
            if dt > 0.05:
                dist = haversine_m(last_gps["lat"], last_gps["lon"], cur_lat, cur_lon)
                v = dist / dt
        last_gps.update({"lat": cur_lat, "lon": cur_lon, "time": cur_time})

    speed.append(v)

    # 6) actualizar plots con datos LIMPIOS
    def set_line(ax, ln, t_buf, ybuf):
        if len(t_buf) < 2:
            return
        ln.set_data(list(t_buf), list(ybuf))
        ax.relim()
        ax.autoscale_view()

    set_line(axT, lnT, t_clean, temp_clean)
    set_line(axH, lnH, t_clean, hum_clean)
    set_line(axP, lnP, t_clean, pres_clean)
    set_line(axA, lnA, t_clean, alt_clean)


def export_graphs():
    """Exporta las gráficas al cerrar el programa."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
    
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    
    print(f"\n[EXPORT] Exportando gráficas a {export_dir}...")
    print(f"  Paquetes totales: {packet_count}")
    print(f"  Datos válidos: {valid_count}")
    print(f"  Datos filtrados: {invalid_count}")
    
    try:
        figT.savefig(os.path.join(export_dir, f"interp_temperatura_{timestamp}.png"), 
                     dpi=150, facecolor='#1a1a2e', bbox_inches='tight')
        print(f"  ✓ Temperatura exportada")
    except: pass
    
    try:
        figH.savefig(os.path.join(export_dir, f"interp_humedad_{timestamp}.png"), 
                     dpi=150, facecolor='#1a1a2e', bbox_inches='tight')
        print(f"  ✓ Humedad exportada")
    except: pass
    
    try:
        figP.savefig(os.path.join(export_dir, f"interp_presion_{timestamp}.png"), 
                     dpi=150, facecolor='#1a1a2e', bbox_inches='tight')
        print(f"  ✓ Presión exportada")
    except: pass
    
    try:
        figA.savefig(os.path.join(export_dir, f"interp_altitud_{timestamp}.png"), 
                     dpi=150, facecolor='#1a1a2e', bbox_inches='tight')
        print(f"  ✓ Altitud exportada")
    except: pass
    
    print(f"\n[EXPORT] Completado en: {export_dir}")


# Animación
ani_T = FuncAnimation(figT, update, interval=200, cache_frame_data=False)
ani_H = FuncAnimation(figH, update, interval=200, cache_frame_data=False)
ani_P = FuncAnimation(figP, update, interval=200, cache_frame_data=False)
ani_A = FuncAnimation(figA, update, interval=200, cache_frame_data=False)

try:
    plt.show()
finally:
    export_graphs()
    if ser.is_open:
        ser.close()
        print("[INFO] Conexión serial cerrada")