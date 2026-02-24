#include <RadioLib.h>

// --- CONFIGURACIÓN DE PINES (Arduino Uno R4) ---
// NSS pin:   10
// DIO1 pin:  2
// NRST pin:  9
// BUSY pin:  3
SX1262 radio = new Module(10, 2, 9, 3);

// Pines para el control de la antena (DX-PJ27)
#define RXEN_PIN 5
#define TXEN_PIN 6

// Bandera para saber si llegó un paquete (volatile porque se usa en una interrupción)
volatile bool receivedFlag = false;

// Esta función se ejecuta automáticamente cuando llega un mensaje
#if defined(ESP8266) || defined(ESP32)
  ICACHE_RAM_ATTR
#endif
void setFlag(void) {
  receivedFlag = true;
}

void setup() {
  Serial.begin(115200);
  while(!Serial); // Esperar al monitor serie

  Serial.println("Iniciando Receptor DX-LR20...");

  // Configurar pines de antena para que RadioLib los maneje
  radio.setRfSwitchPins(RXEN_PIN, TXEN_PIN);

  // --- INICIALIZACIÓN (Debe ser IDÉNTICA al Transmisor) ---
  // Freq: 433.0 MHz (o 915.0 según tu módulo)
  // BW: 125.0 kHz
  // SF: 9
  // CR: 7
  // SyncWord: 0x12
  // Power: 10 dBm
  int state = radio.begin(433.0, 125.0, 9, 7, 0x12, 10);

  if (state == RADIOLIB_ERR_NONE) {
    Serial.println("¡Módulo iniciado con éxito!");
   
    // Configurar la interrupción para cuando llegue un paquete
    radio.setDio1Action(setFlag);

    // Empezar a escuchar (modo recepción continua)
    state = radio.startReceive();
    if (state == RADIOLIB_ERR_NONE) {
      Serial.println("Escuchando...");
    } else {
      Serial.print("Error al iniciar recepción, código: ");
      Serial.println(state);
    }
  } else {
    Serial.print("Error al iniciar el módulo, código: ");
    Serial.println(state);
    while (true);
  }
}

void loop() {
  // Si la bandera está activada, es que llegó un mensaje
  if(receivedFlag) {
    // Reiniciamos la bandera
    receivedFlag = false;

    String str;
    // Leer los datos recibidos
    int state = radio.readData(str);

    if (state == RADIOLIB_ERR_NONE) {
      // Imprimir el mensaje
      Serial.println("--------------------------------");
      Serial.print("Mensaje recibido: ");
      Serial.println(str);

      // Imprimir datos de calidad de señal
      Serial.print("RSSI (Fuerza): ");
      Serial.print(radio.getRSSI());
      Serial.println(" dBm");
     
      Serial.print("SNR (Calidad): ");
      Serial.print(radio.getSNR());
      Serial.println(" dB");
    } else if (state == RADIOLIB_ERR_CRC_MISMATCH) {
      Serial.println("Error: CRC incorrecto (Datos corruptos)");
    } else {
      Serial.print("Error leyendo datos, código: ");
      Serial.println(state);
    }

    // Volver a poner el módulo en modo escucha
    radio.startReceive();
  }
}