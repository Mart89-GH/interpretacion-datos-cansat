# ============================================================================
# OV7670 FIRE DETECTION & VEGETATION ANALYSIS - REPORT GENERATOR
# ============================================================================
#
# Genera un informe HTML profesional con los datos recolectados del sistema
# OV7670 de detección de incendios y análisis de vegetación.
#
# Características:
# - Resumen ejecutivo de riesgo de incendio
# - Análisis temporal de todos los índices
# - Clasificación de terreno
# - Recomendaciones automatizadas
# - Diseño oscuro profesional con glassmorphism
#
# Autor: CanSat Team
# Fecha: Enero 2026
# ============================================================================

import csv
import json
import os
import statistics
from datetime import datetime

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CSV_FILE = os.path.join(DATA_DIR, "ov7670_data.csv")
REPORT_FILE = os.path.join(DATA_DIR, "report.html")

# ============================================================================
# ESTILOS CSS
# ============================================================================

CSS_STYLES = """
:root {
    --bg-dark: #0d1117;
    --bg-panel: #161b22;
    --bg-card: #21262d;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --grid-color: #30363d;
    --accent-fire: #ff6347;
    --accent-smoke: #808080;
    --accent-veg: #32cd32;
    --accent-water: #1e90ff;
    --success: #3fb950;
    --warning: #d29922;
    --error: #f85149;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
    background-color: var(--bg-dark);
    color: var(--text-primary);
    line-height: 1.6;
    padding: 2rem;
}

.container {
    max-width: 1400px;
    margin: 0 auto;
}

header {
    text-align: center;
    margin-bottom: 2rem;
    padding: 2rem;
    background: linear-gradient(135deg, rgba(255, 99, 71, 0.1), rgba(50, 205, 50, 0.1));
    border-radius: 1rem;
    border: 1px solid var(--grid-color);
}

header h1 {
    font-size: 2.5rem;
    background: linear-gradient(135deg, #ff6347, #ffa500);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.5rem;
}

.subtitle {
    color: var(--text-secondary);
    font-size: 1.1rem;
}

.meta-info {
    display: flex;
    justify-content: center;
    gap: 2rem;
    margin-top: 1rem;
    color: var(--text-secondary);
    font-size: 0.9rem;
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
}

.card {
    background-color: var(--bg-card);
    border-radius: 1rem;
    padding: 1.5rem;
    border: 1px solid var(--grid-color);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    transition: transform 0.2s, box-shadow 0.2s;
}

.card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 12px -2px rgba(0, 0, 0, 0.4);
}

.card.fire {
    border-left: 4px solid var(--accent-fire);
}

.card.smoke {
    border-left: 4px solid var(--accent-smoke);
}

.card.veg {
    border-left: 4px solid var(--accent-veg);
}

.card.alert {
    border-left: 4px solid var(--error);
    background: linear-gradient(135deg, rgba(248, 81, 73, 0.1), var(--bg-card));
}

.card.success {
    border-left: 4px solid var(--success);
    background: linear-gradient(135deg, rgba(63, 185, 80, 0.1), var(--bg-card));
}

.card h3 {
    font-size: 0.9rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.5rem;
}

.card .value {
    font-size: 2.5rem;
    font-weight: bold;
    font-family: 'Consolas', monospace;
}

.card .value.fire { color: var(--accent-fire); }
.card .value.smoke { color: var(--accent-smoke); }
.card .value.veg { color: var(--accent-veg); }
.card .value.success { color: var(--success); }
.card .value.warning { color: var(--warning); }
.card .value.error { color: var(--error); }

.card .subtext {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-top: 0.25rem;
}

.section {
    margin-bottom: 2rem;
}

.section h2 {
    font-size: 1.5rem;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid var(--grid-color);
}

.section h2 .emoji {
    margin-right: 0.5rem;
}

.charts-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(600px, 1fr));
    gap: 1.5rem;
}

.chart-container {
    background-color: var(--bg-card);
    border-radius: 1rem;
    padding: 1.5rem;
    border: 1px solid var(--grid-color);
}

.chart-container h3 {
    margin-bottom: 1rem;
    color: var(--text-primary);
}

.terrain-bar {
    display: flex;
    height: 40px;
    border-radius: 0.5rem;
    overflow: hidden;
    margin-bottom: 1rem;
}

.terrain-segment {
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 0.75rem;
    font-weight: bold;
    text-shadow: 0 1px 2px rgba(0,0,0,0.5);
    min-width: 30px;
}

.terrain-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    margin-top: 0.5rem;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
}

.legend-color {
    width: 16px;
    height: 16px;
    border-radius: 4px;
}

.recommendations {
    background-color: var(--bg-panel);
    border-radius: 1rem;
    padding: 1.5rem;
    border: 1px solid var(--grid-color);
}

.recommendations h3 {
    margin-bottom: 1rem;
    color: var(--text-primary);
}

.recommendation {
    padding: 1rem;
    margin-bottom: 0.75rem;
    border-radius: 0.5rem;
    border-left: 4px solid;
}

.recommendation.high {
    background-color: rgba(248, 81, 73, 0.1);
    border-color: var(--error);
}

.recommendation.medium {
    background-color: rgba(210, 153, 34, 0.1);
    border-color: var(--warning);
}

.recommendation.low {
    background-color: rgba(63, 185, 80, 0.1);
    border-color: var(--success);
}

.recommendation h4 {
    margin-bottom: 0.25rem;
}

.recommendation p {
    font-size: 0.9rem;
    color: var(--text-secondary);
}

table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 1rem;
}

th, td {
    padding: 0.75rem 1rem;
    text-align: left;
    border-bottom: 1px solid var(--grid-color);
}

th {
    background-color: var(--bg-panel);
    color: var(--text-secondary);
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.8rem;
    letter-spacing: 0.05em;
}

tr:hover {
    background-color: var(--bg-panel);
}

.risk-badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 1rem;
    font-size: 0.8rem;
    font-weight: bold;
}

.risk-0 { background-color: var(--success); color: white; }
.risk-1 { background-color: #d4d422; color: black; }
.risk-2 { background-color: var(--warning); color: black; }
.risk-3 { background-color: #f0883e; color: white; }
.risk-4 { background-color: var(--error); color: white; }

footer {
    text-align: center;
    margin-top: 3rem;
    padding-top: 2rem;
    border-top: 1px solid var(--grid-color);
    color: var(--text-secondary);
    font-size: 0.9rem;
}

@media (max-width: 768px) {
    .charts-grid {
        grid-template-columns: 1fr;
    }
    body {
        padding: 1rem;
    }
    header h1 {
        font-size: 1.8rem;
    }
}
"""

# ============================================================================
# COLORES DE TERRENO
# ============================================================================

TERRAIN_COLORS = {
    "sky": "#87CEEB",
    "cloud": "#E0E0E0",
    "vegetation": "#228B22",
    "dry_veg": "#DAA520",
    "soil": "#8B4513",
    "water": "#1E90FF",
    "smoke": "#808080",
    "fire": "#FF4500",
    "burned": "#2F2F2F"
}

TERRAIN_NAMES = {
    "sky": "Cielo",
    "cloud": "Nubes",
    "vegetation": "Vegetación",
    "dry_veg": "Veg. Seca",
    "soil": "Suelo",
    "water": "Agua",
    "smoke": "Humo",
    "fire": "Fuego",
    "burned": "Quemado"
}

RISK_NAMES = {
    0: "Sin Riesgo",
    1: "Bajo",
    2: "Moderado",
    3: "Alto",
    4: "Crítico"
}

# ============================================================================
# FUNCIONES DE LECTURA Y ANÁLISIS
# ============================================================================

def read_data(filepath):
    """Lee los datos del archivo CSV."""
    data = []
    
    if not os.path.exists(filepath):
        print(f"[ERROR] Archivo no encontrado: {filepath}")
        return data
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convertir valores numéricos
                parsed = {}
                for key, value in row.items():
                    try:
                        if key == "timestamp" or key == "alerts":
                            parsed[key] = value
                        else:
                            parsed[key] = float(value) if value else 0
                    except ValueError:
                        parsed[key] = value
                data.append(parsed)
        
        print(f"[INFO] Leídas {len(data)} filas de datos")
    except Exception as e:
        print(f"[ERROR] Error leyendo CSV: {e}")
    
    return data


def calculate_stats(values):
    """Calcula estadísticas básicas."""
    if not values:
        return {"min": 0, "max": 0, "avg": 0, "median": 0}
    
    clean = [v for v in values if v is not None and not isinstance(v, str)]
    
    if not clean:
        return {"min": 0, "max": 0, "avg": 0, "median": 0}
    
    return {
        "min": min(clean),
        "max": max(clean),
        "avg": statistics.mean(clean),
        "median": statistics.median(clean)
    }


def analyze_data(data):
    """Analiza los datos y genera estadísticas."""
    if not data:
        return None
    
    analysis = {
        "total_samples": len(data),
        "duration_s": data[-1].get("elapsed_s", 0) if data else 0,
        
        # Estadísticas de terreno
        "terrain": {},
        
        # Estadísticas de fuego
        "fdi": calculate_stats([d.get("fdi", 0) for d in data]),
        "smoke": calculate_stats([d.get("smoke_index", 0) for d in data]),
        
        # Estadísticas de vegetación
        "exg": calculate_stats([d.get("exg", 0) for d in data]),
        "vari": calculate_stats([d.get("vari", 0) for d in data]),
        "health": calculate_stats([d.get("veg_health", 0) for d in data]),
        
        # Alertas
        "total_alerts": 0,
        "alert_types": {},
        
        # Riesgo
        "max_risk": 0,
        "risk_distribution": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    }
    
    # Terreno promedio
    terrain_keys = ["pct_sky", "pct_cloud", "pct_vegetation", "pct_dry_veg",
                    "pct_soil", "pct_water", "pct_smoke", "pct_fire", "pct_burned"]
    
    for key in terrain_keys:
        values = [d.get(key, 0) for d in data]
        short_key = key.replace("pct_", "")
        analysis["terrain"][short_key] = calculate_stats(values)["avg"]
    
    # Alertas y riesgo
    for d in data:
        risk = int(d.get("risk_level", 0))
        analysis["max_risk"] = max(analysis["max_risk"], risk)
        analysis["risk_distribution"][risk] = analysis["risk_distribution"].get(risk, 0) + 1
        
        alerts_str = d.get("alerts", "")
        if alerts_str:
            analysis["total_alerts"] += 1
            for alert in alerts_str.split(","):
                alert = alert.strip()
                if alert:
                    analysis["alert_types"][alert] = analysis["alert_types"].get(alert, 0) + 1
    
    return analysis


def generate_recommendations(analysis):
    """Genera recomendaciones basadas en el análisis."""
    recommendations = []
    
    if not analysis:
        return recommendations
    
    # Riesgo de incendio
    fdi_max = analysis["fdi"]["max"]
    if fdi_max >= 75:
        recommendations.append({
            "priority": "high",
            "title": "🔥 ALERTA CRÍTICA DE INCENDIO",
            "text": f"Se detectó un FDI máximo de {fdi_max:.1f}. Se recomienda verificar inmediatamente la zona para descartar fuego activo."
        })
    elif fdi_max >= 55:
        recommendations.append({
            "priority": "high",
            "title": "⚠️ Alto Riesgo de Incendio",
            "text": f"FDI máximo de {fdi_max:.1f}. Mantener vigilancia activa y preparar recursos de respuesta."
        })
    elif fdi_max >= 35:
        recommendations.append({
            "priority": "medium",
            "title": "🟠 Riesgo Moderado de Incendio",
            "text": "Condiciones favorables para incendios. Incrementar frecuencia de monitoreo."
        })
    
    # Humo
    smoke_max = analysis["smoke"]["max"]
    if smoke_max >= 50:
        recommendations.append({
            "priority": "high",
            "title": "💨 Humo Detectado",
            "text": f"Índice de humo máximo: {smoke_max:.1f}. Posible incendio activo en la zona."
        })
    
    # Vegetación seca
    dry_veg = analysis["terrain"].get("dry_veg", 0)
    if dry_veg >= 30:
        recommendations.append({
            "priority": "medium",
            "title": "🌾 Alta Proporción de Vegetación Seca",
            "text": f"{dry_veg:.1f}% de vegetación seca detectada. Alto riesgo de propagación en caso de incendio."
        })
    
    # Salud vegetación
    health_avg = analysis["health"]["avg"]
    if health_avg < 40:
        recommendations.append({
            "priority": "medium",
            "title": "🥀 Vegetación Estresada",
            "text": f"Salud promedio de vegetación: {health_avg:.1f}%. Posible sequía o déficit hídrico."
        })
    elif health_avg >= 70:
        recommendations.append({
            "priority": "low",
            "title": "🌿 Vegetación Saludable",
            "text": f"Índice de salud promedio: {health_avg:.1f}%. Condiciones óptimas de vegetación."
        })
    
    # Sin alertas
    if not recommendations:
        recommendations.append({
            "priority": "low",
            "title": "✅ Zona Segura",
            "text": "No se detectaron condiciones de riesgo significativas durante el período de monitoreo."
        })
    
    return recommendations

# ============================================================================
# GENERACIÓN DE HTML
# ============================================================================

def generate_html(data):
    """Genera el reporte HTML."""
    analysis = analyze_data(data)
    recommendations = generate_recommendations(analysis)
    
    if not analysis:
        print("[ERROR] No hay datos para generar el reporte")
        return
    
    # Duración formateada
    duration_mins = int(analysis["duration_s"] // 60)
    duration_secs = int(analysis["duration_s"] % 60)
    duration_str = f"{duration_mins}m {duration_secs}s"
    
    # Generar barra de terreno
    terrain_bar_html = ""
    terrain_legend_html = ""
    
    terrain_order = ["sky", "cloud", "vegetation", "dry_veg", "soil", "water", "smoke", "fire", "burned"]
    
    for key in terrain_order:
        pct = analysis["terrain"].get(key, 0)
        if pct > 1:  # Solo mostrar si > 1%
            color = TERRAIN_COLORS.get(key, "#666")
            name = TERRAIN_NAMES.get(key, key)
            terrain_bar_html += f'<div class="terrain-segment" style="width: {pct}%; background-color: {color};">{pct:.0f}%</div>'
        
        color = TERRAIN_COLORS.get(key, "#666")
        name = TERRAIN_NAMES.get(key, key)
        pct_val = analysis["terrain"].get(key, 0)
        terrain_legend_html += f'''
        <div class="legend-item">
            <div class="legend-color" style="background-color: {color};"></div>
            <span>{name}: {pct_val:.1f}%</span>
        </div>
        '''
    
    # Generar recomendaciones HTML
    rec_html = ""
    for rec in recommendations:
        rec_html += f'''
        <div class="recommendation {rec['priority']}">
            <h4>{rec['title']}</h4>
            <p>{rec['text']}</p>
        </div>
        '''
    
    # Determinar clase de riesgo general
    max_risk = analysis["max_risk"]
    risk_class = "success" if max_risk < 2 else ("warning" if max_risk < 3 else "error")
    risk_name = RISK_NAMES.get(max_risk, "Desconocido")
    
    # FDI clase
    fdi_max = analysis["fdi"]["max"]
    fdi_class = "success" if fdi_max < 35 else ("warning" if fdi_max < 55 else "error")
    
    # HTML completo
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OV7670 Fire Detection Report - CanSat</title>
    <style>
    {CSS_STYLES}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔥 Reporte de Detección de Incendios</h1>
            <p class="subtitle">Sistema OV7670 - Análisis Aéreo CanSat</p>
            <div class="meta-info">
                <span>📅 {datetime.now().strftime("%d/%m/%Y %H:%M")}</span>
                <span>⏱️ Duración: {duration_str}</span>
                <span>📊 {analysis['total_samples']} muestras</span>
            </div>
        </header>
        
        <!-- Resumen Ejecutivo -->
        <section class="section">
            <h2><span class="emoji">📊</span>Resumen Ejecutivo</h2>
            <div class="stats-grid">
                <div class="card {'alert' if max_risk >= 3 else 'success'}">
                    <h3>Nivel de Riesgo Máximo</h3>
                    <div class="value {risk_class}">{risk_name}</div>
                    <div class="subtext">Nivel {max_risk} de 4</div>
                </div>
                
                <div class="card fire">
                    <h3>Fire Detection Index (FDI)</h3>
                    <div class="value {fdi_class}">{fdi_max:.1f}</div>
                    <div class="subtext">Promedio: {analysis['fdi']['avg']:.1f} | Mín: {analysis['fdi']['min']:.1f}</div>
                </div>
                
                <div class="card smoke">
                    <h3>Índice de Humo Máximo</h3>
                    <div class="value smoke">{analysis['smoke']['max']:.1f}</div>
                    <div class="subtext">Promedio: {analysis['smoke']['avg']:.1f}</div>
                </div>
                
                <div class="card veg">
                    <h3>Salud de Vegetación</h3>
                    <div class="value veg">{analysis['health']['avg']:.1f}%</div>
                    <div class="subtext">Mín: {analysis['health']['min']:.1f}% | Máx: {analysis['health']['max']:.1f}%</div>
                </div>
            </div>
        </section>
        
        <!-- Clasificación de Terreno -->
        <section class="section">
            <h2><span class="emoji">🗺️</span>Clasificación de Terreno</h2>
            <div class="chart-container">
                <h3>Distribución Promedio del Terreno</h3>
                <div class="terrain-bar">
                    {terrain_bar_html}
                </div>
                <div class="terrain-legend">
                    {terrain_legend_html}
                </div>
            </div>
        </section>
        
        <!-- Índices de Vegetación -->
        <section class="section">
            <h2><span class="emoji">🌱</span>Análisis de Vegetación</h2>
            <div class="stats-grid">
                <div class="card veg">
                    <h3>Excess Green Index (ExG)</h3>
                    <div class="value veg">{analysis['exg']['avg']:.3f}</div>
                    <div class="subtext">Rango: {analysis['exg']['min']:.3f} - {analysis['exg']['max']:.3f}</div>
                </div>
                
                <div class="card veg">
                    <h3>VARI (Atmospheric Resistant)</h3>
                    <div class="value veg">{analysis['vari']['avg']:.3f}</div>
                    <div class="subtext">Rango: {analysis['vari']['min']:.3f} - {analysis['vari']['max']:.3f}</div>
                </div>
                
                <div class="card veg">
                    <h3>Vegetación Sana</h3>
                    <div class="value success">{analysis['terrain'].get('vegetation', 0):.1f}%</div>
                    <div class="subtext">Del área total analizada</div>
                </div>
                
                <div class="card {'alert' if analysis['terrain'].get('dry_veg', 0) > 20 else ''}">
                    <h3>Vegetación Seca/Estresada</h3>
                    <div class="value {'error' if analysis['terrain'].get('dry_veg', 0) > 30 else 'warning'}">{analysis['terrain'].get('dry_veg', 0):.1f}%</div>
                    <div class="subtext">Zona de riesgo de incendio</div>
                </div>
            </div>
        </section>
        
        <!-- Distribución de Riesgo -->
        <section class="section">
            <h2><span class="emoji">⚠️</span>Distribución de Niveles de Riesgo</h2>
            <div class="chart-container">
                <table>
                    <thead>
                        <tr>
                            <th>Nivel</th>
                            <th>Nombre</th>
                            <th>Muestras</th>
                            <th>Porcentaje</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><span class="risk-badge risk-0">0</span></td>
                            <td>Sin Riesgo</td>
                            <td>{analysis['risk_distribution'][0]}</td>
                            <td>{(analysis['risk_distribution'][0] / max(1, analysis['total_samples']) * 100):.1f}%</td>
                        </tr>
                        <tr>
                            <td><span class="risk-badge risk-1">1</span></td>
                            <td>Bajo</td>
                            <td>{analysis['risk_distribution'][1]}</td>
                            <td>{(analysis['risk_distribution'][1] / max(1, analysis['total_samples']) * 100):.1f}%</td>
                        </tr>
                        <tr>
                            <td><span class="risk-badge risk-2">2</span></td>
                            <td>Moderado</td>
                            <td>{analysis['risk_distribution'][2]}</td>
                            <td>{(analysis['risk_distribution'][2] / max(1, analysis['total_samples']) * 100):.1f}%</td>
                        </tr>
                        <tr>
                            <td><span class="risk-badge risk-3">3</span></td>
                            <td>Alto</td>
                            <td>{analysis['risk_distribution'][3]}</td>
                            <td>{(analysis['risk_distribution'][3] / max(1, analysis['total_samples']) * 100):.1f}%</td>
                        </tr>
                        <tr>
                            <td><span class="risk-badge risk-4">4</span></td>
                            <td>Crítico</td>
                            <td>{analysis['risk_distribution'][4]}</td>
                            <td>{(analysis['risk_distribution'][4] / max(1, analysis['total_samples']) * 100):.1f}%</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </section>
        
        <!-- Recomendaciones -->
        <section class="section">
            <h2><span class="emoji">💡</span>Recomendaciones</h2>
            <div class="recommendations">
                {rec_html}
            </div>
        </section>
        
        <footer>
            <p>Generado automáticamente por el Sistema OV7670 Fire Detection - CanSat</p>
            <p>© {datetime.now().year} CanSat Team</p>
        </footer>
    </div>
</body>
</html>
"""
    
    # Guardar archivo
    try:
        with open(REPORT_FILE, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"[OK] Reporte generado: {REPORT_FILE}")
        
        # Abrir en navegador
        import webbrowser
        webbrowser.open(f"file://{os.path.abspath(REPORT_FILE)}")
        
    except Exception as e:
        print(f"[ERROR] Error guardando reporte: {e}")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("OV7670 Fire Detection - Report Generator")
    print("=" * 50)
    
    # Leer datos
    data = read_data(CSV_FILE)
    
    if data:
        # Generar reporte
        generate_html(data)
    else:
        print("[WARNING] No hay datos para generar el reporte")
        print(f"  Asegúrate de que exista el archivo: {CSV_FILE}")
