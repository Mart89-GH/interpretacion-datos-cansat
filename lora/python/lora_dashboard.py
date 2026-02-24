# lora_dashboard.py
# Dashboard profesional para datos LoRa - CanSat Espana 2026
# Lee serial del receptor LoRa y muestra graficas en tiempo real
# Datos: CANSAT,id,temp,presion,altitud,humedad,timestamp + RSSI + SNR

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
import matplotlib.patheffects as path_effects
import os
import csv

# ========= CONFIG =========
PORT = "COM18"  # Puerto del Arduino receptor (cambiar si es diferente)
BAUD = 9600
WINDOW = 200  # Puntos de datos en pantalla
READ_TIMEOUT = 0.1  # Timeout corto para no bloquear la UI

# ========= PALETA DE COLORES =========
COLORS = {
    "bg_dark": "#0a0e17",
    "bg_panel": "#111827",
    "bg_card": "#1a2233",
    "temp": "#ff6b6b",
    "temp_light": "#ff8787",
    "pres": "#ffd93d",
    "pres_light": "#ffe066",
    "alt": "#6c5ce7",
    "alt_light": "#a29bfe",
    "hum": "#00cec9",
    "hum_light": "#55efc4",
    "rssi": "#fd79a8",
    "rssi_light": "#fdcb6e",
    "snr": "#74b9ff",
    "snr_light": "#81ecec",
    "text_primary": "#f0f6fc",
    "text_secondary": "#8b949e",
    "success": "#3fb950",
    "warning": "#d29922",
    "error": "#f85149",
    "grid": "#30363d",
}

# ========= DATA BUFFERS =========
t_data = deque(maxlen=WINDOW)
temp_data = deque(maxlen=WINDOW)
pres_data = deque(maxlen=WINDOW)
alt_data = deque(maxlen=WINDOW)
hum_data = deque(maxlen=WINDOW)
rssi_data = deque(maxlen=WINDOW)
snr_data = deque(maxlen=WINDOW)

stats = {}
for k in ["temp", "pres", "alt", "hum", "rssi", "snr"]:
    stats[k] = {"min": float("inf"), "max": float("-inf"), "sum": 0, "count": 0}

packet_count = 0
last_packet_time = time.monotonic()
data_rate = 0.0

# Estado del parseo: guardamos RSSI/SNR hasta que llegue la linea CANSAT
current_rssi = None
current_snr = None

# ========= SERIAL =========
def find_port():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "Arduino" in p.description or "USB" in p.description:
            return p.device
    return None

if PORT is None:
    PORT = find_port()
if PORT is None:
    print("[ERROR] No se encontro Arduino. Conecta el dispositivo.")
    exit(1)

ser = serial.Serial(PORT, BAUD, timeout=READ_TIMEOUT)
print(f"[INFO] Conectado a {PORT} @ {BAUD} baud")
time.sleep(2)
ser.reset_input_buffer()

# ========= CSV =========
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
CSV_FILE = os.path.join(DATA_DIR, "lora_data.csv")

with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerow([
        "timestamp", "packet_id", "type", "temperature_C", "pressure_hPa",
        "altitude_m", "humidity_%", "arduino_ms", "rssi_dBm", "snr_dB",
        "q0", "q1", "q2", "q3", "acc_x", "acc_y", "acc_z", "pos_x", "pos_y", "pos_z"
    ])
print(f"[INFO] CSV: {CSV_FILE}")


def log_csv(d):
    try:
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            w.writerow([ts, d.get("id",""), d.get("type","PRI"), d.get("temp",""), d.get("pres",""),
                        d.get("alt",""), d.get("hum",""), d.get("ms",""),
                        d.get("rssi",""), d.get("snr",""),
                        d.get("q0",""), d.get("q1",""), d.get("q2",""), d.get("q3",""),
                        d.get("ax",""), d.get("ay",""), d.get("az",""),
                        d.get("px",""), d.get("py",""), d.get("pz","")])
    except Exception as e:
        print(f"[CSV ERR] {e}")


def update_stat(key, val):
    if val is None or np.isnan(val):
        return
    stats[key]["min"] = min(stats[key]["min"], val)
    stats[key]["max"] = max(stats[key]["max"], val)
    stats[key]["sum"] += val
    stats[key]["count"] += 1


def get_avg(key):
    if stats[key]["count"] == 0:
        return 0
    return stats[key]["sum"] / stats[key]["count"]


# ========= MATPLOTLIB =========
plt.style.use('dark_background')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans']
plt.rcParams['font.size'] = 10

fig = plt.figure(figsize=(16, 10))
fig.patch.set_facecolor(COLORS["bg_dark"])
fig.canvas.manager.set_window_title("CanSat LoRa Dashboard")

gs = gridspec.GridSpec(4, 2, figure=fig,
                       height_ratios=[0.35, 1, 1, 1],
                       hspace=0.45, wspace=0.3)

# Header
ax_hdr = fig.add_subplot(gs[0, :])
ax_hdr.set_facecolor(COLORS["bg_panel"])
ax_hdr.axis('off')

title = ax_hdr.text(0.5, 0.78, "CANSAT LORA MISSION DASHBOARD",
                    fontsize=20, fontweight='bold', color=COLORS["text_primary"],
                    ha='center', va='center', transform=ax_hdr.transAxes)
title.set_path_effects([path_effects.withStroke(linewidth=2, foreground=COLORS["bg_dark"])])

ax_hdr.text(0.5, 0.48, "Temp | Presion | Altitud | Humedad | RSSI | SNR",
            fontsize=10, color=COLORS["text_secondary"],
            ha='center', va='center', transform=ax_hdr.transAxes)

def hdr_text(x, txt):
    return ax_hdr.text(x, 0.12, txt, fontsize=10, fontweight='bold',
                       color=COLORS["text_secondary"], ha='center', va='center',
                       transform=ax_hdr.transAxes, family='monospace')

txt_time = hdr_text(0.10, "TIME: 00:00:00")
txt_pkts = hdr_text(0.30, "PKT: 0")
txt_rate = hdr_text(0.48, "RATE: 0.0 Hz")
txt_sig  = hdr_text(0.66, "SIGNAL: --")
txt_conn = ax_hdr.text(0.88, 0.12, f"CONNECTED ({PORT})", fontsize=10,
                       fontweight='bold', color=COLORS["success"],
                       ha='center', va='center', transform=ax_hdr.transAxes)

# Subplots
ax_temp = fig.add_subplot(gs[1, 0])
ax_pres = fig.add_subplot(gs[1, 1])
ax_alt  = fig.add_subplot(gs[2, 0])
ax_hum  = fig.add_subplot(gs[2, 1])
ax_rssi = fig.add_subplot(gs[3, 0])
ax_snr  = fig.add_subplot(gs[3, 1])

def style(ax, titulo, ylabel, color):
    ax.set_facecolor(COLORS["bg_card"])
    ax.set_title(titulo, fontsize=12, fontweight='bold', color=color, pad=10, loc='left')
    ax.set_xlabel("Tiempo (s)", fontsize=9, color=COLORS["text_secondary"], labelpad=6)
    ax.set_ylabel(ylabel, fontsize=9, color=COLORS["text_secondary"], labelpad=6)
    ax.tick_params(colors=COLORS["text_secondary"], labelsize=8)
    ax.grid(True, alpha=0.25, color=COLORS["grid"], linestyle='--', linewidth=0.5)
    for s in ax.spines.values():
        s.set_color(COLORS["grid"])
        s.set_linewidth(0.5)

style(ax_temp, "TEMPERATURA", "C", COLORS["temp"])
style(ax_pres, "PRESION", "hPa", COLORS["pres"])
style(ax_alt,  "ALTITUD", "m", COLORS["alt"])
style(ax_hum,  "HUMEDAD", "%", COLORS["hum"])
style(ax_rssi, "RSSI", "dBm", COLORS["rssi"])
style(ax_snr,  "SNR", "dB", COLORS["snr"])

# Lines
ln_temp, = ax_temp.plot([], [], color=COLORS["temp"], lw=2, alpha=0.95)
ln_pres, = ax_pres.plot([], [], color=COLORS["pres"], lw=2, alpha=0.95)
ln_alt,  = ax_alt.plot([], [], color=COLORS["alt"], lw=2, alpha=0.95)
ln_hum,  = ax_hum.plot([], [], color=COLORS["hum"], lw=2, alpha=0.95)
ln_rssi, = ax_rssi.plot([], [], color=COLORS["rssi"], lw=2, alpha=0.95)
ln_snr,  = ax_snr.plot([], [], color=COLORS["snr"], lw=2, alpha=0.95)

# Big value overlays
def big_val(ax, col, border):
    return ax.text(0.97, 0.92, "--", fontsize=20, fontweight='bold',
                   color=col, ha='right', va='top', transform=ax.transAxes,
                   family='monospace',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["bg_panel"],
                            edgecolor=border, alpha=0.85))

tv_temp = big_val(ax_temp, COLORS["temp_light"], COLORS["temp"])
tv_pres = big_val(ax_pres, COLORS["pres_light"], COLORS["pres"])
tv_alt  = big_val(ax_alt, COLORS["alt_light"], COLORS["alt"])
tv_hum  = big_val(ax_hum, COLORS["hum_light"], COLORS["hum"])
tv_rssi = big_val(ax_rssi, COLORS["rssi_light"], COLORS["rssi"])
tv_snr  = big_val(ax_snr, COLORS["snr_light"], COLORS["snr"])

# Mini stats
def mini_stat(ax):
    return ax.text(0.03, 0.92, "", fontsize=7.5, color=COLORS["text_secondary"],
                   ha='left', va='top', transform=ax.transAxes, family='monospace',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor=COLORS["bg_panel"], alpha=0.7))

ms_temp = mini_stat(ax_temp)
ms_pres = mini_stat(ax_pres)
ms_alt  = mini_stat(ax_alt)
ms_hum  = mini_stat(ax_hum)
ms_rssi = mini_stat(ax_rssi)
ms_snr  = mini_stat(ax_snr)

t0 = time.monotonic()

# ========= PARSEO SERIAL =========
def process_line(raw):
    """Procesa una linea del serial. Retorna dict si es un paquete CANSAT, None si no."""
    global current_rssi, current_snr
    
    line = raw.strip()
    if not line:
        return None
    
    # Capturar RSSI (formato: "RSSI: -XX.X")
    m = re.match(r"RSSI:\s*([-+]?\d+\.?\d*)", line)
    if m:
        current_rssi = float(m.group(1))
        return None
    
    # Capturar SNR (formato: "SNR: X.X")
    m = re.match(r"SNR:\s*([-+]?\d+\.?\d*)", line)
    if m:
        current_snr = float(m.group(1))
        return None
    
    # Capturar datos CANSAT (formato: "CANSAT,id,temp,pres,alt,hum,ms")
    if line.startswith("CANSAT,"):
        parts = line.split(",")
        if len(parts) >= 6:
            try:
                # Si no tenemos RSSI/SNR (estamos conectados al emisor), usar NaN
                rssi_val = current_rssi if current_rssi is not None else float("nan")
                snr_val = current_snr if current_snr is not None else float("nan")
                
                d = {
                    "type": "PRI",
                    "id": int(parts[1]),
                    "temp": float(parts[2]),
                    "pres": float(parts[3]),
                    "alt": float(parts[4]),
                    "hum": float(parts[5]),
                    "ms": int(parts[6]) if len(parts) > 6 else 0,
                    "rssi": rssi_val,
                    "snr": snr_val,
                }
                return d
            except (ValueError, IndexError):
                pass
                
    # Capturar datos CANSAT SECUNDARIA (formato: "CANSAT_SEC,id,ms,q0,q1,q2,q3,ax,ay,az,px,py,pz")
    if line.startswith("CANSAT_SEC,"):
        parts = line.split(",")
        if len(parts) >= 13:
            try:
                rssi_val = current_rssi if current_rssi is not None else float("nan")
                snr_val = current_snr if current_snr is not None else float("nan")
                
                d = {
                    "type": "SEC",
                    "id": int(parts[1]),
                    "ms": int(parts[2]),
                    "q0": float(parts[3]),
                    "q1": float(parts[4]),
                    "q2": float(parts[5]),
                    "q3": float(parts[6]),
                    "ax": float(parts[7]),
                    "ay": float(parts[8]),
                    "az": float(parts[9]),
                    "px": float(parts[10]),
                    "py": float(parts[11]),
                    "pz": float(parts[12]),
                    "rssi": rssi_val,
                    "snr": snr_val,
                }
                return d
            except (ValueError, IndexError):
                pass
    
    return None


# ========= ANIMATION UPDATE =========
def update(_frame):
    global packet_count, last_packet_time, data_rate
    
    # Leer TODAS las lineas disponibles en el buffer serial
    lines_processed = 0
    latest_data = None
    
    while ser.in_waiting > 0 and lines_processed < 20:
        try:
            raw = ser.readline().decode("utf-8", errors="ignore").strip()
        except Exception:
            break
        
        if not raw:
            continue
        
        lines_processed += 1
        
        # Imprimir todo lo que llega del serial (debug)
        print(f"[SER] {raw}")
        
        d = process_line(raw)
        if d is not None:
            latest_data = d
            
            # Actualizar contadores
            packet_count += 1
            now_mono = time.monotonic()
            if now_mono - last_packet_time > 0:
                data_rate = 0.7 * data_rate + 0.3 * (1.0 / (now_mono - last_packet_time))
            last_packet_time = now_mono
            
            now = now_mono - t0
            
            # CSV
            log_csv(d)
            
            if d.get("type", "PRI") == "PRI":
                # Buffers solo para la misión primaria
                t_data.append(now)
                for buf, key in [(temp_data,"temp"),(pres_data,"pres"),(alt_data,"alt"),
                                 (hum_data,"hum"),(rssi_data,"rssi"),(snr_data,"snr")]:
                    val = d.get(key, float("nan"))
                    if val is not None and not np.isnan(val):
                        buf.append(val)
                        update_stat(key, val)
                    else:
                        buf.append(buf[-1] if len(buf) else 0)
                
                print(f"[PKT #{d['id']}] T={d.get('temp',0):.1f}C P={d.get('pres',0):.0f}hPa "
                      f"A={d.get('alt',0):.1f}m RSSI={d.get('rssi','?')} SNR={d.get('snr','?')}")
            else:
                # Misión secundaria
                print(f"[PKT_SEC #{d.get('id','?')}] Pos=[{d.get('px',0):.1f}, {d.get('py',0):.1f}, {d.get('pz',0):.1f}]m "
                      f"Acc=[{d.get('ax',0):.2f}, {d.get('ay',0):.2f}, {d.get('az',0):.2f}]g "
                      f"RSSI={d.get('rssi','?')} SNR={d.get('snr','?')}")
    
    # Actualizar graficas solo si hay datos
    if len(t_data) < 2:
        return
    
    t_list = list(t_data)
    
    # Lineas
    ln_temp.set_data(t_list, list(temp_data))
    ln_pres.set_data(t_list, list(pres_data))
    ln_alt.set_data(t_list, list(alt_data))
    ln_hum.set_data(t_list, list(hum_data))
    ln_rssi.set_data(t_list, list(rssi_data))
    ln_snr.set_data(t_list, list(snr_data))
    
    # Fill
    for ax, buf, col in [(ax_temp, list(temp_data), COLORS["temp"]),
                         (ax_pres, list(pres_data), COLORS["pres"]),
                         (ax_alt, list(alt_data), COLORS["alt"]),
                         (ax_hum, list(hum_data), COLORS["hum"]),
                         (ax_rssi, list(rssi_data), COLORS["rssi"]),
                         (ax_snr, list(snr_data), COLORS["snr"])]:
        for c in ax.collections[:]:
            c.remove()
        if len(t_list) > 1:
            ax.fill_between(t_list, buf, alpha=0.12, color=col)
    
    # Auto-scale
    for ax in [ax_temp, ax_pres, ax_alt, ax_hum, ax_rssi, ax_snr]:
        ax.relim()
        ax.autoscale_view()
    
    # Header
    now = time.monotonic() - t0
    h, rem = divmod(int(now), 3600)
    m, s = divmod(rem, 60)
    txt_time.set_text(f"TIME: {h:02d}:{m:02d}:{s:02d}")
    txt_pkts.set_text(f"PKT: {packet_count}")
    txt_rate.set_text(f"RATE: {data_rate:.1f} Hz")
    
    # Signal quality
    if rssi_data and not np.isnan(rssi_data[-1]):
        r = rssi_data[-1]
        if r > -70:
            txt_sig.set_text("SIGNAL: EXCELENTE")
            txt_sig.set_color(COLORS["success"])
        elif r > -85:
            txt_sig.set_text("SIGNAL: BUENA")
            txt_sig.set_color(COLORS["success"])
        elif r > -100:
            txt_sig.set_text("SIGNAL: ACEPTABLE")
            txt_sig.set_color(COLORS["warning"])
        else:
            txt_sig.set_text("SIGNAL: DEBIL")
            txt_sig.set_color(COLORS["error"])
    
    # Big values
    if temp_data: tv_temp.set_text(f"{temp_data[-1]:.1f}C")
    if pres_data: tv_pres.set_text(f"{pres_data[-1]:.0f}")
    if alt_data:  tv_alt.set_text(f"{alt_data[-1]:.1f}m")
    if hum_data:  tv_hum.set_text(f"{hum_data[-1]:.1f}%")
    if rssi_data and not np.isnan(rssi_data[-1]): tv_rssi.set_text(f"{rssi_data[-1]:.0f}")
    if snr_data and not np.isnan(snr_data[-1]):  tv_snr.set_text(f"{snr_data[-1]:.1f}")
    
    # Mini stats
    def fmt(k):
        if stats[k]["count"] > 0:
            return f"Min:{stats[k]['min']:.1f}\nAvg:{get_avg(k):.1f}\nMax:{stats[k]['max']:.1f}"
        return ""
    
    ms_temp.set_text(fmt("temp"))
    ms_pres.set_text(fmt("pres"))
    ms_alt.set_text(fmt("alt"))
    ms_hum.set_text(fmt("hum"))
    ms_rssi.set_text(fmt("rssi"))
    ms_snr.set_text(fmt("snr"))


# ========= MAIN =========
print("\n" + "=" * 55)
print("  CANSAT LORA DASHBOARD")
print("  Temp | Presion | Altitud | Humedad | RSSI | SNR")
print("  (Cerrar ventana para guardar datos)")
print("=" * 55 + "\n")

ani = FuncAnimation(fig, update, interval=200, cache_frame_data=False)
plt.tight_layout()
plt.show()

print(f"\n[INFO] Sesion terminada. Datos guardados en: {CSV_FILE}")
print(f"[INFO] Total paquetes: {packet_count}")
print(f"[INFO] Para generar report: py generate_lora_report.py")
