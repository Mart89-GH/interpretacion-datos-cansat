# ============================================================================
# OV7670 FIRE DETECTION & VEGETATION ANALYSIS DASHBOARD
# ============================================================================
#
# Dashboard profesional para visualización en tiempo real de datos del sistema
# OV7670 de detección de incendios y análisis de vegetación para CanSat.
#
# Características:
# - Visualización en tiempo real del Fire Detection Index (FDI)
# - Gráficas de clasificación de terreno
# - Monitoreo de índices de vegetación (ExG, VARI, GRVI, NGBDI)
# - Sistema de alertas visuales y sonoras
# - Exportación de datos a CSV
# - Generación automática de reportes
#
# Autor: CanSat Team
# Fecha: Enero 2026
# ============================================================================

import os
import re
import sys
import time
import csv
import subprocess
from datetime import datetime
from collections import deque

import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.patches import Rectangle, FancyBboxPatch, Circle
from matplotlib.collections import PatchCollection
import matplotlib.gridspec as gridspec

import serial
import serial.tools.list_ports

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# Directorio base
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")

# Crear directorios si no existen
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

# Archivos de datos
CSV_FILE = os.path.join(DATA_DIR, "ov7670_data.csv")

# Configuración Serial
BAUD_RATE = 115200
SERIAL_TIMEOUT = 1

# Tamaño del buffer de datos (últimos N puntos)
BUFFER_SIZE = 300

# Niveles de riesgo
RISK_LEVELS = {
    0: ("SIN RIESGO", "#3fb950", "🟢"),
    1: ("BAJO", "#d29922", "🟡"),
    2: ("MODERADO", "#f0883e", "🟠"),
    3: ("ALTO", "#f85149", "🔴"),
    4: ("CRÍTICO", "#ff0000", "🔥")
}

# ============================================================================
# PALETA DE COLORES PROFESIONAL
# ============================================================================

COLORS = {
    # Fondos
    "bg_dark": "#0d1117",
    "bg_panel": "#161b22",
    "bg_card": "#21262d",
    
    # Terrenos
    "sky": "#87CEEB",
    "cloud": "#E0E0E0",
    "vegetation": "#228B22",
    "dry_veg": "#DAA520",
    "bare_soil": "#8B4513",
    "water": "#1E90FF",
    "smoke": "#808080",
    "fire": "#FF4500",
    "burned": "#2F2F2F",
    "urban": "#696969",
    
    # Índices
    "fdi": "#FF6347",
    "exg": "#32CD32",
    "vari": "#00CED1",
    "health": "#98FB98",
    
    # Texto
    "text": "#E6EDF3",
    "text_secondary": "#8B949E",
    "text_muted": "#484f58",
    
    # Estados
    "success": "#3fb950",
    "warning": "#d29922",
    "error": "#f85149",
    
    # Grid
    "grid": "#30363d",
    "border": "#21262d",
}

# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def find_arduino_port():
    """Detecta automáticamente el puerto del Arduino."""
    ports = serial.tools.list_ports.comports()
    
    for port in ports:
        desc = (port.description or "").lower()
        hwid = (port.hwid or "").lower()
        
        # Arduino R4 WiFi específico
        if "2341" in hwid and "1002" in hwid:
            print(f"[INFO] Arduino R4 WiFi detectado en {port.device}")
            return port.device
        
        # Otros Arduinos
        if "arduino" in desc or "ch340" in desc or "cp210" in desc:
            print(f"[INFO] Arduino detectado en {port.device}")
            return port.device
    
    # Listar puertos disponibles
    print("[WARNING] No se detectó Arduino automáticamente.")
    print("Puertos disponibles:")
    for port in ports:
        print(f"  - {port.device}: {port.description}")
    
    if ports:
        return ports[0].device
    return None


def parse_terrain_line(line):
    """Parsea línea de datos de terreno."""
    data = {}
    if not line.startswith("terrain="):
        return data
    
    content = line[8:]  # Quitar "terrain="
    pairs = content.split(",")
    
    for pair in pairs:
        if ":" in pair:
            key, value = pair.split(":", 1)
            try:
                data[key.strip()] = float(value.strip())
            except ValueError:
                pass
    
    return data


def parse_fire_line(line):
    """Parsea línea de datos de fuego."""
    data = {}
    if not line.startswith("fire="):
        return data
    
    content = line[5:]  # Quitar "fire="
    pairs = content.split(",")
    
    for pair in pairs:
        if ":" in pair:
            key, value = pair.split(":", 1)
            try:
                data[key.strip()] = float(value.strip())
            except ValueError:
                pass
    
    return data


def parse_veg_line(line):
    """Parsea línea de datos de vegetación."""
    data = {}
    if not line.startswith("veg="):
        return data
    
    content = line[4:]  # Quitar "veg="
    pairs = content.split(",")
    
    for pair in pairs:
        if ":" in pair:
            key, value = pair.split(":", 1)
            try:
                data[key.strip()] = float(value.strip())
            except ValueError:
                pass
    
    return data


def parse_alert_line(line):
    """Parsea línea de alertas."""
    alerts = []
    if not line.startswith("alert="):
        return alerts
    
    content = line[6:]  # Quitar "alert="
    alerts = [a.strip() for a in content.split(",") if a.strip()]
    
    return alerts


def format_time(seconds):
    """Formatea segundos a MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"

# ============================================================================
# VARIABLES GLOBALES DE DATOS
# ============================================================================

# Buffers de tiempo
time_buffer = deque(maxlen=BUFFER_SIZE)
t0 = None

# Buffers de terreno
terrain_sky = deque(maxlen=BUFFER_SIZE)
terrain_cloud = deque(maxlen=BUFFER_SIZE)
terrain_veg = deque(maxlen=BUFFER_SIZE)
terrain_dryveg = deque(maxlen=BUFFER_SIZE)
terrain_soil = deque(maxlen=BUFFER_SIZE)
terrain_water = deque(maxlen=BUFFER_SIZE)
terrain_smoke = deque(maxlen=BUFFER_SIZE)
terrain_fire = deque(maxlen=BUFFER_SIZE)
terrain_burned = deque(maxlen=BUFFER_SIZE)

# Buffers de fuego
fire_fdi = deque(maxlen=BUFFER_SIZE)
fire_smoke_idx = deque(maxlen=BUFFER_SIZE)
fire_risk = deque(maxlen=BUFFER_SIZE)

# Buffers de vegetación
veg_exg = deque(maxlen=BUFFER_SIZE)
veg_vari = deque(maxlen=BUFFER_SIZE)
veg_health = deque(maxlen=BUFFER_SIZE)

# Alertas actuales
current_alerts = []
current_risk_level = 0

# Estadísticas
stats = {
    "fdi_max": 0,
    "fdi_avg": 0,
    "smoke_max": 0,
    "fire_events": 0,
    "veg_health_avg": 0,
}

# ============================================================================
# CONFIGURACIÓN DE LA FIGURA
# ============================================================================

plt.style.use('dark_background')
fig = plt.figure(figsize=(16, 10), facecolor=COLORS["bg_dark"])
fig.canvas.manager.set_window_title("🔥 OV7670 Fire Detection & Vegetation Analysis - CanSat Dashboard")

# Grid layout: 3 filas, 4 columnas
gs = gridspec.GridSpec(3, 4, figure=fig, 
                       height_ratios=[1.2, 1, 1],
                       width_ratios=[1, 1, 1, 1],
                       hspace=0.35, wspace=0.3)

# ============================================================================
# PANEL 1: FIRE DETECTION INDEX (grande, arriba izquierda)
# ============================================================================

ax_fdi = fig.add_subplot(gs[0, 0:2])
ax_fdi.set_facecolor(COLORS["bg_panel"])
ax_fdi.set_title("🔥 FIRE DETECTION INDEX (FDI)", fontsize=14, fontweight='bold', 
                 color=COLORS["text"], pad=10)
ax_fdi.set_xlabel("Tiempo (s)", fontsize=10, color=COLORS["text_secondary"])
ax_fdi.set_ylabel("FDI (0-100)", fontsize=10, color=COLORS["text_secondary"])
ax_fdi.set_ylim(0, 100)
ax_fdi.axhline(y=15, color=COLORS["success"], linestyle='--', alpha=0.5, linewidth=1)
ax_fdi.axhline(y=35, color=COLORS["warning"], linestyle='--', alpha=0.5, linewidth=1)
ax_fdi.axhline(y=55, color="#f0883e", linestyle='--', alpha=0.5, linewidth=1)
ax_fdi.axhline(y=75, color=COLORS["error"], linestyle='--', alpha=0.5, linewidth=1)
ax_fdi.tick_params(colors=COLORS["text_secondary"])
ax_fdi.grid(True, alpha=0.2, color=COLORS["grid"])
for spine in ax_fdi.spines.values():
    spine.set_color(COLORS["border"])

line_fdi, = ax_fdi.plot([], [], color=COLORS["fdi"], linewidth=2, label="FDI")
fill_fdi = None

# Texto de valor actual
txt_fdi_value = ax_fdi.text(0.98, 0.92, "--", fontsize=28, fontweight='bold',
                            color=COLORS["fdi"], ha='right', va='top',
                            transform=ax_fdi.transAxes, family='monospace',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["bg_panel"],
                                     edgecolor=COLORS["fdi"], alpha=0.9))

# ============================================================================
# PANEL 2: INDICADOR DE RIESGO (arriba centro)
# ============================================================================

ax_risk = fig.add_subplot(gs[0, 2])
ax_risk.set_facecolor(COLORS["bg_panel"])
ax_risk.set_title("⚠️ NIVEL DE RIESGO", fontsize=14, fontweight='bold',
                  color=COLORS["text"], pad=10)
ax_risk.set_xlim(0, 1)
ax_risk.set_ylim(0, 1)
ax_risk.axis('off')

# Círculo de riesgo
risk_circle = Circle((0.5, 0.5), 0.35, color=COLORS["success"], alpha=0.8)
ax_risk.add_patch(risk_circle)

txt_risk_level = ax_risk.text(0.5, 0.5, "0", fontsize=48, fontweight='bold',
                               color='white', ha='center', va='center',
                               transform=ax_risk.transAxes, family='monospace')

txt_risk_label = ax_risk.text(0.5, 0.12, "SIN RIESGO", fontsize=12, fontweight='bold',
                               color=COLORS["success"], ha='center', va='center',
                               transform=ax_risk.transAxes)

# ============================================================================
# PANEL 3: ALERTAS (arriba derecha)
# ============================================================================

ax_alerts = fig.add_subplot(gs[0, 3])
ax_alerts.set_facecolor(COLORS["bg_panel"])
ax_alerts.set_title("🚨 ALERTAS ACTIVAS", fontsize=14, fontweight='bold',
                    color=COLORS["text"], pad=10)
ax_alerts.set_xlim(0, 1)
ax_alerts.set_ylim(0, 1)
ax_alerts.axis('off')

txt_alerts = ax_alerts.text(0.5, 0.5, "Sin alertas", fontsize=11,
                            color=COLORS["text_secondary"], ha='center', va='center',
                            transform=ax_alerts.transAxes, family='monospace')

# ============================================================================
# PANEL 4: CLASIFICACIÓN DE TERRENO (medio izquierda)
# ============================================================================

ax_terrain = fig.add_subplot(gs[1, 0:2])
ax_terrain.set_facecolor(COLORS["bg_panel"])
ax_terrain.set_title("🗺️ CLASIFICACIÓN DE TERRENO", fontsize=14, fontweight='bold',
                     color=COLORS["text"], pad=10)
ax_terrain.set_xlabel("Tipo de Terreno", fontsize=10, color=COLORS["text_secondary"])
ax_terrain.set_ylabel("Porcentaje (%)", fontsize=10, color=COLORS["text_secondary"])
ax_terrain.set_ylim(0, 100)
ax_terrain.tick_params(colors=COLORS["text_secondary"])
ax_terrain.grid(True, alpha=0.2, color=COLORS["grid"], axis='y')
for spine in ax_terrain.spines.values():
    spine.set_color(COLORS["border"])

terrain_labels = ["Cielo", "Nubes", "Veg.", "V.Seca", "Suelo", "Agua", "Humo", "Fuego", "Quemado"]
terrain_colors = [COLORS["sky"], COLORS["cloud"], COLORS["vegetation"], COLORS["dry_veg"],
                  COLORS["bare_soil"], COLORS["water"], COLORS["smoke"], COLORS["fire"], COLORS["burned"]]
terrain_bars = ax_terrain.bar(terrain_labels, [0]*9, color=terrain_colors, edgecolor='white', linewidth=0.5)
ax_terrain.set_xticklabels(terrain_labels, rotation=45, ha='right', fontsize=9)

# ============================================================================
# PANEL 5: ÍNDICES DE VEGETACIÓN (medio derecha)
# ============================================================================

ax_veg = fig.add_subplot(gs[1, 2:4])
ax_veg.set_facecolor(COLORS["bg_panel"])
ax_veg.set_title("🌱 ÍNDICES DE VEGETACIÓN", fontsize=14, fontweight='bold',
                 color=COLORS["text"], pad=10)
ax_veg.set_xlabel("Tiempo (s)", fontsize=10, color=COLORS["text_secondary"])
ax_veg.set_ylabel("Índice (0-1)", fontsize=10, color=COLORS["text_secondary"])
ax_veg.set_ylim(0, 1)
ax_veg.tick_params(colors=COLORS["text_secondary"])
ax_veg.grid(True, alpha=0.2, color=COLORS["grid"])
for spine in ax_veg.spines.values():
    spine.set_color(COLORS["border"])

line_exg, = ax_veg.plot([], [], color=COLORS["exg"], linewidth=2, label="ExG")
line_vari, = ax_veg.plot([], [], color=COLORS["vari"], linewidth=2, label="VARI")
ax_veg.legend(loc='upper right', fontsize=9, framealpha=0.8)

# ============================================================================
# PANEL 6: DETECCIÓN DE HUMO (abajo izquierda)
# ============================================================================

ax_smoke = fig.add_subplot(gs[2, 0:2])
ax_smoke.set_facecolor(COLORS["bg_panel"])
ax_smoke.set_title("💨 DETECCIÓN DE HUMO", fontsize=14, fontweight='bold',
                   color=COLORS["text"], pad=10)
ax_smoke.set_xlabel("Tiempo (s)", fontsize=10, color=COLORS["text_secondary"])
ax_smoke.set_ylabel("Índice Humo (0-100)", fontsize=10, color=COLORS["text_secondary"])
ax_smoke.set_ylim(0, 100)
ax_smoke.axhline(y=50, color=COLORS["warning"], linestyle='--', alpha=0.5, linewidth=1, label="Umbral alerta")
ax_smoke.tick_params(colors=COLORS["text_secondary"])
ax_smoke.grid(True, alpha=0.2, color=COLORS["grid"])
for spine in ax_smoke.spines.values():
    spine.set_color(COLORS["border"])

line_smoke, = ax_smoke.plot([], [], color=COLORS["smoke"], linewidth=2, label="Humo")
ax_smoke.legend(loc='upper right', fontsize=9, framealpha=0.8)

# ============================================================================
# PANEL 7: SALUD DE VEGETACIÓN (abajo derecha)
# ============================================================================

ax_health = fig.add_subplot(gs[2, 2:4])
ax_health.set_facecolor(COLORS["bg_panel"])
ax_health.set_title("🌿 SALUD DE VEGETACIÓN", fontsize=14, fontweight='bold',
                    color=COLORS["text"], pad=10)
ax_health.set_xlabel("Tiempo (s)", fontsize=10, color=COLORS["text_secondary"])
ax_health.set_ylabel("Salud (%)", fontsize=10, color=COLORS["text_secondary"])
ax_health.set_ylim(0, 100)
ax_health.axhline(y=50, color=COLORS["warning"], linestyle='--', alpha=0.5, linewidth=1, label="Umbral sequía")
ax_health.tick_params(colors=COLORS["text_secondary"])
ax_health.grid(True, alpha=0.2, color=COLORS["grid"])
for spine in ax_health.spines.values():
    spine.set_color(COLORS["border"])

line_health, = ax_health.plot([], [], color=COLORS["health"], linewidth=2, label="Salud")
ax_health.legend(loc='upper right', fontsize=9, framealpha=0.8)

# ============================================================================
# CONEXIÓN SERIAL
# ============================================================================

port = find_arduino_port()
if port:
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=SERIAL_TIMEOUT)
        print(f"[OK] Conectado a {port}")
        time.sleep(2)  # Esperar reset del Arduino
    except Exception as e:
        print(f"[ERROR] No se pudo conectar: {e}")
        ser = None
else:
    print("[ERROR] No se encontró puerto Arduino")
    ser = None

# ============================================================================
# ARCHIVO CSV
# ============================================================================

csv_file = None
csv_writer = None

def init_csv():
    global csv_file, csv_writer
    
    csv_file = open(CSV_FILE, 'w', newline='', encoding='utf-8')
    csv_writer = csv.writer(csv_file)
    
    # Header
    csv_writer.writerow([
        "timestamp", "elapsed_s",
        # Terreno
        "pct_sky", "pct_cloud", "pct_vegetation", "pct_dry_veg",
        "pct_soil", "pct_water", "pct_smoke", "pct_fire", "pct_burned",
        # Fuego
        "fdi", "smoke_index", "risk_level",
        # Vegetación
        "exg", "vari", "veg_health",
        # Alertas
        "alerts"
    ])
    
    print(f"[INFO] Archivo CSV creado: {CSV_FILE}")


def log_to_csv(data):
    global csv_writer
    
    if csv_writer is None:
        return
    
    try:
        csv_writer.writerow([
            datetime.now().isoformat(),
            data.get("elapsed", 0),
            # Terreno
            data.get("sky", 0),
            data.get("cloud", 0),
            data.get("veg", 0),
            data.get("dryveg", 0),
            data.get("soil", 0),
            data.get("water", 0),
            data.get("smoke", 0),
            data.get("fire", 0),
            data.get("burned", 0),
            # Fuego
            data.get("fdi", 0),
            data.get("smoke_idx", 0),
            data.get("risk", 0),
            # Vegetación
            data.get("exg", 0),
            data.get("vari", 0),
            data.get("health", 0),
            # Alertas
            ",".join(data.get("alerts", []))
        ])
        csv_file.flush()
    except Exception as e:
        print(f"[ERROR] CSV write: {e}")

# Inicializar CSV
init_csv()

# ============================================================================
# FUNCIÓN DE ACTUALIZACIÓN
# ============================================================================

def update(_frame):
    global t0, current_alerts, current_risk_level, fill_fdi
    global risk_circle
    
    if ser is None or not ser.is_open:
        return
    
    if t0 is None:
        t0 = time.monotonic()
    
    t_now = time.monotonic() - t0
    
    # Datos del frame actual
    frame_data = {
        "elapsed": t_now,
        "alerts": []
    }
    
    # Leer todas las líneas disponibles
    terrain_data = {}
    fire_data = {}
    veg_data = {}
    alerts = []
    
    try:
        while ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            
            if line.startswith("terrain="):
                terrain_data = parse_terrain_line(line)
            elif line.startswith("fire="):
                fire_data = parse_fire_line(line)
            elif line.startswith("veg="):
                veg_data = parse_veg_line(line)
            elif line.startswith("alert="):
                alerts = parse_alert_line(line)
            elif line.startswith("info=") or line.startswith("warning=") or line.startswith("error="):
                print(f"[ARDUINO] {line}")
    except Exception as e:
        print(f"[ERROR] Serial read: {e}")
        return
    
    # Actualizar buffers si hay datos
    if terrain_data or fire_data or veg_data:
        time_buffer.append(t_now)
        
        # Terreno
        terrain_sky.append(terrain_data.get("sky", 0))
        terrain_cloud.append(terrain_data.get("cloud", 0))
        terrain_veg.append(terrain_data.get("veg", 0))
        terrain_dryveg.append(terrain_data.get("dryveg", 0))
        terrain_soil.append(terrain_data.get("soil", 0))
        terrain_water.append(terrain_data.get("water", 0))
        terrain_smoke.append(terrain_data.get("smoke", 0))
        terrain_fire.append(terrain_data.get("fire", 0))
        terrain_burned.append(terrain_data.get("burned", 0))
        
        # Fuego
        fdi = fire_data.get("fdi", 0)
        fire_fdi.append(fdi)
        fire_smoke_idx.append(fire_data.get("smoke", 0))
        risk = int(fire_data.get("risk", 0))
        fire_risk.append(risk)
        current_risk_level = risk
        
        # Vegetación
        veg_exg.append(veg_data.get("exg", 0.5))
        veg_vari.append(veg_data.get("vari", 0.5))
        veg_health.append(veg_data.get("health", 0))
        
        # Alertas
        current_alerts = alerts
        
        # Datos para CSV
        frame_data.update(terrain_data)
        frame_data["fdi"] = fdi
        frame_data["smoke_idx"] = fire_data.get("smoke", 0)
        frame_data["risk"] = risk
        frame_data["exg"] = veg_data.get("exg", 0)
        frame_data["vari"] = veg_data.get("vari", 0)
        frame_data["health"] = veg_data.get("health", 0)
        frame_data["alerts"] = alerts
        
        log_to_csv(frame_data)
    
    # ========================================
    # ACTUALIZAR GRÁFICAS
    # ========================================
    
    if len(time_buffer) > 0:
        times = list(time_buffer)
        
        # Panel 1: FDI
        line_fdi.set_data(times, list(fire_fdi))
        ax_fdi.set_xlim(max(0, times[-1] - 60), times[-1] + 2)
        
        if len(fire_fdi) > 0:
            fdi_val = fire_fdi[-1]
            txt_fdi_value.set_text(f"{fdi_val:.1f}")
            
            # Color según riesgo
            if fdi_val >= 75:
                txt_fdi_value.set_color(COLORS["error"])
            elif fdi_val >= 55:
                txt_fdi_value.set_color("#f0883e")
            elif fdi_val >= 35:
                txt_fdi_value.set_color(COLORS["warning"])
            elif fdi_val >= 15:
                txt_fdi_value.set_color("#d4d422")
            else:
                txt_fdi_value.set_color(COLORS["success"])
        
        # Panel 2: Riesgo
        risk_info = RISK_LEVELS.get(current_risk_level, RISK_LEVELS[0])
        risk_circle.set_color(risk_info[1])
        txt_risk_level.set_text(str(current_risk_level))
        txt_risk_label.set_text(risk_info[0])
        txt_risk_label.set_color(risk_info[1])
        
        # Panel 3: Alertas
        if current_alerts:
            alert_text = "\n".join([f"⚠️ {a}" for a in current_alerts[:5]])
            txt_alerts.set_text(alert_text)
            txt_alerts.set_color(COLORS["error"])
        else:
            txt_alerts.set_text("✓ Sin alertas")
            txt_alerts.set_color(COLORS["success"])
        
        # Panel 4: Terreno (barras)
        if len(terrain_sky) > 0:
            values = [
                terrain_sky[-1], terrain_cloud[-1], terrain_veg[-1],
                terrain_dryveg[-1], terrain_soil[-1], terrain_water[-1],
                terrain_smoke[-1], terrain_fire[-1], terrain_burned[-1]
            ]
            for bar, val in zip(terrain_bars, values):
                bar.set_height(val)
        
        # Panel 5: Vegetación
        line_exg.set_data(times, list(veg_exg))
        line_vari.set_data(times, list(veg_vari))
        ax_veg.set_xlim(max(0, times[-1] - 60), times[-1] + 2)
        
        # Panel 6: Humo
        line_smoke.set_data(times, list(fire_smoke_idx))
        ax_smoke.set_xlim(max(0, times[-1] - 60), times[-1] + 2)
        
        # Panel 7: Salud vegetación
        line_health.set_data(times, list(veg_health))
        ax_health.set_xlim(max(0, times[-1] - 60), times[-1] + 2)

# ============================================================================
# FUNCIÓN DE EXPORTACIÓN
# ============================================================================

def export_graphs():
    """Exporta las gráficas actuales como PNG."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        # Exportar figura completa
        export_path = os.path.join(EXPORTS_DIR, f"dashboard_{timestamp}.png")
        fig.savefig(export_path, dpi=150, facecolor=COLORS["bg_dark"], 
                    edgecolor='none', bbox_inches='tight')
        print(f"[INFO] Gráficas exportadas: {export_path}")
    except Exception as e:
        print(f"[ERROR] Export failed: {e}")


def generate_report():
    """Genera el reporte HTML."""
    try:
        report_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_report.py")
        if os.path.exists(report_script):
            subprocess.run([sys.executable, report_script], check=True)
            print("[INFO] Reporte HTML generado")
    except Exception as e:
        print(f"[ERROR] Report generation: {e}")

# ============================================================================
# MAIN
# ============================================================================

# Animación
ani = FuncAnimation(fig, update, interval=100, cache_frame_data=False)

# Ajustar layout
fig.subplots_adjust(left=0.06, right=0.98, top=0.94, bottom=0.08)

try:
    plt.show()
finally:
    # Cleanup
    print("\n[INFO] Cerrando dashboard...")
    
    if csv_file:
        csv_file.close()
        print(f"[INFO] Datos guardados en: {CSV_FILE}")
    
    if ser and ser.is_open:
        ser.close()
        print("[INFO] Puerto serial cerrado")
    
    # Exportar gráficas
    export_graphs()
    
    # Generar reporte
    generate_report()
    
    print("[INFO] ¡Hasta pronto!")
