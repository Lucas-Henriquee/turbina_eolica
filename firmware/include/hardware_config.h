#pragma once

constexpr unsigned long SERIAL_BAUD = 115200;            // Baud; comunicação USB.
constexpr unsigned long SAMPLE_INTERVAL_MS = 100;        // ms; intervalo de amostragem.
constexpr int HALL_PIN = 27;                             // GPIO; sinal do conversor.
constexpr int I2C_SDA_PIN = 21;                          // GPIO; dados do INA219.
constexpr int I2C_SCL_PIN = 22;                          // GPIO; relógio do INA219.
constexpr int STATUS_LED_PIN = 2;                        // GPIO; LED de gravação.
constexpr unsigned long RECORD_TIMEOUT_MS = 3000;       // ms; apaga o LED sem comandos.
constexpr unsigned char INA219_ADDRESS = 0x40;           // Endereço I²C do INA219.
constexpr double SHUNT_RESISTANCE_OHM = 0.1;             // Ω; resistência do shunt.
constexpr unsigned int PULSES_PER_REVOLUTION = 1;        // Pulsos do Hall por volta.
constexpr int64_t MIN_PULSE_INTERVAL_US = 1000;          // µs; rejeita pulsos mais próximos.
constexpr int64_t PULSE_TIMEOUT_US = 3000000;            // µs; prazo para indicar no_pulse.

constexpr bool HALL_WIRING_VERIFIED = true;              // Habilita Hall após validar o sinal.
constexpr bool INA219_SHUNT_VERIFIED = true;             // Habilita INA219 após validar o shunt.
