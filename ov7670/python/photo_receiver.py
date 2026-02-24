# ============================================================================
# OV7670 BASIC PHOTO RECEIVER
# ============================================================================
# Recibe fotos del Arduino y las muestra en pantalla.
# 
# Uso:
#   1. Sube ov7670_basic_capture.ino al Arduino
#   2. Ejecuta este script: python photo_receiver.py
#   3. Presiona 'p' en la ventana para capturar una foto
#   4. Presiona 'q' para salir
# ============================================================================

import serial
import serial.tools.list_ports
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.widgets import Button
import time
import os

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

BAUD_RATE = 115200
IMG_WIDTH = 40
IMG_HEIGHT = 30

# Directorio para guardar fotos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ============================================================================
# DETECCIÓN DE ARDUINO
# ============================================================================

def find_arduino():
    """Busca el puerto del Arduino"""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        desc = (port.description or "").lower()
        hwid = (port.hwid or "").lower()
        if "2341" in hwid or "arduino" in desc or "ch340" in desc:
            print(f"[INFO] Arduino encontrado en {port.device}")
            return port.device
    if ports:
        print(f"[INFO] Usando primer puerto: {ports[0].device}")
        return ports[0].device
    return None

# ============================================================================
# CONVERSIÓN RGB565 -> RGB888
# ============================================================================

def rgb565_to_rgb888(high_byte, low_byte):
    """Convierte RGB565 a RGB888"""
    rgb565 = (high_byte << 8) | low_byte
    r = ((rgb565 >> 11) & 0x1F) << 3
    g = ((rgb565 >> 5) & 0x3F) << 2
    b = (rgb565 & 0x1F) << 3
    return r, g, b

# ============================================================================
# RECEPCIÓN DE FOTO
# ============================================================================

def receive_photo(ser):
    """Recibe una foto del Arduino"""
    print("[INFO] Esperando foto...")
    
    # Crear imagen vacía
    image = np.zeros((IMG_HEIGHT, IMG_WIDTH, 3), dtype=np.uint8)
    
    # Enviar comando de captura
    ser.write(b'p')
    
    timeout = time.time() + 10  # 10 segundos timeout
    photo_started = False
    lines_received = 0
    
    while time.time() < timeout:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            
            if not line:
                continue
                
            print(f"  <- {line[:60]}{'...' if len(line) > 60 else ''}")
            
            if line == "PHOTO_START":
                photo_started = True
                print("[INFO] Iniciando recepción de foto...")
                
            elif line.startswith("SIZE:"):
                parts = line.split(":")[1].split("x")
                w, h = int(parts[0]), int(parts[1])
                print(f"[INFO] Tamaño: {w}x{h}")
                
            elif line.startswith("LINE:"):
                line_num = int(line.split(":")[1])
                
            elif line.startswith("ERROR:"):
                print(f"[ERROR] {line}")
                return None
                
            elif photo_started and len(line) > 10 and all(c in '0123456789ABCDEFabcdef' for c in line):
                # Esta es una línea de datos hexadecimales
                try:
                    # Convertir hex a bytes
                    data = bytes.fromhex(line)
                    
                    # Procesar píxeles
                    if lines_received < IMG_HEIGHT:
                        for i in range(0, min(len(data), IMG_WIDTH * 2), 2):
                            pixel_idx = i // 2
                            if pixel_idx < IMG_WIDTH:
                                r, g, b = rgb565_to_rgb888(data[i], data[i+1])
                                image[lines_received, pixel_idx] = [r, g, b]
                        
                        lines_received += 1
                        
                except Exception as e:
                    print(f"[WARN] Error procesando línea: {e}")
                    
            elif line == "PHOTO_END":
                print(f"[OK] Foto recibida: {lines_received} líneas")
                return image
                
            elif line.startswith("LINES_READ:"):
                total = int(line.split(":")[1])
                print(f"[INFO] Total líneas: {total}")
    
    print("[ERROR] Timeout esperando foto")
    return image if lines_received > 0 else None

# ============================================================================
# GUARDAR FOTO
# ============================================================================

def save_photo(image, filename=None):
    """Guarda la foto como PNG"""
    if filename is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(DATA_DIR, f"photo_{timestamp}.png")
    
    plt.imsave(filename, image)
    print(f"[OK] Foto guardada: {filename}")
    return filename

# ============================================================================
# INTERFAZ GRÁFICA
# ============================================================================

class PhotoViewer:
    def __init__(self, ser):
        self.ser = ser
        self.current_image = None
        
        # Crear figura
        plt.style.use('dark_background')
        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        self.fig.canvas.manager.set_window_title("OV7670 Photo Capture")
        
        # Imagen inicial
        self.img_display = self.ax.imshow(
            np.zeros((IMG_HEIGHT, IMG_WIDTH, 3), dtype=np.uint8),
            interpolation='nearest'
        )
        self.ax.set_title("Presiona 'p' para capturar foto", fontsize=14)
        self.ax.axis('off')
        
        # Texto de estado
        self.status_text = self.fig.text(
            0.5, 0.02, "Listo - Presiona 'p' para capturar, 's' para guardar, 'q' para salir",
            ha='center', fontsize=10, color='#888888'
        )
        
        # Eventos de teclado
        self.fig.canvas.mpl_connect('key_press_event', self.on_key)
        
        # Contador de fotos
        self.photo_count = 0
        
    def on_key(self, event):
        if event.key == 'p':
            self.capture_photo()
        elif event.key == 't':
            self.capture_test()
        elif event.key == 's':
            if self.current_image is not None:
                save_photo(self.current_image)
                self.status_text.set_text("Foto guardada!")
                self.fig.canvas.draw()
        elif event.key == 'q':
            plt.close()
            
    def capture_photo(self):
        self.status_text.set_text("Capturando foto...")
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()
        
        image = receive_photo(self.ser)
        
        if image is not None:
            self.current_image = image
            self.img_display.set_data(image)
            self.photo_count += 1
            self.ax.set_title(f"Foto #{self.photo_count} - {IMG_WIDTH}x{IMG_HEIGHT}", fontsize=14)
            self.status_text.set_text("Foto recibida! 'p'=capturar, 's'=guardar, 'q'=salir")
        else:
            self.status_text.set_text("Error capturando foto")
            
        self.fig.canvas.draw()
        
    def capture_test(self):
        """Captura con barras de color de test"""
        self.status_text.set_text("Capturando test (barras de color)...")
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()
        
        self.ser.write(b't')
        time.sleep(0.1)
        
        image = receive_photo(self.ser)
        
        if image is not None:
            self.current_image = image
            self.img_display.set_data(image)
            self.ax.set_title("TEST - Barras de color", fontsize=14)
            self.status_text.set_text("Test recibido! 'p'=capturar normal, 's'=guardar")
        else:
            self.status_text.set_text("Error en test")
            
        self.fig.canvas.draw()
        
    def run(self):
        plt.tight_layout()
        plt.subplots_adjust(bottom=0.1)
        plt.show()

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("OV7670 PHOTO RECEIVER")
    print("=" * 50)
    
    port = find_arduino()
    if not port:
        print("[ERROR] No se encontró Arduino")
        exit(1)
    
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=1)
        print(f"[OK] Conectado a {port}")
        time.sleep(2)  # Esperar reset del Arduino
        
        # Leer mensajes iniciales
        print("[INFO] Mensajes del Arduino:")
        start = time.time()
        while time.time() - start < 2:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(f"  {line}")
        
        print()
        print("Controles:")
        print("  p = Capturar foto")
        print("  t = Test (barras de color)")
        print("  s = Guardar foto")
        print("  q = Salir")
        print()
        
        # Iniciar visor
        viewer = PhotoViewer(ser)
        viewer.run()
        
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("[INFO] Puerto cerrado")
