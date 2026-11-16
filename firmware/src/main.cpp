#include <Arduino.h>
#include <Wire.h>
#include <esp_timer.h>
#include "hardware_config.h"

// Protege dados compartilhados com a interrupção.
portMUX_TYPE pulseMux = portMUX_INITIALIZER_UNLOCKED;
volatile int64_t lastPulseUs = 0;
volatile int64_t pulsePeriodUs = 0;
uint32_t sequence = 0;
unsigned long lastSampleMs = 0;
bool inaReady = false;
unsigned long lastRecordCommandMs = 0;
bool recordingLed = false;

void scanI2c() {
  if (!INA219_SHUNT_VERIFIED) return;
  Serial.printf("I2C idle SDA=%d SCL=%d\n", digitalRead(I2C_SDA_PIN), digitalRead(I2C_SCL_PIN));
  if (digitalRead(I2C_SDA_PIN) && digitalRead(I2C_SCL_PIN)) {
    for (uint8_t address = 0x08; address <= 0x77; address++) {
      Wire.beginTransmission(address);
      if (Wire.endTransmission() == 0) Serial.printf("I2C found 0x%02X\n", address);
    }
  }
  Serial.println("I2C scan done");
}

void setRecordingLed(bool enabled) {
  recordingLed = enabled;
  digitalWrite(STATUS_LED_PIN, enabled ? HIGH : LOW);
}

void readCommands() {
  static char command[32];
  static size_t length = 0;
  static bool overflow = false;
  for (int count = 0; count < 128 && Serial.available(); count++) {
    const char value = Serial.read();
    if (value == '\n') {
      command[length] = '\0';
      if (!overflow) {
        if (strcmp(command, "RECORD_START") == 0) {
          lastRecordCommandMs = millis();
          setRecordingLed(true);
        } else if (strcmp(command, "SCAN_I2C") == 0 && !recordingLed) {
          scanI2c();
        } else if (strcmp(command, "RECORD_STOP") == 0) {
          setRecordingLed(false);
        } else if (strcmp(command, "RECORD_PING") == 0 && recordingLed) {
          lastRecordCommandMs = millis();
        }
      }
      length = 0;
      overflow = false;
    } else if (value != '\r') {
      if (length < sizeof(command) - 1) command[length++] = value;
      else overflow = true;
    }
  }
}

void ARDUINO_ISR_ATTR onPulse() {
  const int64_t now = esp_timer_get_time();
  portENTER_CRITICAL_ISR(&pulseMux);
  const int64_t elapsed = now - lastPulseUs;
  if (elapsed >= MIN_PULSE_INTERVAL_US) {
    pulsePeriodUs = lastPulseUs > 0 ? elapsed : 0;
    lastPulseUs = now;
  }
  portEXIT_CRITICAL_ISR(&pulseMux);
}

bool writeRegister(uint8_t reg, uint16_t value) {
  Wire.beginTransmission(INA219_ADDRESS);
  Wire.write(reg);
  Wire.write(value >> 8);
  Wire.write(value & 0xff);
  return Wire.endTransmission() == 0;
}

bool readRegister(uint8_t reg, uint16_t &value) {
  Wire.beginTransmission(INA219_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(INA219_ADDRESS, static_cast<uint8_t>(2)) != 2) return false;
  const uint8_t high = Wire.read();
  const uint8_t low = Wire.read();
  value = (high << 8) | low;
  return true;
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW);
  if (HALL_WIRING_VERIFIED) {
    pinMode(HALL_PIN, INPUT);
    attachInterrupt(digitalPinToInterrupt(HALL_PIN), onPulse, FALLING);
  }
  if (INA219_SHUNT_VERIFIED) {
    Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
    Wire.setTimeOut(50);
    // Faixa de 32 V, shunt de ±320 mV e conversão contínua de 12 bits.
    inaReady = writeRegister(0x00, 0x399f);
  }
}

void loop() {
  const unsigned long nowMs = millis();
  readCommands();
  if (recordingLed && millis() - lastRecordCommandMs > RECORD_TIMEOUT_MS) setRecordingLed(false);
  if (nowMs - lastSampleMs < SAMPLE_INTERVAL_MS) return;
  lastSampleMs = nowMs;
  const int64_t timestampUs = esp_timer_get_time();
  int64_t lastPulse, period;
  portENTER_CRITICAL(&pulseMux);
  lastPulse = lastPulseUs;
  period = pulsePeriodUs;
  portEXIT_CRITICAL(&pulseMux);

  const char *hallStatus = "not_configured";
  double rpm = 0;
  if (HALL_WIRING_VERIFIED) {
    hallStatus = "waiting_for_pulses";
    if (lastPulse > 0 && period > 0 && timestampUs - lastPulse <= PULSE_TIMEOUT_US) {
      rpm = 60000000.0 / (period * PULSES_PER_REVOLUTION);
      hallStatus = "ok";
    } else if (lastPulse > 0 && timestampUs - lastPulse > PULSE_TIMEOUT_US) {
      hallStatus = "no_pulse";
    }
  }

  const char *electricalStatus = "not_configured";
  double voltage = 0, current = 0;
  if (INA219_SHUNT_VERIFIED) {
    uint16_t bus = 0, shunt = 0;
    electricalStatus = "sensor_error";
    if (inaReady && readRegister(0x02, bus) && readRegister(0x01, shunt)) {
      const int16_t signedShunt = static_cast<int16_t>(shunt);
      if ((bus & 0x0002) == 0) {
        electricalStatus = "not_ready";
      } else if ((bus >> 3) * 0.004 > 26.0 || abs(signedShunt) >= 31900) {
        electricalStatus = "out_of_range";
      } else {
        voltage = (bus >> 3) * 0.004;
        // Calcula corrente pela queda no shunt.
        current = signedShunt * 0.00001 / SHUNT_RESISTANCE_OHM;
        electricalStatus = "ok";
      }
    }
  }

  // Falhas são enviadas como null.
  Serial.printf("{\"protocol\":1,\"sequence\":%lu,\"device_time_us\":%lld,",
                static_cast<unsigned long>(sequence++), static_cast<long long>(timestampUs));
  Serial.print("\"rpm\":");
  if (strcmp(hallStatus, "ok") == 0) Serial.print(rpm, 6);
  else Serial.print("null");
  Serial.print(",\"load_voltage_V\":");
  if (strcmp(electricalStatus, "ok") == 0) Serial.print(voltage, 6);
  else Serial.print("null");
  Serial.print(",\"current_A\":");
  if (strcmp(electricalStatus, "ok") == 0) Serial.print(current, 6);
  else Serial.print("null");
  Serial.printf(",\"hall_status\":\"%s\",\"electrical_status\":\"%s\",\"recording_led\":%s}\n",
                hallStatus, electricalStatus, recordingLed ? "true" : "false");
}
