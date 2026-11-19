const getElement = (id) => document.getElementById(id);
let state = { connected: false, recording: null },
  live = [],
  archive = null,
  activeId = null,
  archiveSource = null;
let total = 0,
  lastSequence = null,
  serverOnline = false;
let savedRuns = [],
  gaugeRange = 300,
  chartPointer = null;
const chartField = () => getElement('plotField').value;
const formatValue = (value) =>
  value == null ? '--' : Number(value).toLocaleString('en-US', { maximumFractionDigits: 3 });
const showMessage = (message, error = false) => {
  getElement('message').textContent = message;
  getElement('message').classList.toggle('error', error);
};

async function requestApi(route, options) {
  const response = await fetch(
    route,
    options
      ? {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(options),
        }
      : {},
  );
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'Request failed');
  return result;
}

async function runAction(callback) {
  try {
    await callback();
  } catch (error) {
    showMessage(error.message, true);
  }
}

function updateReadings(row) {
  getElement('rpm').textContent = formatValue(row?.rpm);
  getElement('voltage').textContent = formatValue(row?.load_voltage_V);
  getElement('current').textContent = formatValue(row?.current_A);
  getElement('power').textContent = formatValue(row?.electrical_power_W);
  getElement('energy').textContent = formatValue(row?.electrical_energy_J);
  gaugeRange = Math.max(gaugeRange, Math.ceil((row?.rpm || 0) / 100) * 100);
  const max = gaugeRange;
  getElement('gaugeMax').textContent = max;
  const ratio = row?.rpm == null ? 0 : Math.min(1, row.rpm / max);
  getElement('needle').style.transform = `rotate(${ratio * 240}deg)`;
  getElement('needle').style.opacity = row?.rpm == null ? '0' : '1';
  getElement('gaugeFill').style.strokeDashoffset = 100 - ratio * 100;
}

function renderDashboard() {
  const row = archive ? archive.at(-1) : state.sample;
  updateReadings(row);
  const source = archive
    ? `SAVED · ${(archiveSource || 'unknown').toUpperCase()}`
    : !state.connected
      ? 'Disconnected'
      : state.source === 'demo'
        ? 'DEMO · generated data'
        : 'USB · ESP32';
  getElement('sourceBadge').textContent = source;
  getElement('sourceBadge').className =
    `badge ${archive ? (archiveSource === 'demo' ? 'demo' : 'usb') : state.connected ? state.source : ''}`;
  if (state.connected) getElement('source').value = state.source;
  getElement('connect').disabled = state.connected || !serverOnline;
  getElement('disconnect').disabled = !state.connected || !serverOnline;
  getElement('source').disabled = state.connected;
  getElement('port').disabled = state.connected || getElement('source').value === 'demo';
  getElement('start').disabled =
    !state.connected || !state.sample || !!state.recording || !serverOnline;
  getElement('stop').disabled = !state.recording || !serverOnline;
  for (const id of ['runName', 'rotor', 'material', 'wind', 'fanDistance', 'windSource', 'notes'])
    getElement(id).disabled = !!state.recording;
  getElement('addWindPoint').disabled = !!state.recording;
  for (const control of getElement('windProfileRows').querySelectorAll('input, button'))
    control.disabled = !!state.recording;
  getElement('recordState').textContent = state.recording
    ? `Recording · ${state.recording.name}`
    : 'Not recording';
  getElement('sensorStatus').textContent =
    `Hall: ${row?.hall_status || '--'} · Electrical: ${row?.electrical_status || '--'}` +
    (row?.hall_rejected_pulses != null ? ` · Hall rejected: ${row.hall_rejected_pulses}` : '');
  getElement('sampleStatus').textContent =
    `${archive ? archive.length : total} samples · ${row?.missing_packets || 0} lost · ${formatValue(row?.integrated_duration_s)} s integrated`;
  getElement('returnLive').hidden = !archive;
  const hallStatus = row?.hall_status;
  getElement('hallState').textContent =
    hallStatus === 'ok'
      ? 'Pulses detected'
      : hallStatus === 'no_pulse'
        ? 'No recent pulses'
        : hallStatus === 'not_configured'
          ? 'Sensor not configured'
          : 'Waiting for pulses';
  getElement('hallDot').className =
    `status-dot ${hallStatus === 'ok' ? 'ok' : hallStatus === 'no_pulse' ? 'warning' : ''}`;
  document.querySelector('.recording').classList.toggle('active', !!state.recording);
  updateTimer();
  drawTrends();
  drawChart();
}

async function refreshPorts() {
  const ports = await requestApi('/api/ports');
  const selected = getElement('port').value;
  getElement('port').replaceChildren(new Option('Select port', ''));
  for (const port of ports.filter((port) => !port.path.startsWith('/dev/ttyS'))) {
    getElement('port').add(
      new Option(`${port.path} · ${port.friendlyName || port.manufacturer || 'Serial'}`, port.path),
    );
  }
  if ([...getElement('port').options].some((option) => option.value === selected))
    getElement('port').value = selected;
  else if (getElement('port').options.length === 2) getElement('port').selectedIndex = 1;
}

async function refreshHistory() {
  savedRuns = await requestApi('/api/runs');
  renderHistory();
}

function renderHistory() {
  const query = getElement('historySearch').value.trim().toLocaleLowerCase();
  const runs = savedRuns.filter((run) => (run.name || run.id).toLocaleLowerCase().includes(query));
  getElement('historyCount').textContent = savedRuns.length;
  const container = getElement('history');
  container.replaceChildren();
  if (!runs.length) {
    const p = document.createElement('p');
    p.textContent = query ? 'No matching runs.' : 'Your experiments will appear here.';
    p.className = 'muted';
    container.append(p);
  }
  for (const run of runs) {
    const item = document.createElement('div');
    item.className = `history-run ${activeId === run.id ? 'selected' : ''}`;
    const title = document.createElement('strong');
    title.textContent = run.name || run.id;
    const detail = document.createElement('p');
    const date = new Date(run.started_at_utc);
    detail.textContent = `${run.source?.toUpperCase() || 'USB'} · ${run.status}\n${Number.isNaN(date.getTime()) ? '' : date.toLocaleString()}${run.ended_at_utc ? ` · ${formatDuration((new Date(run.ended_at_utc) - date) / 1000)}` : ''}`;
    detail.style.whiteSpace = 'pre-line';
    const view = document.createElement('button');
    view.textContent = 'View';
    view.onclick = () => runAction(() => openRun(run));
    const download = document.createElement('a');
    download.textContent = 'CSV';
    download.href = `/api/runs/${encodeURIComponent(run.id)}/csv`;
    const setup = document.createElement('a');
    setup.textContent = 'Setup';
    setup.href = `/api/runs/${encodeURIComponent(run.id)}/metadata`;
    setup.title = 'Download run parameters (JSON)';
    item.append(title, detail, view, download, setup);
    container.append(item);
  }
}

async function openRun(run) {
  const response = await fetch(`/api/runs/${encodeURIComponent(run.id)}/csv`);
  if (!response.ok) throw Error('Could not open saved run');
  const lines = (await response.text()).trim().split(/\r?\n/);
  const fields = lines.shift().split(',');
  archive = lines.filter(Boolean).map((line) => {
    const values = line.split(',');
    return Object.fromEntries(
      fields.map((field, i) => [
        field,
        values[i] === ''
          ? null
          : Number.isFinite(Number(values[i]))
            ? Number(values[i])
            : values[i],
      ]),
    );
  });
  activeId = run.id;
  archiveSource = run.source;
  gaugeRange = 300;
  getElement('plotWindow').value = 'all';
  getElement('plotTitle').textContent = run.name || run.id;
  getElement('plotDetail').textContent =
    `${run.source?.toUpperCase()} · ${archive.length} saved samples · ${run.status}` +
    (run.fan_distance_m != null ? ` · Fan distance ${formatValue(run.fan_distance_m)} m` : '') +
    (run.wind_speed_m_s != null ? ` · Wind ${formatValue(run.wind_speed_m_s)} m/s (${run.wind_speed_source === 'anemometer' ? 'anemometer' : 'nominal / estimated'})` : '') +
    (run.wind_speed_profile?.length ? ` · Wind reference: ${run.wind_speed_profile.map((point) => `${formatValue(point.time_s)} s → ${formatValue(point.speed_m_s)} m/s`).join('; ')} (previous value held)` : '') +
    (run.notes ? ` · ${run.notes}` : '');
  showMessage('Viewing a saved run. Live acquisition continues if connected.');
  renderDashboard();
  await refreshHistory();
}

function showLive() {
  archive = null;
  activeId = null;
  archiveSource = null;
  getElement('plotWindow').value = '60';
  getElement('plotTitle').textContent = 'Live readings';
  getElement('plotDetail').textContent = 'Last 60 seconds';
  renderDashboard();
  runAction(refreshHistory);
}

function formatDuration(seconds) {
  const totalSeconds = Math.max(0, Math.floor(seconds || 0));
  const minutes = Math.floor(totalSeconds / 60);
  return `${String(minutes).padStart(2, '0')}:${String(totalSeconds % 60).padStart(2, '0')}`;
}

function updateTimer() {
  const startedAt = state.recording?.started_at_utc;
  getElement('recordTimer').textContent = formatDuration(
    startedAt ? (Date.now() - new Date(startedAt)) / 1000 : 0,
  );
}

function samplesAreAdjacent(previous, row) {
  return (
    previous &&
    row.sequence === previous.sequence + 1 &&
    row.device_time_s - previous.device_time_s <= 0.5
  );
}

function drawTrends() {
  const rows = (archive || live).slice(-80);
  for (const [id, field] of [
    ['voltage', 'load_voltage_V'],
    ['current', 'current_A'],
    ['power', 'electrical_power_W'],
    ['energy', 'electrical_energy_J'],
  ]) {
    const target = getElement(`${id}Trend`);
    const values = rows
      .map((row) => row[field])
      .filter((value) => value != null && Number.isFinite(value));
    target.replaceChildren();
    if (!values.length) continue;
    const low = Math.min(...values),
      high = Math.max(...values);
    const span = high - low || Math.max(Math.abs(high) * 0.1, 1e-6);
    let path = '',
      previous = null;
    rows.forEach((row, i) => {
      if (row[field] == null || !Number.isFinite(row[field])) {
        previous = null;
        return;
      }
      const x = (i / Math.max(1, rows.length - 1)) * 240;
      const y = high === low ? 16 : 28 - ((row[field] - low) / span) * 24;
      path += `${samplesAreAdjacent(previous, row) ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)} `;
      previous = row;
    });
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    line.setAttribute('d', path);
    target.append(line);
  }
}

function drawChart() {
  const canvas = getElement('chart'),
    context = canvas.getContext('2d');
  const width = canvas.clientWidth,
    height = canvas.clientHeight;
  if (!width || !height) return;
  const scale = window.devicePixelRatio || 1;
  const theme = getComputedStyle(document.documentElement);
  canvas.width = width * scale;
  canvas.height = height * scale;
  context.scale(scale, scale);
  context.clearRect(0, 0, width, height);
  const field = chartField(),
    rows = archive || live;
  const windowValue = getElement('plotWindow').value;
  const end = Math.max(1, rows.at(-1)?.elapsed_s || 1);
  const begin =
    windowValue === 'all' ? rows[0]?.elapsed_s || 0 : Math.max(0, end - Number(windowValue));
  const visible = rows.filter((row) => row.elapsed_s >= begin);
  const valid = visible.filter((row) => row[field] != null && Number.isFinite(row[field]));
  const values = valid.map((row) => row[field]);
  const minimum = values.length
    ? values.reduce((result, value) => Math.min(result, value), Infinity)
    : null;
  const maximum = values.length
    ? values.reduce((result, value) => Math.max(result, value), -Infinity)
    : null;
  const average = values.length
    ? values.reduce((sum, value) => sum + value, 0) / values.length
    : null;
  getElement('chartMin').textContent = formatValue(minimum);
  getElement('chartMax').textContent = formatValue(maximum);
  getElement('chartMean').textContent = formatValue(average);
  getElement('chartLegend').textContent = {
    rpm: 'Rotational speed · RPM',
    rpm_raw: 'Raw rotational speed · RPM',
    load_voltage_V: 'Load voltage · V',
    current_A: 'Current · A',
    electrical_power_W: 'Electrical power · W',
  }[field];
  if (!archive)
    getElement('plotDetail').textContent =
      windowValue === 'all' ? 'Available session samples' : `Last ${windowValue} seconds`;
  const low = Math.min(0, minimum || 0),
    high = Math.max(maximum || 0, 1e-6) * 1.12;
  const left = 51,
    right = width - 12,
    top = 12,
    bottom = height - 25;
  const xAt = (row) =>
    left + ((row.elapsed_s - begin) / Math.max(end - begin, 1e-6)) * (right - left);
  const yAt = (row) => bottom - ((row[field] - low) / (high - low)) * (bottom - top);
  context.font = '10px monospace';
  context.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = top + ((bottom - top) * i) / 4;
    context.strokeStyle = theme.getPropertyValue('--chart-grid').trim();
    context.beginPath();
    context.moveTo(left, y);
    context.lineTo(right, y);
    context.stroke();
    context.fillStyle = theme.getPropertyValue('--chart-text').trim();
    context.fillText(formatValue(high - ((high - low) * i) / 4), 0, y + 3);
    const time = begin + ((end - begin) * i) / 4;
    const x = left + ((right - left) * i) / 4;
    context.fillText(`${time.toFixed(1)} s`, Math.min(x, right - 43), height - 5);
  }
  const tooltip = getElement('chartTooltip');
  tooltip.hidden = true;
  if (!values.length) {
    context.fillStyle = '#8b969f';
    context.textAlign = 'center';
    context.fillText('Waiting for valid measurements', (left + right) / 2, (top + bottom) / 2);
    return;
  }
  context.strokeStyle = theme.getPropertyValue('--chart-line').trim();
  context.lineWidth = 1.8;
  context.beginPath();
  let previous = null;
  // Preserva as lacunas entre amostras inválidas ou perdidas.
  for (const row of visible) {
    if (row[field] == null || !Number.isFinite(row[field])) {
      previous = null;
      continue;
    }
    if (samplesAreAdjacent(previous, row)) context.lineTo(xAt(row), yAt(row));
    else context.moveTo(xAt(row), yAt(row));
    previous = row;
  }
  context.stroke();
  if (chartPointer != null && chartPointer >= left && chartPointer <= right) {
    const targetTime = begin + ((chartPointer - left) / (right - left)) * (end - begin);
    const closest = valid.reduce((best, row) =>
      Math.abs(row.elapsed_s - targetTime) < Math.abs(best.elapsed_s - targetTime) ? row : best,
    );
    const x = xAt(closest),
      y = yAt(closest);
    context.strokeStyle = '#5c7163';
    context.setLineDash([3, 4]);
    context.beginPath();
    context.moveTo(x, top);
    context.lineTo(x, bottom);
    context.stroke();
    context.setLineDash([]);
    context.fillStyle = '#c6e0cf';
    context.beginPath();
    context.arc(x, y, 3.5, 0, Math.PI * 2);
    context.fill();
    tooltip.textContent = `${formatValue(closest[field])} · ${getElement('plotField').selectedOptions[0].textContent}\n${closest.elapsed_s.toFixed(2)} s`;
    tooltip.hidden = false;
    tooltip.style.left = `${Math.max(0, Math.min(x + 12, width - tooltip.offsetWidth - 4))}px`;
    tooltip.style.top = `${Math.max(0, y - 48)}px`;
  }
}

function addWindPoint() {
  const rows = getElement('windProfileRows');
  if (rows.children.length >= 100) return;
  const row = document.createElement('tr');
  for (const [key, label] of [['time_s', 'Elapsed time in seconds'], ['speed_m_s', 'Wind speed in metres per second']]) {
    const cell = document.createElement('td');
    const input = document.createElement('input');
    input.type = 'number';
    input.min = '0';
    input.step = 'any';
    input.required = true;
    input.dataset.key = key;
    input.setAttribute('aria-label', label);
    if (key === 'time_s' && !rows.children.length) input.value = '0';
    cell.append(input);
    row.append(cell);
  }
  const cell = document.createElement('td');
  const remove = document.createElement('button');
  remove.textContent = '×';
  remove.className = 'quiet';
  remove.type = 'button';
  remove.setAttribute('aria-label', 'Remove wind reference point');
  remove.onclick = () => row.remove();
  cell.append(remove);
  row.append(cell);
  rows.append(row);
}

getElement('addWindPoint').onclick = addWindPoint;
getElement('historySearch').oninput = renderHistory;
getElement('plotWindow').onchange = () => {
  chartPointer = null;
  drawChart();
};
getElement('chart').addEventListener('pointermove', (event) => {
  chartPointer = event.clientX - event.currentTarget.getBoundingClientRect().left;
  drawChart();
});
getElement('chart').addEventListener('pointerleave', () => {
  chartPointer = null;
  drawChart();
});
setInterval(updateTimer, 1000);

getElement('refreshPorts').onclick = () => runAction(refreshPorts);
getElement('refreshHistory').onclick = () => runAction(refreshHistory);
getElement('source').onchange = renderDashboard;
getElement('connect').onclick = () =>
  runAction(async () => {
    live = [];
    total = 0;
    lastSequence = null;
    gaugeRange = 300;
    showLive();
    await requestApi('/api/connect', {
      source: getElement('source').value,
      port: getElement('port').value,
    });
  });
getElement('disconnect').onclick = () => runAction(() => requestApi('/api/disconnect', {}));
getElement('start').onclick = () =>
  runAction(async () => {
    for (const id of ['runName', 'wind', 'fanDistance']) {
      if (!getElement(id).reportValidity()) return;
    }
    const windProfile = [];
    for (const row of getElement('windProfileRows').children) {
      const point = {};
      for (const input of row.querySelectorAll('input')) {
        if (!input.reportValidity()) {
          getElement('windProfileDetails').open = true;
          input.reportValidity();
          return;
        }
        point[input.dataset.key] = Number(input.value);
      }
      windProfile.push(point);
    }
    await requestApi('/api/start', {
      name: getElement('runName').value,
      rotor_name: getElement('rotor').value,
      material: getElement('material').value,
      wind_speed_m_s: getElement('wind').value,
      wind_speed_source: getElement('windSource').value,
      fan_distance_m: getElement('fanDistance').value,
      notes: getElement('notes').value,
      wind_speed_profile: windProfile,
    });
    live = [];
    total = 0;
    lastSequence = null;
    showLive();
    await refreshHistory();
  });
getElement('stop').onclick = () =>
  runAction(async () => {
    await requestApi('/api/stop', {});
    showMessage('Run saved. Find it in the history.');
    await refreshHistory();
  });
getElement('returnLive').onclick = showLive;
getElement('plotField').onchange = drawChart;
window.addEventListener('resize', drawChart);
const events = new EventSource('/api/events');
events.onopen = () => {
  serverOnline = true;
  renderDashboard();
};
events.onerror = () => {
  serverOnline = false;
  let savedRuns = [],
    gaugeRange = 300,
    chartPointer = null;
  updateReadings(null);
  showMessage('Server connection lost. Waiting to reconnect.', true);
  getElement('start').disabled =
    getElement('stop').disabled =
    getElement('connect').disabled =
      true;
};
events.onmessage = (event) => {
  const previousId = state.recording?.id;
  state = JSON.parse(event.data);
  serverOnline = true;
  if (state.sample && state.sample.sequence !== lastSequence) {
    if (previousId !== state.recording?.id && state.recording) {
      live = [];
      total = 0;
    }
    live.push(state.sample);
    if (live.length > 1500) live.shift();
    total++;
    lastSequence = state.sample.sequence;
  }
  if (!archive)
    showMessage(
      state.message,
      !state.connected && state.message !== 'Ready' && state.message !== 'Disconnected',
    );
  renderDashboard();
  if (previousId && !state.recording) runAction(refreshHistory);
};
await runAction(async () => {
  const config = await requestApi('/api/config');
  getElement('rotor').value = config.rotor_name;
  getElement('material').value = config.material;
  getElement('wind').value = config.wind_speed_m_s;
  getElement('fanDistance').value = config.fan_distance_m ?? '';
  getElement('windSource').value = config.wind_speed_source === 'anemometer' ? 'anemometer' : 'manual';
  getElement('notes').value = config.notes || '';
  await refreshPorts();
  await refreshHistory();
});
setInterval(() => runAction(refreshHistory), 10000);
