export const columns = [
  'received_at_utc',
  'source',
  'sequence',
  'device_time_s',
  'elapsed_s',
  'rpm',
  'omega_rad_s',
  'load_voltage_V',
  'current_A',
  'electrical_power_W',
  'electrical_energy_J',
  'integrated_duration_s',
  'hall_status',
  'electrical_status',
  'missing_packets',
];

export function validateSample(sample) {
  if (!sample || sample.protocol !== 1) throw Error('Unsupported packet');
  for (const key of ['sequence', 'device_time_us']) {
    if (!Number.isSafeInteger(sample[key]) || sample[key] < 0)
      throw Error('Invalid timestamp or sequence');
  }
  for (const key of ['hall_status', 'electrical_status']) {
    if (typeof sample[key] !== 'string' || !/^[a-z_]{1,80}$/.test(sample[key]))
      throw Error('Invalid sensor status');
  }
  for (const key of ['rpm', 'load_voltage_V', 'current_A']) {
    if (sample[key] != null && (typeof sample[key] !== 'number' || !Number.isFinite(sample[key]))) {
      throw Error('Invalid measurement');
    }
  }
  const data = { ...sample };
  if (data.hall_status === 'ok') {
    if (data.rpm == null || data.rpm < 0) throw Error('Invalid RPM');
  } else data.rpm = null;
  if (data.electrical_status === 'ok') {
    if (data.load_voltage_V == null || data.current_A == null)
      throw Error('Missing electrical measurement');
  } else data.load_voltage_V = data.current_A = null;
  return data;
}

export class Measurements {
  constructor(maxGap = 0.5) {
    this.maxGap = maxGap;
    this.previous = null;
    this.firstTime = null;
    this.energy = 0;
    this.coverage = 0;
    this.missing = 0;
    this.count = 0;
  }

  add(sample, source) {
    const time = sample.device_time_us / 1e6;
    const previous = this.previous;
    if (previous && (time <= previous.device_time_s || sample.sequence <= previous.sequence)) {
      throw Error('Device restarted or samples arrived out of order');
    }
    this.firstTime ??= time;
    const power =
      sample.electrical_status === 'ok' ? sample.load_voltage_V * sample.current_A : null;
    if (previous) {
      const dt = time - previous.device_time_s;
      const missed = sample.sequence - previous.sequence - 1;
      this.missing += missed;
      // Integra apenas amostras consecutivas.
      if (!missed && dt <= this.maxGap && power !== null && previous.electrical_power_W !== null) {
        this.energy += ((power + previous.electrical_power_W) * dt) / 2;
        this.coverage += dt;
      }
    }
    const row = {
      received_at_utc: new Date().toISOString(),
      source,
      sequence: sample.sequence,
      device_time_s: time,
      elapsed_s: time - this.firstTime,
      rpm: sample.rpm,
      omega_rad_s: sample.rpm === null ? null : (sample.rpm * 2 * Math.PI) / 60,
      load_voltage_V: sample.load_voltage_V,
      current_A: sample.current_A,
      electrical_power_W: power,
      electrical_energy_J: this.energy,
      integrated_duration_s: this.coverage,
      hall_status: sample.hall_status,
      electrical_status: sample.electrical_status,
      missing_packets: this.missing,
    };
    this.previous = row;
    this.count++;
    return row;
  }
}

export function demoSample(elapsed, sequence, resistance) {
  const rpm = 190 * (1 - Math.exp(-elapsed / 8));
  const voltage = rpm * 0.005;
  return {
    protocol: 1,
    sequence,
    device_time_us: Math.round(elapsed * 1e6),
    rpm,
    load_voltage_V: voltage,
    current_A: voltage / resistance,
    hall_status: 'ok',
    electrical_status: 'ok',
  };
}
