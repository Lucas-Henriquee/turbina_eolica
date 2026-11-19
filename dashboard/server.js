import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { performance } from 'node:perf_hooks';
import { SerialPort } from 'serialport';
import { columns, validateSample, Measurements, demoSample } from './measurements.js';
import { createLogger } from './logger.js';

const root = path.dirname(fileURLToPath(import.meta.url));
const logger = createLogger(process.env.BENCH_LOG_DIR || path.join(root, 'logs'));
function exitWithError(error) {
  logger.error('server_failed', error instanceof Error ? error : new Error(String(error)));
  console.error(`[FAIL] Dashboard server. Log: ${logger.file}`);
  process.exit(1);
}
process.on('uncaughtException', exitWithError);
process.on('unhandledRejection', exitWithError);
const config = JSON.parse(fs.readFileSync(path.join(root, 'config.json')));
const dataRoot = process.env.BENCH_DATA_DIR || path.resolve(root, config.output_directory);
const portNumber = Number(process.env.BENCH_PORT || 8765);
fs.mkdirSync(dataRoot, { recursive: true });
const clients = new Set();
let serial = null,
  timer = null,
  staleTimer = null,
  connecting = false;
let session = null,
  receivedAt = 0,
  invalidPackets = 0;
let model = new Measurements(config.max_energy_gap_s);
let state = {
  connected: false,
  source: null,
  message: 'Ready',
  sample: null,
  recording: null,
  invalid_packets: 0,
};
const safeId = /^[a-zA-Z0-9_-]+$/;

function history() {
  return fs
    .readdirSync(dataRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .flatMap((entry) => {
      if (!safeId.test(entry.name)) return [];
      try {
        const metadata = JSON.parse(
          fs.readFileSync(path.join(dataRoot, entry.name, 'metadata.json')),
        );
        return [{ ...metadata, id: entry.name }];
      } catch {
        return [];
      }
    })
    .sort((a, b) => (b.started_at_utc || '').localeCompare(a.started_at_utc || ''));
}

// Recupera gravações interrompidas.
for (const run of history()) {
  if (run.status === 'recording') {
    run.status = 'interrupted';
    logger.warn('recording_recovered', { id: run.id });
    fs.writeFileSync(path.join(dataRoot, run.id, 'metadata.json'), JSON.stringify(run, null, 2));
  }
}

function broadcast() {
  state.invalid_packets = invalidPackets;
  const message = `data: ${JSON.stringify(state)}\n\n`;
  for (const client of clients) {
    if (client.writableLength > 1024 * 1024) {
      client.destroy();
      clients.delete(client);
    } else client.write(message);
  }
}

function sendCommand(command) {
  const activePort = serial;
  if (!activePort?.isOpen) return;
  activePort.write(`${command}\n`, (error) => {
    if (error && serial === activePort) disconnect('USB command failed');
  });
}

function stopRecording(status = 'stopped') {
  sendCommand('RECORD_STOP');
  if (!session) return;
  session.metadata.status = status;
  session.metadata.ended_at_utc = new Date().toISOString();
  session.metadata.samples = model.count;
  session.metadata.missing_packets = model.missing;
  session.metadata.electrical_energy_J = model.energy;
  session.metadata.integrated_duration_s = model.coverage;
  fs.closeSync(session.fd);
  fs.writeFileSync(session.metadataPath, JSON.stringify(session.metadata, null, 2));
  logger.info('recording_stopped', {
    id: session.metadata.id,
    status,
    samples: model.count,
    invalid_packets: invalidPackets,
  });
  session = null;
  state.recording = null;
}

function disconnect(reason = 'Disconnected') {
  if (state.connected) logger.info('disconnected', { source: state.source, reason });
  clearInterval(timer);
  clearInterval(staleTimer);
  timer = staleTimer = null;
  stopRecording(reason === 'Disconnected' ? 'stopped' : reason);
  const previous = serial;
  serial = null;
  if (previous?.isOpen) previous.drain(() => previous.close(() => {}));
  state = { ...state, connected: false, sample: null, recording: null, message: reason };
  broadcast();
}

function receive(sample) {
  try {
    const row = model.add(sample, state.source);
    if (session) {
      fs.writeSync(session.fd, columns.map((key) => row[key] ?? '').join(',') + '\n');
      session.metadata.samples = model.count;
    }
    receivedAt = performance.now();
    state.sample = row;
    state.device_recording_led =
      typeof sample.recording_led === 'boolean' ? sample.recording_led : null;
    state.message = 'Receiving';
    broadcast();
  } catch (error) {
    logger.error('acquisition_failed', error);
    disconnect(error.message);
  }
}

async function connect(options) {
  if (connecting) throw Error('Connection in progress');
  if (!['demo', 'usb'].includes(options.source)) throw Error('Select Demo or USB');
  connecting = true;
  try {
    disconnect();
    model = new Measurements(config.max_energy_gap_s);
    invalidPackets = 0;
    state.source = options.source;
    if (options.source === 'usb') {
      const ports = await SerialPort.list();
      if (!ports.some((port) => port.path === options.port)) throw Error('Serial port not found');
      serial = new SerialPort({ path: options.port, baudRate: config.baud_rate, autoOpen: false });
      const activePort = serial;
      await new Promise((resolve, reject) =>
        activePort.open((error) => (error ? reject(error) : resolve())),
      );
      // Remonta pacotes divididos entre leituras USB.
      let buffer = '';
      activePort.on('data', (chunk) => {
        if (serial !== activePort) return;
        buffer += chunk.toString('utf8');
        if (buffer.length > 65536) return disconnect('Serial buffer exceeded limit');
        let end;
        while ((end = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, end);
          buffer = buffer.slice(end + 1);
          try {
            receive(validateSample(JSON.parse(line)));
          } catch {
            invalidPackets++;
          }
          if (!state.connected) break;
        }
      });
      activePort.on('error', (error) => {
        if (serial === activePort) disconnect(error.message);
      });
      activePort.on('close', () => {
        if (serial === activePort) disconnect('USB disconnected');
      });
    } else {
      const start = performance.now();
      let sequence = 0;
      timer = setInterval(
        () =>
          receive(
            demoSample((performance.now() - start) / 1000, sequence++, config.load_resistance_ohm),
          ),
        config.sample_interval_ms,
      );
    }
    receivedAt = performance.now();
    state.connected = true;
    state.message = 'Waiting for data';
    logger.info('connected', { source: options.source, port: options.port || null });
    staleTimer = setInterval(() => {
      // Mantém o LED ativo durante a gravação USB.
      if (session && state.source === 'usb') sendCommand('RECORD_PING');
      if (performance.now() - receivedAt > config.stale_timeout_s * 1000)
        disconnect('No valid data');
    }, 500);
    broadcast();
  } catch (error) {
    disconnect(error.message);
    throw error;
  } finally {
    connecting = false;
  }
}

function startRecording(options) {
  if (!state.connected || !state.sample) throw Error('Connect and wait for data first');
  if (session) throw Error('A recording is already running');
  const name = String(options.name || '').trim();
  if (!name || name.length > 80 || /[\x00-\x1f]/.test(name))
    throw Error('Enter a run name (1–80 characters)');
  const wind = Number(options.wind_speed_m_s);
  if (
    options.wind_speed_m_s == null || String(options.wind_speed_m_s).trim() === '' ||
    !Number.isFinite(wind) || wind < 0
  )
    throw Error('Enter a valid wind speed');
  const distance = Number(options.fan_distance_m);
  if (
    options.fan_distance_m == null || String(options.fan_distance_m).trim() === '' ||
    !Number.isFinite(distance) || distance <= 0
  )
    throw Error('Enter the fan distance in metres (greater than zero)');
  const windSource = options.wind_speed_source || 'manual';
  if (!['manual', 'anemometer'].includes(windSource)) throw Error('Invalid wind speed source');
  const windProfile = options.wind_speed_profile ?? [];
  if (!Array.isArray(windProfile) || windProfile.length > 100)
    throw Error('Use up to 100 wind reference points');
  let lastTime = -1;
  for (const point of windProfile) {
    if (
      !point || !Number.isFinite(point.time_s) || !Number.isFinite(point.speed_m_s) ||
      point.time_s < 0 || point.speed_m_s < 0 || point.time_s <= lastTime
    ) throw Error('Wind reference points need increasing times and non-negative speeds');
    lastTime = point.time_s;
  }
  if (windProfile.length && windProfile[0].time_s !== 0)
    throw Error('Start the wind reference profile at 0 seconds');
  const slug =
    name
      .normalize('NFKD')
      .replace(/[^a-zA-Z0-9_-]+/g, '_')
      .slice(0, 40) || 'run';
  const id = `${slug}_${Date.now()}_${randomBytes(3).toString('hex')}`;
  const directory = path.join(dataRoot, id);
  fs.mkdirSync(directory);
  const metadata = {
    ...config,
    id,
    name,
    source: state.source,
    status: 'recording',
    wind_speed_m_s: wind,
    wind_speed_source: windSource,
    wind_speed_profile: windProfile,
    wind_profile_time_reference: 'recording_elapsed_seconds',
    wind_profile_interpolation: 'previous_value',
    wind_profile_role: 'reference_only_not_synchronized_measurement',
    fan_distance_m: distance,
    fan_distance_reference: 'fan_grille_to_rotor_plane',
    notes: String(options.notes || '').trim().slice(0, 500),
    rotor_name: String(options.rotor_name || '').slice(0, 80),
    material: String(options.material || '').slice(0, 40),
    started_at_utc: new Date().toISOString(),
    protocol: 1,
    samples: 0,
    voltage_location: 'load_side_of_shunt',
    rotation_direction: 'not_measured',
    hall_filter: state.sample.hall_filter ?? null,
  };
  const metadataPath = path.join(directory, 'metadata.json');
  fs.writeFileSync(metadataPath, JSON.stringify(metadata, null, 2));
  const fd = fs.openSync(path.join(directory, 'samples.csv'), 'wx');
  fs.writeSync(fd, columns.join(',') + '\n');
  model = new Measurements(config.max_energy_gap_s);
  session = { metadata, metadataPath, fd };
  state.sample = null;
  state.recording = { id, name };
  logger.info('recording_started', { id, name, source: state.source });
  sendCommand('RECORD_START');
  broadcast();
}

function reply(response, code, value) {
  response.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  response.end(JSON.stringify(value));
}

const server = http.createServer(async (request, response) => {
  try {
    if (![`127.0.0.1:${portNumber}`, `localhost:${portNumber}`].includes(request.headers.host)) {
      return reply(response, 403, { error: 'Invalid host' });
    }
    const url = new URL(request.url, `http://127.0.0.1:${portNumber}`);
    if (request.method === 'POST') {
      const origin = request.headers.origin;
      if (
        (origin &&
          ![`http://127.0.0.1:${portNumber}`, `http://localhost:${portNumber}`].includes(origin)) ||
        !request.headers['content-type']?.startsWith('application/json')
      ) {
        return reply(response, 403, { error: 'Invalid request origin or content type' });
      }
      let body = '';
      for await (const chunk of request) {
        body += chunk;
        if (body.length > 8192) return reply(response, 413, { error: 'Request too large' });
      }
      const options = JSON.parse(body || '{}');
      if (url.pathname === '/api/connect') await connect(options);
      else if (url.pathname === '/api/disconnect') disconnect();
      else if (url.pathname === '/api/start') startRecording(options);
      else if (url.pathname === '/api/stop') {
        stopRecording();
        broadcast();
      } else return reply(response, 404, { error: 'Not found' });
      return reply(response, 200, state);
    }
    if (request.method !== 'GET') return reply(response, 405, { error: 'Method not allowed' });
    if (url.pathname === '/api/events') {
      response.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      });
      clients.add(response);
      response.write(`data: ${JSON.stringify(state)}\n\n`);
      request.on('close', () => clients.delete(response));
      return;
    }
    if (url.pathname === '/api/ports') return reply(response, 200, await SerialPort.list());
    if (url.pathname === '/api/runs') return reply(response, 200, history());
    if (url.pathname === '/api/config') return reply(response, 200, config);
    const match = url.pathname.match(/^\/api\/runs\/([a-zA-Z0-9_-]+)\/(csv|metadata)$/);
    if (match) {
      const isMetadata = match[2] === 'metadata';
      const extension = isMetadata ? 'json' : 'csv';
      const file = path.join(dataRoot, match[1], isMetadata ? 'metadata.json' : 'samples.csv');
      if (!fs.existsSync(file)) return reply(response, 404, { error: 'Recording not found' });
      response.writeHead(200, {
        'Content-Type': isMetadata ? 'application/json' : 'text/csv',
        'Content-Disposition': `attachment; filename="${match[1]}.${extension}"`,
        'Cache-Control': 'no-store',
      });
      const stream = fs.createReadStream(file);
      stream.on('error', () => response.destroy());
      return stream.pipe(response);
    }
    const assets = {
      '/': ['index.html', 'text/html'],
      '/dashboard.js': ['dashboard.js', 'text/javascript'],
      '/dashboard.css': ['dashboard.css', 'text/css'],
    };
    const asset = assets[url.pathname];
    if (!asset) return reply(response, 404, { error: 'Not found' });
    response.writeHead(200, { 'Content-Type': asset[1], 'X-Content-Type-Options': 'nosniff' });
    response.end(fs.readFileSync(path.join(root, 'public', asset[0])));
  } catch (error) {
    logger.error('request_failed', error);
    if (!response.headersSent) reply(response, 400, { error: error.message });
    else response.end();
  }
});
server.on('error', exitWithError);
server.listen(portNumber, '127.0.0.1', () => {
  logger.info('server_started', { port: portNumber, data_directory: dataRoot });
  console.log(`[READY] Dashboard http://127.0.0.1:${portNumber}`);
  console.log(`Logs: ${logger.file}`);
});
for (const signal of ['SIGINT', 'SIGTERM'])
  process.on(signal, () => {
    logger.info('server_stopped', { signal });
    disconnect('server_stopped');
    for (const client of clients) client.end();
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 2000).unref();
  });
