/*
 * MQ-2 Pollution Sensor for CanSat
 * Reads analog value from Pin A0 and sends it via Serial.
 * 
 * Connections:
 *   VCC -> 5V (MQ-2 needs 5V normally, check your module)
 *   GND -> GND
 *   AO  -> A0 (Analog Output)
 */

#define SENSOR_PIN A0
#define READ_INTERVAL 500 // ms

void setup() {
  Serial.begin(115200);
  pinMode(SENSOR_PIN, INPUT);
  
  Serial.println("MQ-2 Gas Sensor Initialized");
  delay(2000); // Warmup
}

void loop() {
  int raw_value = analogRead(SENSOR_PIN);
  
  // Mapping raw value (0-1023) to a rough percentage (0-100)
  // Adjust MAX_VAL based on calibration in clean air vs gas
  int pollution_percent = map(raw_value, 0, 1023, 0, 100);
  
  Serial.print("gas_raw=");
  Serial.print(raw_value);
  Serial.print(",pollution_percent=");
  Serial.println(pollution_percent);
  
  delay(READ_INTERVAL);
}
