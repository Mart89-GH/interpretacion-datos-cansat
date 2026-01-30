import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import time
import csv
import os
import re
from datetime import datetime
from collections import deque

# ========= CONFIG =========
PORT = None  # Auto-detect
BAUD = 115200
WINDOW = 120
CSV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "mq2_data.csv")

# ========= COLORES =========
COLORS = {
    "bg": "#121212",
    "card": "#1e1e1e",
    "text": "#ffffff",
    "safe": "#4caf50",    # Green
    "warn": "#ffeb3b",    # Yellow
    "danger": "#f44336",  # Red
    "line": "#03a9f4"     # Blue
}

# ========= CSV INIT =========
# Reiniciar CSV en cada sesión
with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "gas_raw", "pollution_percent"])
print(f"[INFO] CSV reiniciado: {CSV_FILE}")

def log_to_csv(data):
    try:
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                data.get("gas_raw", ""),
                data.get("pollution_percent", "")
            ])
    except Exception:
        pass

# ========= SERIAL CONNECTION =========
def find_port():
    print("[DEBUG] Buscando puertos disponibles...")
    ports = serial.tools.list_ports.comports()
    for p in ports:
        print(f"  - Encontrado: {p.device} | {p.description}")
        if "Arduino" in p.description or "USB" in p.description:
            return p.device
    # Fallbacks
    for p in ports:
        if p.device in ["COM5", "COM6", "COM9"]:
            print(f"  - Usando fallback conocido: {p.device}")
            return p.device
    return None

PORT = find_port()
if not PORT:
    print("[ERROR] No Arduino found. Please connect it.")
    input("Presiona ENTER para salir...") # Pausa para que el usuario vea el error
    exit()

print(f"Connecting to {PORT}...")
try:
    ser = serial.Serial(PORT, BAUD, timeout=1.0)
    time.sleep(2)
except Exception as e:
    print(f"Error connecting: {e}")
    exit()

# ========= DATA =========
t_data = deque(maxlen=WINDOW)
val_data = deque(maxlen=WINDOW)
start_time = time.time()

# ========= PLOT SETUP =========
plt.style.use('dark_background')
fig = plt.figure(figsize=(12, 8))
fig.patch.set_facecolor(COLORS["bg"])

# Layout: High value on top, graph on bottom
gs = fig.add_gridspec(2, 1, height_ratios=[1, 2])
ax_gauge = fig.add_subplot(gs[0])
ax_graph = fig.add_subplot(gs[1])

# Styling
for ax in [ax_gauge, ax_graph]:
    ax.set_facecolor(COLORS["card"])

ax_gauge.axis('off')
ax_graph.set_title("HISTORIAL DE CONTAMINACIÓN", color=COLORS["text"], fontsize=14, pad=10)
ax_graph.set_xlabel("Tiempo (s)", color=COLORS["text"])
ax_graph.set_ylabel("Nivel (%)", color=COLORS["text"])
ax_graph.grid(True, alpha=0.2)

# Line object
line, = ax_graph.plot([], [], color=COLORS["line"], linewidth=2)
fill = ax_graph.fill_between([], [], color=COLORS["line"], alpha=0.2)

# Text objects for gauge
txt_status = ax_gauge.text(0.5, 0.7, "CALIDAD DEL AIRE", ha='center', fontsize=20, color=COLORS["text"])
txt_value = ax_gauge.text(0.5, 0.4, "-- %", ha='center', fontsize=60, fontweight='bold', color=COLORS["text"])
txt_desc = ax_gauge.text(0.5, 0.15, "ESPERANDO DATOS...", ha='center', fontsize=16, color="#888")

def get_status_color(perc):
    if perc < 30: return COLORS["safe"], "BUENA"
    if perc < 60: return COLORS["warn"], "MODERADA"
    return COLORS["danger"], "PELIGROSA"

def update(frame):
    try:
        # Leer todo lo que hay en el buffer
        if ser.in_waiting > 0:
            line_raw = ser.readline().decode('utf-8', errors='ignore').strip()
            # print(f"[DEBUG] Raw: {line_raw}") # Descomentar si es necesario ver todo
            
            if not line_raw: return
            
            # Parse "gas_raw=123,pollution_percent=45"
            parts = re.findall(r"([a-z_]+)=([\d\.]+)", line_raw)
            if not parts:
                if "MQ-2" not in line_raw: # Ignorar mensaje de inicio
                    print(f"[DEBUG] Línea no reconocida: {line_raw}")
                return

            data = {k: float(v) for k, v in parts}
            print(f"[DATA] {data}")
            
            if "pollution_percent" in data:
                val = data["pollution_percent"]
                now = time.time() - start_time
                
                t_data.append(now)
                val_data.append(val)
                log_to_csv(data)
                
                # Update Graph
                line.set_data(t_data, val_data)
                # Safely clear collections
                for c in ax_graph.collections:
                    c.remove()
                ax_graph.fill_between(t_data, val_data, alpha=0.2, color=COLORS["line"])
                
                ax_graph.relim()
                ax_graph.autoscale_view()
                
                # Update Gauge
                color, status = get_status_color(val)
                txt_value.set_text(f"{val:.1f}%")
                txt_value.set_color(color)
                txt_desc.set_text(status)
                txt_desc.set_color(color)
                
                fig.patch.set_edgecolor(color)
                fig.patch.set_linewidth(5)
            
    except Exception as e:
        print(f"[ERROR] En update: {e}")

ani = FuncAnimation(fig, update, interval=100)

try:
    plt.show()
finally:
    if ser.is_open: ser.close()
    print("Closed.")
