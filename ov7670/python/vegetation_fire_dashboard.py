# ============================================================================
# VEGETATION TYPE & FIRE PROBABILITY ANALYZER - DASHBOARD
# ============================================================================
#
# Dashboard especializado para visualización de tipos de vegetación y
# probabilidad de incendio en tiempo real.
#
# Autor: CanSat Team
# Fecha: Febrero 2026
# ============================================================================

import os
import re
import sys
import time
import csv
from datetime import datetime
from collections import deque

import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.patches import Wedge, Circle, Rectangle
import matplotlib.gridspec as gridspec
import numpy as np

import serial
import serial.tools.list_ports

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

CSV_FILE = os.path.join(DATA_DIR, "vegetation_fire_data.csv")
BAUD_RATE = 115200
BUFFER_SIZE = 200

# ============================================================================
# TIPOS DE VEGETACIÓN
# ============================================================================

VEG_TYPES = {
    "SIN_VEGETACION": {"name": "Sin Vegetación", "color": "#8B4513", "risk": "bajo"},
    "BOSQUE_DENSO": {"name": "Bosque Denso", "color": "#006400", "risk": "alto"},
    "BOSQUE_ABIERTO": {"name": "Bosque Abierto", "color": "#228B22", "risk": "medio-alto"},
    "MATORRAL": {"name": "Matorral", "color": "#9ACD32", "risk": "muy alto"},
    "PASTIZAL": {"name": "Pastizal", "color": "#7CFC00", "risk": "alto"},
    "CULTIVO": {"name": "Cultivo", "color": "#FFD700", "risk": "medio"},
    "RIPARIA": {"name": "Riparia", "color": "#00CED1", "risk": "bajo"},
    "ESTRESADA": {"name": "Estresada", "color": "#FF8C00", "risk": "alto"},
    "MUERTA_SECA": {"name": "Muerta/Seca", "color": "#8B0000", "risk": "muy alto"},
    "MIXTA": {"name": "Mixta", "color": "#808080", "risk": "medio"}
}

# ============================================================================
# PALETA DE COLORES
# ============================================================================

COLORS = {
    "bg_dark": "#0d1117",
    "bg_panel": "#161b22",
    "bg_card": "#21262d",
    "text": "#E6EDF3",
    "text_secondary": "#8B949E",
    "grid": "#30363d",
    "fire_low": "#3fb950",
    "fire_medium": "#d29922",
    "fire_high": "#f0883e",
    "fire_critical": "#f85149",
    "veg_healthy": "#32CD32",
    "veg_stressed": "#FF8C00",
}

# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def find_arduino_port():
    """Detecta el puerto del Arduino."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        desc = (port.description or "").lower()
        hwid = (port.hwid or "").lower()
        if "2341" in hwid or "arduino" in desc or "ch340" in desc:
            print(f"[INFO] Arduino detectado en {port.device}")
            return port.device
    if ports:
        return ports[0].device
    return None


def parse_line(line):
    """Parsea una línea de datos del Arduino."""
    data = {}
    
    if "=" not in line:
        return data
    
    prefix, content = line.split("=", 1)
    data["type"] = prefix
    
    if prefix == "vegtype":
        # vegtype=MATORRAL,conf:85.5%
        parts = content.split(",")
        data["vegtype"] = parts[0]
        if len(parts) > 1 and ":" in parts[1]:
            data["confidence"] = float(parts[1].split(":")[1].replace("%", ""))
    
    elif prefix == "vegtypes":
        # vegtypes=bosque_d:12.5,bosque_a:8.3,...
        for pair in content.split(","):
            if ":" in pair:
                key, val = pair.split(":")
                data[f"veg_{key}"] = float(val)
    
    elif prefix == "vegindex":
        # vegindex=exg:0.250,vari:0.180,...
        for pair in content.split(","):
            if ":" in pair:
                key, val = pair.split(":")
                data[key] = float(val)
    
    elif prefix == "vegstate":
        # vegstate=sequia:45.2,estres:32.1,...
        for pair in content.split(","):
            if ":" in pair:
                key, val = pair.split(":")
                data[key] = float(val)
    
    elif prefix == "FIRE_PROB":
        # FIRE_PROB=67.5%,propagacion:72.3,intensidad:58.1
        parts = content.split(",")
        data["fire_prob"] = float(parts[0].replace("%", ""))
        for pair in parts[1:]:
            if ":" in pair:
                key, val = pair.split(":")
                data[key] = float(val)
    
    elif prefix == "fire_factors":
        # fire_factors=f_vegtype:70.2,f_sequia:45.3,...
        for pair in content.split(","):
            if ":" in pair:
                key, val = pair.split(":")
                data[key] = float(val)
    
    elif prefix == "ALERTA":
        data["alert"] = content
    
    return data

# ============================================================================
# BUFFERS DE DATOS
# ============================================================================

time_buffer = deque(maxlen=BUFFER_SIZE)
fire_prob_buffer = deque(maxlen=BUFFER_SIZE)
spread_buffer = deque(maxlen=BUFFER_SIZE)
intensity_buffer = deque(maxlen=BUFFER_SIZE)
dryness_buffer = deque(maxlen=BUFFER_SIZE)
stress_buffer = deque(maxlen=BUFFER_SIZE)
exg_buffer = deque(maxlen=BUFFER_SIZE)
vari_buffer = deque(maxlen=BUFFER_SIZE)

current_vegtype = "MIXTA"
current_confidence = 0
current_fire_prob = 0
current_alert = ""

veg_distribution = {
    "bosque_d": 0, "bosque_a": 0, "matorral": 0, "pastizal": 0,
    "cultivo": 0, "riparia": 0, "estres": 0, "seca": 0, "sinveg": 0
}

fire_factors = {
    "f_vegtype": 0, "f_sequia": 0, "f_biomasa": 0, "f_conti": 0, "f_estres": 0
}

t0 = None

# ============================================================================
# FIGURA Y PANELES
# ============================================================================

plt.style.use('dark_background')
fig = plt.figure(figsize=(16, 10), facecolor=COLORS["bg_dark"])
fig.canvas.manager.set_window_title("🌲 Vegetation Type & Fire Probability Analyzer")

gs = gridspec.GridSpec(3, 4, figure=fig, 
                       height_ratios=[1.2, 1, 1],
                       hspace=0.35, wspace=0.3)

# ============================================================================
# Panel 1: PROBABILIDAD DE INCENDIO (gauge grande)
# ============================================================================

ax_gauge = fig.add_subplot(gs[0, 0:2])
ax_gauge.set_facecolor(COLORS["bg_panel"])
ax_gauge.set_xlim(-1.5, 1.5)
ax_gauge.set_ylim(-0.2, 1.3)
ax_gauge.set_aspect('equal')
ax_gauge.axis('off')
ax_gauge.set_title("🔥 PROBABILIDAD DE INCENDIO", fontsize=16, fontweight='bold',
                   color=COLORS["text"], pad=10)

# Arco del gauge
theta1, theta2 = 180, 0
gauge_bg = Wedge((0, 0), 1, theta1, theta2, width=0.3, 
                  facecolor=COLORS["bg_card"], edgecolor=COLORS["grid"])
ax_gauge.add_patch(gauge_bg)

# Segmentos de color
colors_gauge = [COLORS["fire_low"], COLORS["fire_medium"], COLORS["fire_high"], COLORS["fire_critical"]]
for i, (start, end) in enumerate([(180, 135), (135, 90), (90, 45), (45, 0)]):
    seg = Wedge((0, 0), 1, start, end, width=0.3, facecolor=colors_gauge[i], alpha=0.3)
    ax_gauge.add_patch(seg)

# Aguja del gauge
gauge_needle, = ax_gauge.plot([0, 0], [0, 0.7], color='white', linewidth=4, solid_capstyle='round')
gauge_center = Circle((0, 0), 0.08, facecolor='white', edgecolor=COLORS["grid"])
ax_gauge.add_patch(gauge_center)

# Texto de valor
txt_fire_prob = ax_gauge.text(0, -0.15, "0%", fontsize=42, fontweight='bold',
                               color=COLORS["fire_low"], ha='center', va='top',
                               family='monospace')

# Etiquetas
ax_gauge.text(-1.2, 0, "0%", fontsize=10, color=COLORS["text_secondary"], ha='center')
ax_gauge.text(0, 1.15, "50%", fontsize=10, color=COLORS["text_secondary"], ha='center')
ax_gauge.text(1.2, 0, "100%", fontsize=10, color=COLORS["text_secondary"], ha='center')

# ============================================================================
# Panel 2: TIPO DE VEGETACIÓN
# ============================================================================

ax_vegtype = fig.add_subplot(gs[0, 2])
ax_vegtype.set_facecolor(COLORS["bg_panel"])
ax_vegtype.axis('off')
ax_vegtype.set_title("🌲 VEGETACIÓN DOMINANTE", fontsize=14, fontweight='bold',
                     color=COLORS["text"], pad=10)

txt_vegtype = ax_vegtype.text(0.5, 0.6, "---", fontsize=20, fontweight='bold',
                               color=COLORS["veg_healthy"], ha='center', va='center',
                               transform=ax_vegtype.transAxes)

txt_vegtype_risk = ax_vegtype.text(0.5, 0.35, "Riesgo: ---", fontsize=12,
                                    color=COLORS["text_secondary"], ha='center', va='center',
                                    transform=ax_vegtype.transAxes)

txt_confidence = ax_vegtype.text(0.5, 0.15, "Confianza: ---%", fontsize=11,
                                  color=COLORS["text_secondary"], ha='center', va='center',
                                  transform=ax_vegtype.transAxes)

# ============================================================================
# Panel 3: ALERTAS
# ============================================================================

ax_alert = fig.add_subplot(gs[0, 3])
ax_alert.set_facecolor(COLORS["bg_panel"])
ax_alert.axis('off')
ax_alert.set_title("🚨 ESTADO", fontsize=14, fontweight='bold',
                   color=COLORS["text"], pad=10)

txt_alert = ax_alert.text(0.5, 0.5, "✓ Normal", fontsize=14,
                          color=COLORS["fire_low"], ha='center', va='center',
                          transform=ax_alert.transAxes, family='monospace')

# ============================================================================
# Panel 4: DISTRIBUCIÓN DE VEGETACIÓN
# ============================================================================

ax_vegdist = fig.add_subplot(gs[1, 0:2])
ax_vegdist.set_facecolor(COLORS["bg_panel"])
ax_vegdist.set_title("📊 DISTRIBUCIÓN DE VEGETACIÓN", fontsize=14, fontweight='bold',
                     color=COLORS["text"], pad=10)
ax_vegdist.set_ylabel("%", fontsize=10, color=COLORS["text_secondary"])
ax_vegdist.set_ylim(0, 100)
ax_vegdist.tick_params(colors=COLORS["text_secondary"])
ax_vegdist.grid(True, alpha=0.2, color=COLORS["grid"], axis='y')

veg_labels = ["Bosque\nDenso", "Bosque\nAbierto", "Matorral", "Pastizal", 
              "Cultivo", "Riparia", "Estres.", "Seca", "Sin Veg."]
veg_colors = [VEG_TYPES["BOSQUE_DENSO"]["color"], VEG_TYPES["BOSQUE_ABIERTO"]["color"],
              VEG_TYPES["MATORRAL"]["color"], VEG_TYPES["PASTIZAL"]["color"],
              VEG_TYPES["CULTIVO"]["color"], VEG_TYPES["RIPARIA"]["color"],
              VEG_TYPES["ESTRESADA"]["color"], VEG_TYPES["MUERTA_SECA"]["color"],
              VEG_TYPES["SIN_VEGETACION"]["color"]]
bars_veg = ax_vegdist.bar(veg_labels, [0]*9, color=veg_colors, edgecolor='white', linewidth=0.5)
ax_vegdist.set_xticklabels(veg_labels, fontsize=8, rotation=0)

# ============================================================================
# Panel 5: FACTORES DE RIESGO
# ============================================================================

ax_factors = fig.add_subplot(gs[1, 2:4])
ax_factors.set_facecolor(COLORS["bg_panel"])
ax_factors.set_title("⚠️ FACTORES DE RIESGO DE INCENDIO", fontsize=14, fontweight='bold',
                     color=COLORS["text"], pad=10)
ax_factors.set_xlim(0, 100)
ax_factors.set_ylim(-0.5, 4.5)
ax_factors.tick_params(colors=COLORS["text_secondary"])
ax_factors.grid(True, alpha=0.2, color=COLORS["grid"], axis='x')

factor_labels = ["Tipo Vegetación\n(30%)", "Sequedad\n(25%)", "Biomasa\n(20%)", 
                 "Continuidad\n(15%)", "Estrés\n(10%)"]
bars_factors = ax_factors.barh(range(5), [0]*5, color=[COLORS["fire_medium"]]*5, height=0.6)
ax_factors.set_yticks(range(5))
ax_factors.set_yticklabels(factor_labels, fontsize=9)
ax_factors.invert_yaxis()

# ============================================================================
# Panel 6: ÍNDICES DE VEGETACIÓN
# ============================================================================

ax_indices = fig.add_subplot(gs[2, 0:2])
ax_indices.set_facecolor(COLORS["bg_panel"])
ax_indices.set_title("🌱 ÍNDICES DE VEGETACIÓN", fontsize=14, fontweight='bold',
                     color=COLORS["text"], pad=10)
ax_indices.set_xlabel("Tiempo (s)", fontsize=10, color=COLORS["text_secondary"])
ax_indices.set_ylabel("Valor", fontsize=10, color=COLORS["text_secondary"])
ax_indices.set_ylim(-0.5, 0.5)
ax_indices.tick_params(colors=COLORS["text_secondary"])
ax_indices.grid(True, alpha=0.2, color=COLORS["grid"])
ax_indices.axhline(y=0, color=COLORS["grid"], linewidth=1)

line_exg, = ax_indices.plot([], [], color=COLORS["veg_healthy"], linewidth=2, label="ExG")
line_vari, = ax_indices.plot([], [], color="#00CED1", linewidth=2, label="VARI")
ax_indices.legend(loc='upper right', fontsize=9)

# ============================================================================
# Panel 7: HISTÓRICO DE PROBABILIDAD
# ============================================================================

ax_history = fig.add_subplot(gs[2, 2:4])
ax_history.set_facecolor(COLORS["bg_panel"])
ax_history.set_title("📈 HISTÓRICO DE PROBABILIDAD DE INCENDIO", fontsize=14, fontweight='bold',
                     color=COLORS["text"], pad=10)
ax_history.set_xlabel("Tiempo (s)", fontsize=10, color=COLORS["text_secondary"])
ax_history.set_ylabel("Probabilidad (%)", fontsize=10, color=COLORS["text_secondary"])
ax_history.set_ylim(0, 100)
ax_history.axhline(y=30, color=COLORS["fire_low"], linestyle='--', alpha=0.5)
ax_history.axhline(y=50, color=COLORS["fire_medium"], linestyle='--', alpha=0.5)
ax_history.axhline(y=70, color=COLORS["fire_high"], linestyle='--', alpha=0.5)
ax_history.tick_params(colors=COLORS["text_secondary"])
ax_history.grid(True, alpha=0.2, color=COLORS["grid"])

line_fire_prob, = ax_history.plot([], [], color=COLORS["fire_high"], linewidth=2)

# ============================================================================
# CONEXIÓN SERIAL
# ============================================================================

port = find_arduino_port()
ser = None
if port:
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=1)
        print(f"[OK] Conectado a {port}")
        time.sleep(2)
    except Exception as e:
        print(f"[ERROR] {e}")
        ser = None

# ============================================================================
# CSV
# ============================================================================

csv_file = open(CSV_FILE, 'w', newline='', encoding='utf-8')
csv_writer = csv.writer(csv_file)
csv_writer.writerow([
    "timestamp", "elapsed_s", "vegtype", "confidence",
    "fire_prob", "spread", "intensity",
    "dryness", "stress", "biomass", "continuity",
    "exg", "vari", "alert"
])

# ============================================================================
# FUNCIÓN DE ACTUALIZACIÓN
# ============================================================================

def update(_frame):
    global t0, current_vegtype, current_confidence, current_fire_prob, current_alert
    global veg_distribution, fire_factors
    
    if ser is None or not ser.is_open:
        return
    
    if t0 is None:
        t0 = time.monotonic()
    
    t_now = time.monotonic() - t0
    
    # Datos actuales
    frame_data = {}
    
    # Leer líneas
    try:
        while ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if not line or line == "---":
                continue
            
            parsed = parse_line(line)
            
            if parsed.get("type") == "vegtype":
                current_vegtype = parsed.get("vegtype", "MIXTA")
                current_confidence = parsed.get("confidence", 0)
            
            elif parsed.get("type") == "vegtypes":
                for key in veg_distribution:
                    if f"veg_{key}" in parsed:
                        veg_distribution[key] = parsed[f"veg_{key}"]
            
            elif parsed.get("type") == "vegindex":
                if "exg" in parsed:
                    exg_buffer.append(parsed["exg"])
                if "vari" in parsed:
                    vari_buffer.append(parsed["vari"])
            
            elif parsed.get("type") == "vegstate":
                if "sequia" in parsed:
                    dryness_buffer.append(parsed["sequia"])
                    frame_data["dryness"] = parsed["sequia"]
                if "estres" in parsed:
                    stress_buffer.append(parsed["estres"])
                    frame_data["stress"] = parsed["estres"]
                if "biomasa" in parsed:
                    frame_data["biomass"] = parsed["biomasa"]
                if "continuidad" in parsed:
                    frame_data["continuity"] = parsed["continuidad"]
            
            elif parsed.get("type") == "FIRE_PROB":
                current_fire_prob = parsed.get("fire_prob", 0)
                fire_prob_buffer.append(current_fire_prob)
                time_buffer.append(t_now)
                
                if "propagacion" in parsed:
                    spread_buffer.append(parsed["propagacion"])
                    frame_data["spread"] = parsed["propagacion"]
                if "intensidad" in parsed:
                    intensity_buffer.append(parsed["intensidad"])
                    frame_data["intensity"] = parsed["intensidad"]
            
            elif parsed.get("type") == "fire_factors":
                for key in fire_factors:
                    if key in parsed:
                        fire_factors[key] = parsed[key]
            
            elif parsed.get("type") == "ALERTA":
                current_alert = parsed.get("alert", "")
            
            elif line.startswith("info=") or line.startswith("warning="):
                print(f"[ARDUINO] {line}")
    
    except Exception as e:
        print(f"[ERROR] {e}")
        return
    
    # Guardar CSV
    if fire_prob_buffer:
        try:
            csv_writer.writerow([
                datetime.now().isoformat(), t_now,
                current_vegtype, current_confidence,
                current_fire_prob,
                frame_data.get("spread", 0), frame_data.get("intensity", 0),
                frame_data.get("dryness", 0), frame_data.get("stress", 0),
                frame_data.get("biomass", 0), frame_data.get("continuity", 0),
                exg_buffer[-1] if exg_buffer else 0,
                vari_buffer[-1] if vari_buffer else 0,
                current_alert
            ])
            csv_file.flush()
        except:
            pass
    
    # ========================================
    # ACTUALIZAR GRÁFICAS
    # ========================================
    
    # Panel 1: Gauge de probabilidad
    angle = 180 - (current_fire_prob / 100 * 180)
    angle_rad = np.radians(angle)
    gauge_needle.set_data([0, 0.7 * np.cos(angle_rad)], [0, 0.7 * np.sin(angle_rad)])
    
    txt_fire_prob.set_text(f"{current_fire_prob:.0f}%")
    if current_fire_prob >= 70:
        txt_fire_prob.set_color(COLORS["fire_critical"])
    elif current_fire_prob >= 50:
        txt_fire_prob.set_color(COLORS["fire_high"])
    elif current_fire_prob >= 30:
        txt_fire_prob.set_color(COLORS["fire_medium"])
    else:
        txt_fire_prob.set_color(COLORS["fire_low"])
    
    # Panel 2: Tipo de vegetación
    veg_info = VEG_TYPES.get(current_vegtype, VEG_TYPES["MIXTA"])
    txt_vegtype.set_text(veg_info["name"])
    txt_vegtype.set_color(veg_info["color"])
    txt_vegtype_risk.set_text(f"Riesgo: {veg_info['risk']}")
    txt_confidence.set_text(f"Confianza: {current_confidence:.1f}%")
    
    # Panel 3: Alerta
    if current_alert:
        txt_alert.set_text(f"⚠️ {current_alert.replace('_', ' ')}")
        txt_alert.set_color(COLORS["fire_critical"])
    else:
        txt_alert.set_text("✓ Normal")
        txt_alert.set_color(COLORS["fire_low"])
    
    # Panel 4: Distribución
    values = [
        veg_distribution["bosque_d"], veg_distribution["bosque_a"],
        veg_distribution["matorral"], veg_distribution["pastizal"],
        veg_distribution["cultivo"], veg_distribution["riparia"],
        veg_distribution["estres"], veg_distribution["seca"],
        veg_distribution["sinveg"]
    ]
    for bar, val in zip(bars_veg, values):
        bar.set_height(val)
    
    # Panel 5: Factores
    factor_values = [
        fire_factors["f_vegtype"], fire_factors["f_sequia"],
        fire_factors["f_biomasa"], fire_factors["f_conti"], fire_factors["f_estres"]
    ]
    for bar, val in zip(bars_factors, factor_values):
        bar.set_width(val)
        if val >= 70:
            bar.set_color(COLORS["fire_critical"])
        elif val >= 50:
            bar.set_color(COLORS["fire_high"])
        elif val >= 30:
            bar.set_color(COLORS["fire_medium"])
        else:
            bar.set_color(COLORS["fire_low"])
    
    # Panel 6: Índices
    if len(time_buffer) > 0:
        times = list(time_buffer)
        line_exg.set_data(times[:len(exg_buffer)], list(exg_buffer))
        line_vari.set_data(times[:len(vari_buffer)], list(vari_buffer))
        ax_indices.set_xlim(max(0, times[-1] - 60), times[-1] + 2)
        
        # Panel 7: Histórico
        line_fire_prob.set_data(times, list(fire_prob_buffer))
        ax_history.set_xlim(max(0, times[-1] - 60), times[-1] + 2)

# ============================================================================
# MAIN
# ============================================================================

ani = FuncAnimation(fig, update, interval=100, cache_frame_data=False)
fig.subplots_adjust(left=0.06, right=0.98, top=0.94, bottom=0.08)

try:
    plt.show()
finally:
    if csv_file:
        csv_file.close()
        print(f"[INFO] Datos guardados: {CSV_FILE}")
    if ser and ser.is_open:
        ser.close()
    print("[INFO] Dashboard cerrado")
