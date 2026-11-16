import fs from 'node:fs';
import path from 'node:path';

export function createLogger(directory) {
  fs.mkdirSync(directory, { recursive: true });
  const file = path.join(directory, 'server.log');

  function write(level, event, details = {}) {
    const entry = { time: new Date().toISOString(), level, event, ...details };
    fs.appendFileSync(file, JSON.stringify(entry) + '\n');
  }

  return {
    file,
    info: (event, details) => write('INFO', event, details),
    warn: (event, details) => write('WARN', event, details),
    error: (event, error) => write('ERROR', event, { message: error.message, stack: error.stack }),
  };
}
