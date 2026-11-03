import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { Store } from '../src/store.js';
import { Mirror, phoneFromJid } from '../src/mirror.js';

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
    store.close();
    assert.equal(readFileSync(path).includes(Buffer.from('confidential-message-body')), false);
    assert.equal(readFileSync(path).includes(Buffer.from('private-key-material')), false);
    store = new Store(path, key);
    assert.equal(store.registered(), true);
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
