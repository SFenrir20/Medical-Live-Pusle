import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { Store } from '../src/store.js';
import { Mirror, phoneFromJid } from '../src/mirror.js';
import { DisconnectReason } from '@whiskeysockets/baileys';

const key = 'ab'.repeat(32), business = '+51900000000', contact = '+51911111111';
function setup(t) {
  const store = new Store(':memory:', key); t.after(() => store.close());
  const mirror = new Mirror(store, business);
  mirror.socket = { user: { id: business.slice(1) + ':3@s.whatsapp.net' },
    signalRepository: { lidMapping: { getPNForLID: async () => null } } };
  mirror.state = 'connected';
  return { store, mirror };
}

test('phone JIDs normalize devices but never interpret LIDs/groups as phone numbers', () => {
  assert.equal(phoneFromJid('51911111111:7@s.whatsapp.net'), contact);
  assert.equal(phoneFromJid('51911111111@lid'), null);
  assert.equal(phoneFromJid('51911111111@g.us'), null);
});

test('Signal auth, queued events survive restart, stay encrypted and reject a wrong key', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'medical-wa-test-')), path = join(directory, 'store.sqlite');
  try {
    let store = new Store(path, key);
    const auth = store.auth(); auth.state.creds.registered = true; auth.save();
    await auth.state.keys.set({ session: { private: { secret: Buffer.from('private-key-material') } } });
    store.event({ body: 'confidential-message-body' });
    assert.equal(new Mirror(store).bindAccount(business.slice(1) + ':3@s.whatsapp.net'), true);
    store.close();
    assert.equal(readFileSync(path).includes(Buffer.from('confidential-message-body')), false);
    assert.equal(readFileSync(path).includes(Buffer.from('private-key-material')), false);
    store = new Store(path, key);
    assert.equal(store.registered(), true);
    assert.equal(new Mirror(store).status().phone, business);
    assert.deepEqual((await store.auth().state.keys.get('session', ['private'])).private.secret, Buffer.from('private-key-material'));
    const event = store.events()[0]; assert.equal(event.body, 'confidential-message-body');
    store.ack([event.seq]); assert.equal(store.events().length, 0);
    store.close();
    assert.throws(() => new Store(path, 'cd'.repeat(32)));
  } finally { rmSync(directory, { recursive: true, force: true }); }
});

test('same request submits only once, including concurrent retries', async t => {
  const { mirror, store } = setup(t); let calls = 0;
  mirror.socket.sendMessage = async (jid, content, options) => {
    calls++;
    return { key: { id: options.messageId, remoteJid: jid, fromMe: true }, message: { conversation: content.text }, messageTimestamp: 1800000000 };
  };
  const request = { request_id: randomUUID(), phone: contact, text: 'Hola' };
  const [a, b] = await Promise.all([mirror.send(request), mirror.send(request)]);
  assert.equal(calls, 1); assert.equal(a.external_id, b.external_id); assert.equal(a.state, 'sent');
  assert.equal(store.events()[0].request_id, request.request_id);
  await assert.rejects(() => mirror.send({ ...request, text: 'Different message' }), /request_conflict/);
});

test('ambiguous failure is never retransmitted, even by a new connector instance', async t => {
  const { mirror, store } = setup(t); let calls = 0;
  mirror.socket.sendMessage = async () => { calls++; throw new Error('connection lost after transmission'); };
  const request = { request_id: randomUUID(), phone: contact, text: 'Hola' };
  assert.equal((await mirror.send(request)).state, 'unknown');
  const restarted = new Mirror(store, business);
  assert.equal((await restarted.send(request)).state, 'unknown');
  assert.equal(calls, 1);
});

test('unresolved LID persists until mapped; own phone messages have no fictitious agent', async t => {
  const { mirror, store } = setup(t);
  const message = { key: { id: 'm1', remoteJid: '123456789@lid', fromMe: true },
    message: { conversation: 'desde el celular' }, messageTimestamp: 1800000000 };
  await mirror.message(message);
  assert.equal(store.events().length, 0); assert.equal(store.pendingCount(), 1);
  mirror.socket.signalRepository.lidMapping.getPNForLID = async () => contact.slice(1) + '@s.whatsapp.net';
  await mirror.retryPending();
  assert.equal(store.pendingCount(), 0);
  const event = store.events()[0];
  assert.equal(event.phone, contact); assert.equal(event.request_id, null); assert.equal(event.from_me, true);
});

test('a linked number mismatch cannot emit messages or reuse an existing account volume', async t => {
  const { mirror, store } = setup(t);
  mirror.socket.user.id = '51922222222@s.whatsapp.net';
  await mirror.message({ key: { id: 'wrong', remoteJid: contact.slice(1) + '@s.whatsapp.net' }, message: { conversation: 'private' } });
  assert.equal(store.events().length, 0);
  store.set('account', business);
  assert.throws(() => new Mirror(store, '+51933333333'), /another WhatsApp number/);
});

test('empty number configuration permits QR pairing and learns the linked phone', async t => {
  const store = new Store(':memory:', key); t.after(() => store.close());
  const socket = { ev: new EventEmitter(), user: undefined };
  const mirror = new Mirror(store, '', () => socket);
  assert.equal(mirror.status().phone, null);
  mirror.connect();
  socket.ev.emit('connection.update', { qr: 'test-pairing-code' });
  await mirror.eventsTail;
  assert.equal(mirror.state, 'qr');
  assert.match(mirror.status().qr, /^data:image\/png;base64,/);
  // No messages or receipts are accepted before a real phone identity is known.
  await mirror.message({ key: { id: 'early' }, message: { conversation: 'not yet authenticated' } });
  await mirror.receipt({ id: 'early' }, 'read', new Date().toISOString(), 'observed');
  assert.equal(store.events().length, 0);
  socket.user = { id: business.slice(1) + ':4@s.whatsapp.net' };
  socket.ev.emit('connection.update', { connection: 'open' });
  await mirror.eventsTail;
  assert.equal(mirror.state, 'connected');
  assert.equal(mirror.status().phone, business);
  assert.equal(mirror.status().qr, null);
  assert.equal(store.get('account'), business);
});

test('automatic pairing retains identity across relinks and rejects a different account', async t => {
  const store = new Store(':memory:', key); t.after(() => store.close());
  assert.equal(new Mirror(store).bindAccount(business.slice(1) + '@s.whatsapp.net'), true);
  let logouts = 0;
  const socket = { ev: new EventEmitter(), user: { id: '51922222222@s.whatsapp.net' },
    logout: async () => { logouts++; } };
  const mirror = new Mirror(store, undefined, () => socket);
  assert.equal(mirror.status().phone, business);
  mirror.connect();
  socket.ev.emit('connection.update', { connection: 'open' });
  await mirror.eventsTail;
  assert.equal(mirror.state, 'wrong_number');
  assert.equal(logouts, 1);
  assert.equal(store.get('account'), business);
  assert.equal(mirror.bindAccount(business.slice(1) + ':8@s.whatsapp.net'), true);
});

test('optional expected number still validates and unidentified accounts cannot be bound', t => {
  const store = new Store(':memory:', key); t.after(() => store.close());
  const auto = new Mirror(store, '  ');
  for (const jid of [undefined, '123456789@lid', '123456789@g.us']) assert.equal(auto.bindAccount(jid), false);
  assert.equal(store.get('account'), null);
  assert.throws(() => new Mirror(store, 'invalid'), /E.164/);
  const restricted = new Mirror(store, business);
  assert.equal(restricted.bindAccount('51922222222@s.whatsapp.net'), false);
  assert.equal(store.get('account'), null);
  assert.equal(restricted.bindAccount(business.slice(1) + '@s.whatsapp.net'), true);
});

test('bad event moves atomically into encrypted quarantine and can be replayed after restart', () => {
  const directory = mkdtempSync(join(tmpdir(), 'medical-wa-test-')), path = join(directory, 'store.sqlite');
  let store;
  try {
    store = new Store(path, key);
    store.event({ type: 'receipt', phone: contact, body: 'private-quarantined-content' });
    store.event({ type: 'message', body: 'next' });
    const original = store.events()[0];
    store.quarantine(original.seq, 'receipt_phone_mismatch');
    store.quarantine(original.seq, 'receipt_phone_mismatch'); // HTTP response lost: safe repeat.
    assert.equal(store.rejectedCount(), 1);
    assert.equal(store.events().length, 1);
    assert.equal(store.events()[0].body, 'next');
    assert.deepEqual(store.rejected().map(row => ({ ...row })), [{ seq: original.seq, reason: 'receipt_phone_mismatch' }]);
    store.close(); store = null;
    assert.equal(readFileSync(path).includes(Buffer.from('private-quarantined-content')), false);
    store = new Store(path, key);
    assert.equal(store.rejectedCount(), 1);
    assert.equal(store.retryRejected([original.seq]), 1);
    assert.equal(store.retryRejected([original.seq]), 0);
    assert.equal(store.rejectedCount(), 0);
    const replay = store.events().find(e => e.id === original.id);
    assert.equal(replay.body, original.body);
    assert.equal(replay.phone, contact);
    assert.notEqual(replay.seq, original.seq);
  } finally { store?.close(); rmSync(directory, { recursive: true, force: true }); }
});

test('failure to preserve an event cannot remove it from the active queue', t => {
  const { store } = setup(t);
  store.event({ body: 'keep this message' });
  const original = store.events()[0];
  // Simulate a storage error on the preservation step.
  store.db.exec("CREATE TRIGGER reject_quarantine BEFORE INSERT ON quarantined_events BEGIN SELECT RAISE(ABORT, 'storage error'); END;");
  assert.throws(() => store.quarantine(original.seq, 'invalid_timestamp'));
  assert.deepEqual(store.events()[0], original);
  assert.equal(store.rejectedCount(), 0);
});

function lifecycle(t, factory) {
  const store = new Store(':memory:', key);
  let clock = 1_800_000_000_000;
  const sockets = [];
  const mirror = new Mirror(store, business, factory || (() => {
    const socket = { ev: new EventEmitter(), ws: { isOpen: true },
      user: { id: business.slice(1) + '@s.whatsapp.net' },
      end() { this.ws.isOpen = false; this.ev.emit('connection.update', { connection: 'close' }); } };
    sockets.push(socket);
    return socket;
  }), { now: () => clock, random: () => 0.5 });
  t.after(() => { mirror.stop(); store.close(); });
  return { mirror, store, sockets, advance: ms => { clock += ms; } };
}

test('expired handshake reconnects once without discarding credentials or queued events', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const { mirror, store, sockets, advance } = lifecycle(t);
  const auth = store.auth(); auth.state.creds.registered = true; auth.save();
  store.event({ type: 'message', body: 'keep me' });
  mirror.connect();
  advance(60_001);
  mirror.checkConnection(); mirror.checkConnection();
  await mirror.eventsTail; // end() emitted close from the retired socket.
  assert.equal(mirror.state, 'disconnected');
  assert.equal(mirror.status().recovery_reason, 'connection_timeout');
  assert.equal(mirror.status().reconnect_attempt, 1);
  assert.equal(store.registered(), true);
  assert.equal(store.eventCount(), 1);
  t.mock.timers.tick(2_000);
  assert.equal(sockets.length, 2);
  assert.equal(mirror.state, 'connecting');
});

test('retired socket callbacks cannot change the new connection or persist old messages', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const { mirror, store, sockets } = lifecycle(t);
  mirror.connect();
  const old = sockets[0];
  old.ev.emit('connection.update', { connection: 'close' });
  await mirror.eventsTail;
  t.mock.timers.tick(2_000);
  const current = sockets[1];
  current.ev.emit('connection.update', { connection: 'open' });
  await mirror.eventsTail;
  old.ev.emit('connection.update', { connection: 'close' });
  old.ev.emit('messages.upsert', { messages: [{ key: { id: 'stale', remoteJid: contact.slice(1) + '@s.whatsapp.net' },
    message: { conversation: 'from retired socket' }, messageTimestamp: 1800000000 }] });
  await mirror.eventsTail;
  assert.equal(mirror.state, 'connected');
  assert.equal(mirror.socket, current);
  assert.equal(store.eventCount(), 0);
});

test('quiet connected sessions stay open; a closed transport recovers without a close event', async t => {
  const { mirror, sockets, advance } = lifecycle(t);
  mirror.connect();
  sockets[0].ev.emit('connection.update', { connection: 'open' });
  await mirror.eventsTail;
  advance(24 * 60 * 60 * 1000);
  mirror.checkConnection();
  assert.equal(mirror.state, 'connected');
  sockets[0].ws.isOpen = false;
  mirror.checkConnection();
  assert.equal(mirror.state, 'disconnected');
  assert.equal(mirror.status().recovery_reason, 'transport_closed');
});

test('revoked sessions wait for a person; shutdown never reconnects or wipes auth', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const { mirror, store, sockets, advance } = lifecycle(t);
  const auth = store.auth(); auth.state.creds.registered = true; auth.save();
  mirror.connect();
  sockets[0].ev.emit('connection.update', { connection: 'close',
    lastDisconnect: { error: { output: { statusCode: DisconnectReason.loggedOut } } } });
  await mirror.eventsTail;
  advance(120_000); mirror.checkConnection(); t.mock.timers.tick(120_000);
  assert.equal(mirror.state, 'relink_required');
  assert.equal(sockets.length, 1);
  assert.equal(store.registered(), true);
  mirror.stop(); mirror.connect();
  assert.equal(sockets.length, 1);
  assert.equal(store.registered(), true);
});

test('socket startup failure schedules a bounded retry instead of getting stuck connecting', t => {
  const { mirror } = lifecycle(t, () => { throw new Error('temporary startup failure'); });
  mirror.connect();
  assert.equal(mirror.state, 'disconnected');
  assert.equal(mirror.status().recovery_reason, 'connection_start_failed');
  assert.ok(mirror.status().retry_at);
});

test('disconnect during media preparation leaves a send queued without creating an ambiguous intent', async t => {
  const { mirror, store } = setup(t);
  const request = { request_id: randomUUID(), phone: contact, text: 'Foto', media_id: 'a'.repeat(64) };
  let sends = 0;
  mirror.socket.sendMessage = async () => { sends++; };
  mirror.image = async () => {
    mirror.state = 'disconnected'; mirror.socket = null;
    return { phone: contact, data: '', mime: 'image/png' };
  };
  assert.deepEqual(await mirror.send(request), { state: 'offline' });
  assert.equal(sends, 0);
  assert.equal(store.get(`request:${request.request_id}`), null);
});

test('shutdown drains accepted messages but refuses new callbacks and never reconnects', async t => {
  const { mirror, store, sockets } = lifecycle(t);
  mirror.connect();
  sockets[0].ev.emit('connection.update', { connection: 'open' });
  await mirror.eventsTail;
  const message = id => ({ key: { id, remoteJid: contact.slice(1) + '@s.whatsapp.net' },
    message: { conversation: id }, messageTimestamp: 1800000000 });
  sockets[0].ev.emit('messages.upsert', { messages: [message('accepted')] });
  mirror.stop();
  sockets[0].ev.emit('messages.upsert', { messages: [message('after-stop')] });
  await mirror.eventsTail;
  assert.deepEqual(store.events().map(e => e.external_id), ['accepted']);
  assert.equal(mirror.state, 'disconnected');
  assert.equal(mirror.retryTimer, null);
});
