# MQ-2 Pollution Sensor Project

This folder contains the code for the CanSat MQ-2 pollution sensor mission.

## Structure

- **arduino/**: Contains the Arduino sketch (`mq2_pollution.ino`).
- **python/**: Contains Python scripts for the dashboard and report generation.
- **data/**: Stores the logged data (`mq2_data.csv`) and generated reports (`mq2_report.html`).

## How to Run

### 1. Arduino
You can upload the code directly from the terminal using `arduino-cli`.

**Step 1: Check your connection**
Find which port your Arduino is connected to (e.g., COM5, COM9).
```powershell
..\arduino-cli.exe board list
```

**Step 2: Compile**
```powershell
..\arduino-cli.exe compile --fqbn arduino:renesas_uno:unor4wifi mq2/arduino/mq2_pollution/mq2_pollution.ino
```

**Step 3: Upload**
Replace `COM9` with your actual port.
```powershell
..\arduino-cli.exe upload -p COM9 --fqbn arduino:renesas_uno:unor4wifi mq2/arduino/mq2_pollution/mq2_pollution.ino
```

### 2. Dashboard
1.  Open a terminal in the `python` folder (or root).
2.  Run the dashboard script using the Python Launcher:
    ```bash
    cd mq2
    cd python
    py mq2_dashboard.py
    ```

### 3. Generate Report
To generate an HTML report from the collected data:
```bash
py generate_mq2_report.py
```
The report will be saved to `data/mq2_report.html`.
