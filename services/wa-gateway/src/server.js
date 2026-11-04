import { createServer } from 'node:http';
import { timingSafeEqual } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { Store } from './store.js';
import { Mirror } from './mirror.js';

const token = process.env.WA_GATEWAY_TOKEN || '';
if (token.length < 32) throw new Error('WA_GATEWAY_TOKEN must contain at least 32 characters');
const directory = process.env.WA_DATA_DIR || '/data';
mkdirSync(directory, { recursive: true, mode: 0o700 });
const store = new Store(directory + '/session.sqlite', process.env.WA_SESSION_KEY);
const mirror = new Mirror(store, process.env.WA_EXPECTED_PHONE);
// Detect a wrong encryption key on startup, before accepting a new pairing.
if (store.registered()) mirror.connect();
const secret = Buffer.from('Bearer ' + token);
createServer(async (req, res) => {
  res.setHeader('Content-Type', 'application/json'); res.setHeader('Cache-Control', 'no-store');
  const reply = (status, value) => { res.writeHead(status); res.end(JSON.stringify(value)); };
  if (req.url === '/health') return reply(200, { ok: true });
  const provided = Buffer.from(req.headers.authorization || '');
  if (provided.length !== secret.length || !timingSafeEqual(secret, provided)) return reply(401, { error: 'unauthorized' });
  try {
    let raw = '';
    for await (const part of req) { raw += part; if (raw.length > 32000) return reply(413, { error: 'too_large' }); }
    const data = raw ? JSON.parse(raw) : {};
    if (req.method === 'GET' && req.url === '/status') return reply(200, { ...mirror.status(), rejected: store.rejectedCount() });
    if (req.method === 'GET' && req.url === '/events') return reply(200, store.events());
    if (req.method === 'GET' && req.url === '/events/rejected') return reply(200, store.rejected());
    if (req.method === 'POST' && req.url === '/events/quarantine') {
      store.quarantine(data.sequence, data.reason); return reply(200, { ok: true });
    }
    if (req.method === 'POST' && req.url === '/events/retry' && Array.isArray(data.sequences) &&
      data.sequences.length <= 100 && data.sequences.every(n => Number.isSafeInteger(n) && n > 0)) {
      return reply(200, { restored: store.retryRejected(data.sequences) });
    }
    if (req.method === 'POST' && req.url === '/connect') { mirror.connect(); return reply(200, mirror.status()); }
    if (req.method === 'POST' && req.url === '/events/ack' && Array.isArray(data.sequences) &&
      data.sequences.length <= 100 && data.sequences.every(Number.isSafeInteger)) {
      store.ack(data.sequences); return reply(200, { ok: true });
    }
    if (req.method === 'POST' && req.url === '/send') return reply(200, await mirror.send(data));
    reply(404, { error: 'not_found' });
  } catch { reply(400, { error: 'request_failed' }); }
}).listen(3001, '0.0.0.0');
