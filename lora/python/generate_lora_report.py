# generate_lora_report.py
# Genera un report HTML interactivo con datos LoRa del CSV
# Usa Chart.js para gráficas individuales por cada dato

import csv
import json
import os
import statistics

# Configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CSV_FILE = os.path.join(DATA_DIR, "lora_data.csv")
OUTPUT_HTML = os.path.join(DATA_DIR, "report.html")

# CSS Styles
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --bg-dark: #0a0e17;
    --bg-card: #111827;
    --bg-card-hover: #1a2233;
    --text-primary: #f0f6fc;
    --text-secondary: #8b949e;
    --accent-temp: #ff6b6b;
    --accent-pres: #ffd93d;
    --accent-alt: #6c5ce7;
    --accent-hum: #00cec9;
    --accent-rssi: #fd79a8;
    --accent-snr: #74b9ff;
    --accent-id: #a29bfe;
    --grid-color: #1e293b;
    --border-color: #30363d;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    background-color: var(--bg-dark);
    color: var(--text-primary);
    padding: 2rem;
    line-height: 1.6;
    min-height: 100vh;
}

.container {
    max-width: 1500px;
    margin: 0 auto;
}

header {
    margin-bottom: 2.5rem;
    text-align: center;
    padding: 2rem 0;
}

h1 {
    font-size: 2.8rem;
    font-weight: 800;
    margin-bottom: 0.5rem;
    background: linear-gradient(135deg, #ff6b6b, #ffd93d, #6c5ce7, #00cec9);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-size: 200% 200%;
    animation: gradientShift 4s ease infinite;
}

@keyframes gradientShift {
    0%, 100% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
}

.subtitle {
    color: var(--text-secondary);
    font-size: 1.1rem;
    margin-bottom: 0.5rem;
}

.meta-info {
    color: var(--text-secondary);
    font-size: 0.9rem;
    opacity: 0.7;
}

/* Summary Stats Cards */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1.2rem;
    margin-bottom: 2.5rem;
}

.card {
    background: var(--bg-card);
    border-radius: 1rem;
    padding: 1.5rem;
    border: 1px solid var(--border-color);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
}

.card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    border-radius: 1rem 1rem 0 0;
}

.card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
    background: var(--bg-card-hover);
}

.card-icon {
    font-size: 1.8rem;
    margin-bottom: 0.5rem;
}

.stat-title {
    color: var(--text-secondary);
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.5rem;
}

.stat-value {
    font-size: 2rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.stat-unit {
    font-size: 0.9rem;
    color: var(--text-secondary);
    font-weight: 500;
}

.stat-details {
    font-size: 0.78rem;
    color: var(--text-secondary);
    margin-top: 0.5rem;
    line-height: 1.6;
}

/* Charts */
.charts-section-title {
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: 1.5rem;
    padding-left: 0.5rem;
    border-left: 4px solid #6c5ce7;
}

.charts-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(550px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
}

.chart-container {
    background: var(--bg-card);
    border-radius: 1rem;
    padding: 1.5rem;
    border: 1px solid var(--border-color);
    height: 380px;
    position: relative;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
    transition: all 0.3s ease;
}

.chart-container:hover {
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.chart-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 0.5rem;
}

.full-width {
    grid-column: 1 / -1;
    height: 420px;
}

footer {
    text-align: center;
    color: var(--text-secondary);
    font-size: 0.85rem;
    padding: 2rem 0;
    border-top: 1px solid var(--border-color);
    margin-top: 2rem;
}

@media (max-width: 768px) {
    .charts-grid { grid-template-columns: 1fr; }
    .stats-grid { grid-template-columns: repeat(2, 1fr); }
    body { padding: 1rem; }
    h1 { font-size: 1.8rem; }
}
"""

# Valid ranges for filtering
VALID_RANGES = {
    "temp": (-40.0, 85.0),
    "pres": (300.0, 1100.0),
    "alt": (-500.0, 10000.0),
    "hum": (0.0, 100.0),
    "rssi": (-150.0, 0.0),
    "snr": (-20.0, 15.0),
}


def is_valid(value, key):
    """Checks if a value is within the valid range."""
    if key not in VALID_RANGES:
        return True
    min_val, max_val = VALID_RANGES[key]
    return min_val <= value <= max_val


def read_data(filepath):
    """Reads data from CSV file."""
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return None

    data = {
        "timestamp": [],
        "packet_id": [],
        "temp": [],
        "pres": [],
        "alt": [],
        "hum": [],
        "arduino_ms": [],
        "rssi": [],
        "snr": [],
    }

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    temp = float(row['temperature_C']) if row['temperature_C'] else None
                    pres = float(row['pressure_hPa']) if row['pressure_hPa'] else None
                    alt = float(row['altitude_m']) if row['altitude_m'] else None
                    hum = float(row['humidity_%']) if row['humidity_%'] else None
                    rssi = float(row['rssi_dBm']) if row['rssi_dBm'] else None
                    snr = float(row['snr_dB']) if row['snr_dB'] else None
                    pkt_id = int(row['packet_id']) if row['packet_id'] else None
                    ard_ms = int(row['arduino_ms']) if row['arduino_ms'] else None
                    ts_str = row['timestamp']

                    # Validate
                    if temp is not None and not is_valid(temp, "temp"):
                        continue
                    if pres is not None and not is_valid(pres, "pres"):
                        continue
                    if alt is not None and not is_valid(alt, "alt"):
                        continue
                    if hum is not None and not is_valid(hum, "hum"):
                        continue

                    data['timestamp'].append(ts_str)
                    data['packet_id'].append(pkt_id if pkt_id is not None else 0)
                    data['temp'].append(temp if temp is not None else 0)
                    data['pres'].append(pres if pres is not None else 0)
                    data['alt'].append(alt if alt is not None else 0)
                    data['hum'].append(hum if hum is not None else 0)
                    data['arduino_ms'].append(ard_ms if ard_ms is not None else 0)
                    data['rssi'].append(rssi if rssi is not None else 0)
                    data['snr'].append(snr if snr is not None else 0)

                except (ValueError, KeyError):
                    continue
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return None

    if not data['timestamp']:
        print("No valid data found in CSV.")
        return None

    return data


def calculate_stats(values):
    """Calculates min, max, avg for a list of values."""
    filtered = [v for v in values if v is not None and v != 0]
    if not filtered:
        return {"min": 0, "max": 0, "avg": 0, "last": 0, "count": 0}
    return {
        "min": min(filtered),
        "max": max(filtered),
        "avg": sum(filtered) / len(filtered),
        "last": filtered[-1],
        "count": len(filtered),
    }


def generate_html(data):
    """Generates the HTML report."""

    stats_temp = calculate_stats(data['temp'])
    stats_pres = calculate_stats(data['pres'])
    stats_alt = calculate_stats(data['alt'])
    stats_hum = calculate_stats(data['hum'])
    stats_rssi = calculate_stats(data['rssi'])
    stats_snr = calculate_stats(data['snr'])

    total_packets = len(data['timestamp'])

    # Duration
    if data['timestamp']:
        first_ts = data['timestamp'][0]
        last_ts = data['timestamp'][-1]
        duration_text = f"{first_ts} → {last_ts}"
    else:
        duration_text = "Sin datos"

    # Prepare JS data
    js_data = json.dumps(data)

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CanSat LoRa SX1262 - Mission Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        {CSS}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🛰️ CanSat LoRa SX1262 Mission Report</h1>
            <div class="subtitle">Telemetría completa de datos de vuelo CanSat España 2026</div>
            <div class="meta-info">{duration_text} • {total_packets} paquetes recibidos</div>
        </header>

        <!-- Summary Stats -->
        <div class="stats-grid">
            <!-- Temperature -->
            <div class="card" style="border-top: 3px solid var(--accent-temp)">
                <div class="card-icon">🌡️</div>
                <div class="stat-title">Temperatura</div>
                <div class="stat-value" style="color: var(--accent-temp)">
                    {stats_temp['last']:.1f}<span class="stat-unit">°C</span>
                </div>
                <div class="stat-details">
                    Min: {stats_temp['min']:.1f}°C • Prom: {stats_temp['avg']:.1f}°C • Max: {stats_temp['max']:.1f}°C
                </div>
            </div>

            <!-- Pressure -->
            <div class="card" style="border-top: 3px solid var(--accent-pres)">
                <div class="card-icon">📊</div>
                <div class="stat-title">Presión</div>
                <div class="stat-value" style="color: var(--accent-pres)">
                    {stats_pres['last']:.1f}<span class="stat-unit">hPa</span>
                </div>
                <div class="stat-details">
                    Min: {stats_pres['min']:.1f} • Prom: {stats_pres['avg']:.1f} • Max: {stats_pres['max']:.1f}
                </div>
            </div>

            <!-- Altitude -->
            <div class="card" style="border-top: 3px solid var(--accent-alt)">
                <div class="card-icon">📍</div>
                <div class="stat-title">Altitud</div>
                <div class="stat-value" style="color: var(--accent-alt)">
                    {stats_alt['last']:.1f}<span class="stat-unit">m</span>
                </div>
                <div class="stat-details">
                    Min: {stats_alt['min']:.1f}m • Prom: {stats_alt['avg']:.1f}m • Max: {stats_alt['max']:.1f}m
                </div>
            </div>

            <!-- Humidity -->
            <div class="card" style="border-top: 3px solid var(--accent-hum)">
                <div class="card-icon">💧</div>
                <div class="stat-title">Humedad</div>
                <div class="stat-value" style="color: var(--accent-hum)">
                    {stats_hum['last']:.1f}<span class="stat-unit">%</span>
                </div>
                <div class="stat-details">
                    Min: {stats_hum['min']:.1f}% • Prom: {stats_hum['avg']:.1f}% • Max: {stats_hum['max']:.1f}%
                </div>
            </div>

            <!-- RSSI -->
            <div class="card" style="border-top: 3px solid var(--accent-rssi)">
                <div class="card-icon">📶</div>
                <div class="stat-title">RSSI</div>
                <div class="stat-value" style="color: var(--accent-rssi)">
                    {stats_rssi['last']:.0f}<span class="stat-unit">dBm</span>
                </div>
                <div class="stat-details">
                    Min: {stats_rssi['min']:.0f} • Prom: {stats_rssi['avg']:.0f} • Max: {stats_rssi['max']:.0f}
                </div>
            </div>

            <!-- SNR -->
            <div class="card" style="border-top: 3px solid var(--accent-snr)">
                <div class="card-icon">📡</div>
                <div class="stat-title">SNR</div>
                <div class="stat-value" style="color: var(--accent-snr)">
                    {stats_snr['last']:.1f}<span class="stat-unit">dB</span>
                </div>
                <div class="stat-details">
                    Min: {stats_snr['min']:.1f} • Prom: {stats_snr['avg']:.1f} • Max: {stats_snr['max']:.1f}
                </div>
            </div>
        </div>

        <!-- Sensor Data Charts -->
        <h2 class="charts-section-title">📈 Datos de Sensores</h2>
        <div class="charts-grid">
            <div class="chart-container">
                <div class="chart-title">🌡️ Temperatura (°C)</div>
                <canvas id="chartTemp"></canvas>
            </div>
            <div class="chart-container">
                <div class="chart-title">📊 Presión (hPa)</div>
                <canvas id="chartPres"></canvas>
            </div>
            <div class="chart-container">
                <div class="chart-title">📍 Altitud (m)</div>
                <canvas id="chartAlt"></canvas>
            </div>
            <div class="chart-container">
                <div class="chart-title">💧 Humedad (%)</div>
                <canvas id="chartHum"></canvas>
            </div>
        </div>

        <!-- Signal Quality Charts -->
        <h2 class="charts-section-title">📡 Calidad de Señal</h2>
        <div class="charts-grid">
            <div class="chart-container">
                <div class="chart-title">📶 RSSI (dBm)</div>
                <canvas id="chartRSSI"></canvas>
            </div>
            <div class="chart-container">
                <div class="chart-title">📡 SNR (dB)</div>
                <canvas id="chartSNR"></canvas>
            </div>
        </div>

        <!-- Correlation Charts -->
        <h2 class="charts-section-title">🔗 Correlaciones</h2>
        <div class="charts-grid">
            <div class="chart-container full-width">
                <div class="chart-title">🌡️📍 Temperatura vs Altitud</div>
                <canvas id="chartTempAlt"></canvas>
            </div>
            <div class="chart-container full-width">
                <div class="chart-title">📊📍 Presión vs Altitud</div>
                <canvas id="chartPresAlt"></canvas>
            </div>
        </div>

        <footer>
            <p>CanSat España 2026 • LoRa SX1262 868 MHz • Report generado automáticamente</p>
        </footer>
    </div>

    <script>
        const rawData = {js_data};

        // Chart.js defaults
        Chart.defaults.color = '#8b949e';
        Chart.defaults.borderColor = '#1e293b';

        const commonOptions = {{
            responsive: true,
            maintainAspectRatio: false,
            interaction: {{
                mode: 'index',
                intersect: false,
            }},
            plugins: {{
                legend: {{ display: false }},
                tooltip: {{
                    backgroundColor: '#111827',
                    titleColor: '#f0f6fc',
                    bodyColor: '#8b949e',
                    borderColor: '#30363d',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false,
                    titleFont: {{ weight: '600' }},
                    bodyFont: {{ family: "'JetBrains Mono', monospace" }},
                    callbacks: {{
                        title: function(items) {{
                            return rawData.timestamp[items[0].dataIndex] || '';
                        }}
                    }}
                }}
            }},
            scales: {{
                x: {{
                    grid: {{ display: false }},
                    ticks: {{
                        maxTicksLimit: 10,
                        maxRotation: 0,
                        font: {{ size: 10 }}
                    }}
                }},
                y: {{
                    grid: {{
                        color: '#1e293b55',
                        drawBorder: false,
                    }},
                    ticks: {{
                        font: {{ size: 10 }}
                    }}
                }}
            }},
            elements: {{
                point: {{
                    radius: 0,
                    hitRadius: 10,
                    hoverRadius: 5
                }},
                line: {{
                    tension: 0.35,
                    borderWidth: 2.5
                }}
            }}
        }};

        function createChart(ctxId, label, dataArr, colorInfo) {{
            const ctx = document.getElementById(ctxId).getContext('2d');
            const gradient = ctx.createLinearGradient(0, 0, 0, 350);
            gradient.addColorStop(0, colorInfo.start);
            gradient.addColorStop(1, colorInfo.end);

            return new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: rawData.timestamp,
                    datasets: [{{
                        label: label,
                        data: dataArr,
                        borderColor: colorInfo.border,
                        backgroundColor: gradient,
                        fill: true,
                        pointBackgroundColor: colorInfo.border,
                    }}]
                }},
                options: commonOptions
            }});
        }}

        // Sensor Charts
        createChart('chartTemp', 'Temperatura (°C)', rawData.temp, {{
            border: '#ff6b6b',
            start: 'rgba(255, 107, 107, 0.4)',
            end: 'rgba(255, 107, 107, 0.0)'
        }});

        createChart('chartPres', 'Presión (hPa)', rawData.pres, {{
            border: '#ffd93d',
            start: 'rgba(255, 217, 61, 0.4)',
            end: 'rgba(255, 217, 61, 0.0)'
        }});

        createChart('chartAlt', 'Altitud (m)', rawData.alt, {{
            border: '#6c5ce7',
            start: 'rgba(108, 92, 231, 0.4)',
            end: 'rgba(108, 92, 231, 0.0)'
        }});

        createChart('chartHum', 'Humedad (%)', rawData.hum, {{
            border: '#00cec9',
            start: 'rgba(0, 206, 201, 0.4)',
            end: 'rgba(0, 206, 201, 0.0)'
        }});

        // Signal Charts
        createChart('chartRSSI', 'RSSI (dBm)', rawData.rssi, {{
            border: '#fd79a8',
            start: 'rgba(253, 121, 168, 0.4)',
            end: 'rgba(253, 121, 168, 0.0)'
        }});

        createChart('chartSNR', 'SNR (dB)', rawData.snr, {{
            border: '#74b9ff',
            start: 'rgba(116, 185, 255, 0.4)',
            end: 'rgba(116, 185, 255, 0.0)'
        }});

        // Scatter: Temp vs Altitude
        const ctxTempAlt = document.getElementById('chartTempAlt').getContext('2d');
        const tempAltData = rawData.temp.map((t, i) => ({{ x: t, y: rawData.alt[i] }}));

        new Chart(ctxTempAlt, {{
            type: 'scatter',
            data: {{
                datasets: [{{
                    label: 'Temp vs Altitud',
                    data: tempAltData,
                    backgroundColor: 'rgba(108, 92, 231, 0.6)',
                    borderColor: '#6c5ce7',
                    pointRadius: 4,
                    pointHoverRadius: 7,
                    pointBorderWidth: 1,
                }}]
            }},
            options: {{
                ...commonOptions,
                scales: {{
                    x: {{
                        title: {{
                            display: true,
                            text: 'Temperatura (°C)',
                            color: '#8b949e',
                            font: {{ weight: '600' }}
                        }},
                        grid: {{ color: '#1e293b55' }}
                    }},
                    y: {{
                        title: {{
                            display: true,
                            text: 'Altitud (m)',
                            color: '#8b949e',
                            font: {{ weight: '600' }}
                        }},
                        grid: {{ color: '#1e293b55' }}
                    }}
                }}
            }}
        }});

        // Scatter: Pressure vs Altitude
        const ctxPresAlt = document.getElementById('chartPresAlt').getContext('2d');
        const presAltData = rawData.pres.map((p, i) => ({{ x: p, y: rawData.alt[i] }}));

        new Chart(ctxPresAlt, {{
            type: 'scatter',
            data: {{
                datasets: [{{
                    label: 'Presión vs Altitud',
                    data: presAltData,
                    backgroundColor: 'rgba(255, 217, 61, 0.6)',
                    borderColor: '#ffd93d',
                    pointRadius: 4,
                    pointHoverRadius: 7,
                    pointBorderWidth: 1,
                }}]
            }},
            options: {{
                ...commonOptions,
                scales: {{
                    x: {{
                        title: {{
                            display: true,
                            text: 'Presión (hPa)',
                            color: '#8b949e',
                            font: {{ weight: '600' }}
                        }},
                        grid: {{ color: '#1e293b55' }}
                    }},
                    y: {{
                        title: {{
                            display: true,
                            text: 'Altitud (m)',
                            color: '#8b949e',
                            font: {{ weight: '600' }}
                        }},
                        grid: {{ color: '#1e293b55' }}
                    }}
                }}
            }}
        }});

    </script>
</body>
</html>
"""

    # Ensure output directory exists
    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)

    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"[OK] Report generado: {os.path.abspath(OUTPUT_HTML)}")
    print(f"[OK] Total datos: {total_packets} paquetes")
    print(f"[OK] Abre el archivo en tu navegador para ver las gráficas interactivas.")


if __name__ == "__main__":
    data = read_data(CSV_FILE)
    if data:
        generate_html(data)
