import csv
import json
import os
import statistics

# Configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CSV_FILE = os.path.join(DATA_DIR, "mq2_data.csv")
OUTPUT_HTML = os.path.join(DATA_DIR, "mq2_report.html")

# CSS Styles (Embedded for standalone file)
CSS = """
:root {
    --bg-dark: #0f172a;
    --bg-card: #1e293b;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --accent-safe: #4caf50;
    --accent-warn: #ffeb3b;
    --accent-danger: #f43f5e;
    --accent-raw: #60a5fa;
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
    background: linear-gradient(to right, #4caf50, #f43f5e);
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

def read_data(filepath):
    """Reads data from CSV file."""
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return None

    data = {
        "timestamp": [],
        "gas_raw": [],
        "pollution_percent": []
    }

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Parse timestamp
                    ts_str = row['timestamp']
                    data['timestamp'].append(ts_str)

                    data['gas_raw'].append(float(row['gas_raw']))
                    data['pollution_percent'].append(float(row['pollution_percent']))
                except (ValueError, KeyError):
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

def get_pollution_color(percent):
    if percent < 30: return "#4caf50" # Green
    if percent < 60: return "#ffeb3b" # Yellow
    return "#f43f5e" # Red

def generate_html(data):
    """Generates the HTML report."""
    
    # Calculate stats
    stats_raw = calculate_stats(data['gas_raw'])
    stats_poll = calculate_stats(data['pollution_percent'])
    
    current_color = get_pollution_color(stats_poll['last'])

    # Prepare data for JS
    js_data = json.dumps(data)

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CanSat MQ-2 Pollution Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        {CSS}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>CanSat MQ-2 Mission Report</h1>
            <div class="subtitle">Monitoreo de Calidad de Aire y Gases</div>
        </header>

        <!-- Summary Cards -->
        <div class="stats-grid">
            <!-- Pollution Percent -->
            <div class="card" style="border-top: 4px solid {current_color}">
                <div class="stat-title">Nivel de Contaminación</div>
                <div class="stat-value" style="color: {current_color}">
                    {stats_poll['last']:.1f}<span class="stat-unit">%</span>
                </div>
                <div class="subtitle" style="font-size: 0.85rem; margin-top: 0.5rem">
                    Prom: {stats_poll['avg']:.1f} • Max: {stats_poll['max']:.1f}
                </div>
            </div>

            <!-- Gas Raw -->
            <div class="card" style="border-top: 4px solid var(--accent-raw)">
                <div class="stat-title">Valor Sensor (Raw)</div>
                <div class="stat-value" style="color: var(--accent-raw)">
                    {stats_raw['last']:.0f}<span class="stat-unit">/1023</span>
                </div>
                <div class="subtitle" style="font-size: 0.85rem; margin-top: 0.5rem">
                    Prom: {stats_raw['avg']:.1f} • Max: {stats_raw['max']:.0f}
                </div>
            </div>
        </div>

        <!-- Charts -->
        <div class="charts-grid">
            <div class="chart-container">
                <div class="chart-title">Nivel de Contaminación (%)</div>
                <canvas id="chartPollution"></canvas>
            </div>
            <div class="chart-container">
                <div class="chart-title">Lectura Cruda del Sensor</div>
                <canvas id="chartRaw"></canvas>
            </div>
            
            <!-- Scatter (Full Width) -->
            <div class="chart-container" style="grid-column: 1 / -1;">
                <div class="chart-title">Relación: Raw Value vs Contaminación %</div>
                <canvas id="chartScatter"></canvas>
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
                    tension: 0.4, 
                    borderWidth: 2
                }}
            }}
        }};

        function createChart(ctxId, label, data, colorInfo) {{
            const ctx = document.getElementById(ctxId).getContext('2d');
            
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

        // Pollution Chart
        createChart('chartPollution', 'Contaminación (%)', rawData.pollution_percent, {{
            border: '{current_color}',
            start: '{current_color}80', // 50% opacity hex approximation
            end: '{current_color}00'
        }});

        // Raw Value Chart
        createChart('chartRaw', 'Raw Value', rawData.gas_raw, {{
            border: '#60a5fa',
            start: 'rgba(96, 165, 250, 0.5)',
            end: 'rgba(96, 165, 250, 0.0)'
        }});

        // Scatter Chart
        const ctxScatter = document.getElementById('chartScatter').getContext('2d');
        const scatterData = rawData.gas_raw.map((r, i) => ({{ x: r, y: rawData.pollution_percent[i] }}));
        
        new Chart(ctxScatter, {{
            type: 'scatter',
            data: {{
                datasets: [{{
                    label: 'Raw vs %',
                    data: scatterData,
                    backgroundColor: '#f43f5e',
                    borderColor: '#f43f5e',
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
                            text: 'Valor Raw Sensor',
                            color: '#94a3b8'
                        }},
                        grid: {{
                            color: '#33415555'
                        }}
                    }},
                    y: {{
                        title: {{
                            display: true,
                            text: 'Contaminación (%)',
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
