import csv
import json
import os
import statistics

# Configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CSV_FILE = os.path.join(DATA_DIR, "bmp280_data.csv")
OUTPUT_HTML = os.path.join(DATA_DIR, "report.html")

# CSS Styles (Embedded for standalone file)
CSS = """
:root {
    --bg-dark: #0f172a;
    --bg-card: #1e293b;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --accent-temp: #f43f5e;
    --accent-hum: #06b6d4;
    --accent-pres: #eab308;
    --accent-alt: #8b5cf6;
    --grid-color: #334155;
}

body {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    background-color: var(--bg-dark);
    color: var(--text-primary);
    margin: 0;
    padding: 2rem;
    line-height: 1.5;
}

.container {
    max-width: 1400px;
    margin: 0 auto;
}

header {
    margin-bottom: 2rem;
    text-align: center;
}

h1 {
    font-size: 2.5rem;
    font-weight: 800;
    margin-bottom: 0.5rem;
    background: linear-gradient(to right, #60a5fa, #c084fc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.subtitle {
    color: var(--text-secondary);
    font-size: 1.1rem;
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
}

.card {
    background-color: var(--bg-card);
    border-radius: 1rem;
    padding: 1.5rem;
    border: 1px solid var(--grid-color);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    transition: transform 0.2s;
}

.card:hover {
    transform: translateY(-2px);
}

.stat-title {
    color: var(--text-secondary);
    font-size: 0.875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.5rem;
}

.stat-value {
    font-size: 2rem;
    font-weight: 700;
}

.stat-unit {
    font-size: 1rem;
    color: var(--text-secondary);
    font-weight: 500;
}

.charts-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(600px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
}

.chart-container {
    background-color: var(--bg-card);
    border-radius: 1rem;
    padding: 1.5rem;
    border: 1px solid var(--grid-color);
    height: 400px;
    position: relative;
}

.chart-title {
    position: absolute;
    top: 1rem;
    left: 1.5rem;
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text-primary);
    z-index: 10;
}

@media (max-width: 768px) {
    .charts-grid {
        grid-template-columns: 1fr;
    }
    body {
        padding: 1rem;
    }
}
"""

# Filtering Configuration (Matched with Dashboard)
BASELINE_ALTITUDE = 650.0
ALTITUDE_TOLERANCE = 500.0

VALID_RANGES = {
    "alt": (BASELINE_ALTITUDE - ALTITUDE_TOLERANCE, BASELINE_ALTITUDE + ALTITUDE_TOLERANCE),
    "temp": (-40.0, 85.0),
    "pres": (300.0, 1100.0),
}

def is_valid(value, key):
    """Checks if a value is within the valid range for the given key."""
    min_val, max_val = VALID_RANGES[key]
    return min_val <= value <= max_val

def read_data(filepath):
    """Reads data from CSV file."""
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return None

    data = {
        "timestamp": [],
        "temp": [],
        "pres": [],
        "alt": []
    }

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Parse values
                    temp = float(row['temperature_C'])
                    pres = float(row['pressure_hPa'])
                    alt = float(row['altitude_m'])
                    ts_str = row['timestamp']

                    # Filter invalid values (Cribado de datos excesivos/erróneos)
                    if not (is_valid(temp, "temp") and 
                            is_valid(pres, "pres") and 
                            is_valid(alt, "alt")):
                        continue

                    # Append only if all values are valid
                    data['timestamp'].append(ts_str)
                    data['temp'].append(temp)
                    data['pres'].append(pres)
                    data['alt'].append(alt)

                except (ValueError, KeyError) as e:
                    # Skip malformed lines
                    continue
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return None

    return data

def calculate_stats(values):
    """Calculates min, max, avg for a list of values."""
    if not values:
        return {"min": 0, "max": 0, "avg": 0, "last": 0}
    return {
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
        "last": values[-1]
    }

def generate_html(data):
    """Generates the HTML report."""
    
    # Calculate stats
    stats_temp = calculate_stats(data['temp'])
    stats_pres = calculate_stats(data['pres'])
    stats_alt = calculate_stats(data['alt'])

    # Prepare data for JS
    js_data = json.dumps(data)

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CanSat BMP280 Data Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        {CSS}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>CanSat BMP280 Mission Report</h1>
            <div class="subtitle">Visualización de datos de telemetría</div>
        </header>

        <!-- Summary Cards -->
        <div class="stats-grid">
            <!-- Temperature -->
            <div class="card" style="border-top: 4px solid var(--accent-temp)">
                <div class="stat-title">Temperatura</div>
                <div class="stat-value" style="color: var(--accent-temp)">
                    {stats_temp['last']:.1f}<span class="stat-unit">°C</span>
                </div>
                <div class="subtitle" style="font-size: 0.85rem; margin-top: 0.5rem">
                    Prom: {stats_temp['avg']:.1f} • Max: {stats_temp['max']:.1f}
                </div>
            </div>

            <!-- Pressure -->
            <div class="card" style="border-top: 4px solid var(--accent-pres)">
                <div class="stat-title">Presión</div>
                <div class="stat-value" style="color: var(--accent-pres)">
                    {stats_pres['last']:.1f}<span class="stat-unit">hPa</span>
                </div>
                <div class="subtitle" style="font-size: 0.85rem; margin-top: 0.5rem">
                    Prom: {stats_pres['avg']:.1f} • Min: {stats_pres['min']:.1f}
                </div>
            </div>

            <!-- Altitude -->
            <div class="card" style="border-top: 4px solid var(--accent-alt)">
                <div class="stat-title">Altitud</div>
                <div class="stat-value" style="color: var(--accent-alt)">
                    {stats_alt['last']:.1f}<span class="stat-unit">m</span>
                </div>
                <div class="subtitle" style="font-size: 0.85rem; margin-top: 0.5rem">
                    Prom: {stats_alt['avg']:.1f} • Max: {stats_alt['max']:.1f}
                </div>
            </div>
        </div>

        <!-- Charts -->
        <div class="charts-grid">
            <div class="chart-container">
                <div class="chart-title">Temperatura (°C)</div>
                <canvas id="chartTemp"></canvas>
            </div>
            <div class="chart-container">
                <div class="chart-title">Presión (hPa)</div>
                <canvas id="chartPres"></canvas>
            </div>
            <div class="chart-container">
                <div class="chart-title">Altitud (m)</div>
                <canvas id="chartAlt"></canvas>
            </div>
            
            <!-- Temp vs Altitude (Full Width) -->
            <div class="chart-container" style="grid-column: 1 / -1;">
                <div class="chart-title">Temperatura vs Altitud</div>
                <canvas id="chartTempAlt"></canvas>
            </div>
        </div>
    </div>

    <script>
        const rawData = {js_data};
        
        // Common Chart Options
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.borderColor = '#334155';
        
        const commonOptions = {{
            responsive: true,
            maintainAspectRatio: false,
            interaction: {{
                mode: 'index',
                intersect: false,
            }},
            plugins: {{
                legend: {{
                    display: false
                }},
                tooltip: {{
                    backgroundColor: '#1e293b',
                    titleColor: '#f8fafc',
                    bodyColor: '#cbd5e1',
                    borderColor: '#334155',
                    borderWidth: 1,
                    padding: 10,
                    displayColors: false
                }}
            }},
            scales: {{
                x: {{
                    grid: {{
                        display: false
                    }},
                    ticks: {{
                        maxTicksLimit: 8,
                        maxRotation: 0
                    }}
                }},
                y: {{
                    grid: {{
                        color: '#33415555'
                    }}
                }}
            }},
            elements: {{
                point: {{
                    radius: 0,
                    hitRadius: 10,
                    hoverRadius: 4
                }},
                line: {{
                    tension: 0.4, // Smooth curves
                    borderWidth: 2
                }}
            }}
        }};

        // Create Chart Function
        function createChart(ctxId, label, data, colorInfo) {{
            const ctx = document.getElementById(ctxId).getContext('2d');
            
            // Create Gradient
            const gradient = ctx.createLinearGradient(0, 0, 0, 400);
            gradient.addColorStop(0, colorInfo.start);
            gradient.addColorStop(1, colorInfo.end);

            return new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: rawData.timestamp,
                    datasets: [{{
                        label: label,
                        data: data,
                        borderColor: colorInfo.border,
                        backgroundColor: gradient,
                        fill: true
                    }}]
                }},
                options: commonOptions
            }});
        }}

        // Render Charts
        createChart('chartTemp', 'Temperatura', rawData.temp, {{
            border: '#f43f5e',
            start: 'rgba(244, 63, 94, 0.5)', 
            end: 'rgba(244, 63, 94, 0.0)'
        }});



        createChart('chartPres', 'Presión', rawData.pres, {{
            border: '#eab308',
            start: 'rgba(234, 179, 8, 0.5)',
            end: 'rgba(234, 179, 8, 0.0)'
        }});

        createChart('chartAlt', 'Altitud', rawData.alt, {{
            border: '#8b5cf6',
            start: 'rgba(139, 92, 246, 0.5)',
            end: 'rgba(139, 92, 246, 0.0)'
        }});

        // Scatter Chart: Temp vs Altitude
        const ctxTempAlt = document.getElementById('chartTempAlt').getContext('2d');
        const tempAltData = rawData.temp.map((t, i) => ({{ x: t, y: rawData.alt[i] }}));
        
        new Chart(ctxTempAlt, {{
            type: 'scatter',
            data: {{
                datasets: [{{
                    label: 'Temp vs Altitud',
                    data: tempAltData,
                    backgroundColor: '#8b5cf6',
                    borderColor: '#8b5cf6',
                    pointRadius: 4,
                    pointHoverRadius: 6
                }}]
            }},
            options: {{
                ...commonOptions,
                scales: {{
                    x: {{
                        title: {{
                            display: true,
                            text: 'Temperatura (°C)',
                            color: '#94a3b8'
                        }},
                        grid: {{
                            color: '#33415555'
                        }}
                    }},
                    y: {{
                        title: {{
                            display: true,
                            text: 'Altitud (m)',
                            color: '#94a3b8'
                        }},
                        grid: {{
                            color: '#33415555'
                        }}
                    }}
                }}
            }}
        }});

    </script>
</body>
</html>
"""
    
    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Report generated successfully: {os.path.abspath(OUTPUT_HTML)}")

if __name__ == "__main__":
    data = read_data(CSV_FILE)
    if data:
        generate_html(data)
