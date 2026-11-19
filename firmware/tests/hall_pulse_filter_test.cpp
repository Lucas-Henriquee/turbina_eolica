#include <cassert>
#include <iostream>
#include "hall_pulse_filter.h"

int main() {
  HallPulseFilter filter(1000, 3000000, 0.25);
  assert(filter.snapshot(100).periodUs == 0);
  for (int64_t time = 1000000; time <= 2500000; time += 500000) filter.observe(time);
  assert(filter.snapshot(2500000).periodUs == 500000);

  // Pulso extra semelhante ao pico observado no ensaio.
  filter.observe(2539240);
  auto state = filter.snapshot(2539240);
  assert(state.periodUs == 500000);
  assert(state.rawPeriodUs == 39240);
  assert(state.rejectedPulses == 1);
  filter.observe(3000000);
  assert(filter.snapshot(3000000).periodUs == 500000);

  // Ruído abaixo de 1 ms não altera a referência temporal.
  filter.observe(3000100);
  assert(filter.snapshot(3000100).rejectedPulses == 2);
  filter.observe(3500000);
  assert(filter.snapshot(3500000).periodUs == 500000);

  // Aceleração real de 120 para 240 RPM permanece mensurável.
  filter.observe(3750000);
  filter.observe(4000000);
  assert(filter.snapshot(4000000).periodUs == 250000);

  // Uma volta perdida não duplica o período filtrado.
  filter.observe(4500000);
  assert(filter.snapshot(4500000).periodUs == 250000);
  filter.observe(4750000);
  assert(filter.snapshot(4750000).periodUs == 250000);

  assert(filter.snapshot(7750001).periodUs == 0);
  filter.observe(9000000);
  assert(filter.snapshot(9000000).periodUs == 0);
  filter.observe(9500000);
  filter.observe(10000000);
  assert(filter.snapshot(10000000).periodUs == 0);
  filter.observe(10500000);
  assert(filter.snapshot(10500000).periodUs == 500000);

  // Não usa o intervalo de uma parada longa para calcular RPM.
  HallPulseFilter startup(1000, 3000000, 0.25);
  startup.observe(1000000);
  startup.observe(130000000);
  assert(startup.snapshot(130000000).rawPeriodUs == 0);
  assert(startup.snapshot(130000000).periodUs == 0);

  // A mediana reduz um pulso extra antes de estabilizar a janela.
  HallPulseFilter earlyNoise(1000, 3000000, 0.25);
  for (int64_t time : {1000000, 1500000, 1539240, 2000000, 2500000}) earlyNoise.observe(time);
  assert(earlyNoise.snapshot(2500000).periodUs == 460760);
  earlyNoise.observe(3000000);
  assert(earlyNoise.snapshot(3000000).periodUs == 500000);

  std::cout << "PASS: steady rotation, extra pulses, acceleration, missed pulse, timeout and restart\n";
}
