import test from 'node:test';
import assert from 'node:assert/strict';
import { validateSample, Measurements, demoSample, columns } from '../measurements.js';

test('preserves filtered and raw RPM with pulse diagnostics', () => {
  const sample = {
    ...demoSample(10, 1, 10),
    rpm: 120,
    rpm_raw: 1529,
    hall_accepted_pulses: 20,
    hall_rejected_pulses: 1,
    hall_filter: {
      algorithm: 'median3_relative_gate_v1', window_periods: 3,
      min_interval_us: 1000, min_period_ratio: 0.25,
      timeout_us: 3000000, pulses_per_revolution: 1,
    },
  };
  const row = new Measurements().add(validateSample(sample), 'usb');
  assert.equal(row.rpm, 120);
  assert.equal(row.rpm_raw, 1529);
  assert.equal(row.hall_rejected_pulses, 1);
  assert.deepEqual(row.hall_filter, sample.hall_filter);
  assert.equal(row.electrical_power_W, sample.load_voltage_V * sample.current_A);
  for (const key of ['rpm_raw', 'hall_accepted_pulses', 'hall_rejected_pulses'])
    assert.ok(columns.includes(key));
});

test('accepts old firmware and demo packets without Hall diagnostics', () => {
  const row = new Measurements().add(validateSample(demoSample(10, 1, 10)), 'usb');
  assert.equal(row.rpm_raw, null);
  assert.equal(row.hall_rejected_pulses, null);
  assert.equal(row.hall_filter, null);
});

test('rejects invalid diagnostic fields', () => {
  const sample = demoSample(10, 1, 10);
  for (const invalid of [{ rpm_raw: -1 }, { hall_rejected_pulses: 1.5 }, { hall_filter: {} }])
    assert.throws(() => validateSample({ ...sample, ...invalid }));
});

test('does not turn missing Hall pulses into zero or discard electrical energy', () => {
  const model = new Measurements();
  const sample = { ...demoSample(10, 1, 10), rpm: null, hall_status: 'no_pulse', rpm_raw: null };
  model.add(validateSample(sample), 'usb');
  const row = model.add(validateSample({ ...sample, sequence: 2, device_time_us: 10100000 }), 'usb');
  assert.equal(row.rpm, null);
  assert.ok(row.electrical_energy_J > 0);
});
