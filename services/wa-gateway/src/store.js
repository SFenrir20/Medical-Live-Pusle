import { DatabaseSync } from 'node:sqlite';
import { createCipheriv, createDecipheriv, randomBytes, randomUUID, createHmac } from 'node:crypto';
import { BufferJSON, initAuthCreds, proto } from '@whiskeysockets/baileys';

// Values and lookup keys are encrypted/hashed, including Signal sessions and queued messages.
export class Store {
  constructor(path, hexKey) {
    if (!/^[a-f0-9]{64}$/i.test(hexKey || '')) throw new Error('WA_SESSION_KEY must be 64 hex characters');
    this.key = Buffer.from(hexKey, 'hex');
    this.db = new DatabaseSync(path);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
      CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value BLOB NOT NULL);
      CREATE TABLE IF NOT EXISTS auth (key TEXT PRIMARY KEY, value BLOB NOT NULL);
      CREATE TABLE IF NOT EXISTS pending (key TEXT PRIMARY KEY, value BLOB NOT NULL);
      CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value BLOB NOT NULL);
      CREATE TABLE IF NOT EXISTS quarantined_events (seq INTEGER PRIMARY KEY, reason TEXT NOT NULL, value BLOB NOT NULL);
      CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, value BLOB NOT NULL);`);
    const check = this.db.prepare("SELECT value FROM metadata WHERE key='key-check'").get();
    if (check) {
      try { this.decrypt(check.value); } // Wrong key must fail, never create a fresh identity.
      catch (error) { this.db.close(); throw error; }
    }
    else this.db.prepare("INSERT INTO metadata VALUES ('key-check',?)").run(this.encrypt('medical-wa-v1'));
  }
  hash(key) { return createHmac('sha256', this.key).update(key).digest('hex'); }
  encrypt(value) {
    const nonce = randomBytes(12), cipher = createCipheriv('aes-256-gcm', this.key, nonce);
    const body = Buffer.concat([cipher.update(JSON.stringify(value, BufferJSON.replacer)), cipher.final()]);
    return Buffer.concat([nonce, cipher.getAuthTag(), body]);
  }
  decrypt(value) {
    const data = Buffer.from(value), cipher = createDecipheriv('aes-256-gcm', this.key, data.subarray(0, 12));
    cipher.setAuthTag(data.subarray(12, 28));
    return JSON.parse(Buffer.concat([cipher.update(data.subarray(28)), cipher.final()]).toString(), BufferJSON.reviver);
  }
  get(key, namespace = 'kv') {
    if (!['kv', 'auth', 'pending'].includes(namespace)) throw new Error('Invalid namespace');
    const row = this.db.prepare(`SELECT value FROM ${namespace} WHERE key=?`).get(this.hash(key));
    return row ? this.decrypt(row.value) : null;
  }
  set(key, value, namespace = 'kv') {
    if (!['kv', 'auth', 'pending'].includes(namespace)) throw new Error('Invalid namespace');
    if (value == null) this.db.prepare(`DELETE FROM ${namespace} WHERE key=?`).run(this.hash(key));
    else this.db.prepare(`INSERT OR REPLACE INTO ${namespace} VALUES (?,?)`).run(this.hash(key), this.encrypt(value));
  }
  pending() {
    return this.db.prepare('SELECT value FROM pending LIMIT 200').all().map(row => this.decrypt(row.value));
  }
  pendingCount() { return this.db.prepare('SELECT count(*) AS n FROM pending').get().n; }
  eventCount() { return this.db.prepare('SELECT count(*) AS n FROM events').get().n; }
  resetAuth() { this.db.exec('DELETE FROM auth'); }
  registered() { return !!this.get('creds', 'auth')?.registered; }
  close() {
    this.db.close();
  }
  transaction(fn) {
    this.db.exec('BEGIN IMMEDIATE');
    try { const value = fn(); this.db.exec('COMMIT'); return value; }
    catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }
  event(payload) {
    this.db.prepare('INSERT INTO events(value) VALUES (?)').run(this.encrypt({ id: randomUUID(), ...payload }));
  }
  events() {
    return this.db.prepare('SELECT seq,value FROM events ORDER BY seq LIMIT 100').all()
      .map(row => ({ seq: row.seq, ...this.decrypt(row.value) }));
  }
  ack(sequences) {
    this.transaction(() => { for (const seq of sequences) this.db.prepare('DELETE FROM events WHERE seq=?').run(seq); });
  }
  quarantine(sequence, reason) {
    if (!Number.isSafeInteger(sequence) || sequence <= 0 || typeof reason !== 'string' ||
      !/^[a-z_]{1,64}$/.test(reason)) throw new Error('invalid_quarantine');
    this.transaction(() => {
      const row = this.db.prepare('SELECT value FROM events WHERE seq=?').get(sequence);
      if (row) {
        // Preserve the ciphertext verbatim; the worker never has to send the message body back.
        this.db.prepare('INSERT INTO quarantined_events(seq,reason,value) VALUES (?,?,?)').run(sequence, reason, row.value);
        this.db.prepare('DELETE FROM events WHERE seq=?').run(sequence);
      } else if (!this.db.prepare('SELECT seq FROM quarantined_events WHERE seq=?').get(sequence)) {
        throw new Error('event_not_found');
      }
    });
  }
  rejectedCount() { return this.db.prepare('SELECT count(*) AS n FROM quarantined_events').get().n; }
  rejected() {
    return this.db.prepare('SELECT seq,reason FROM quarantined_events ORDER BY seq LIMIT 100').all();
  }
  retryRejected(sequences) {
    let restored = 0;
    this.transaction(() => {
      for (const seq of sequences) {
        const row = this.db.prepare('SELECT value FROM quarantined_events WHERE seq=?').get(seq);
        if (!row) continue;
        // Keep the original event UUID so a repeated import still cannot duplicate a message.
        this.db.prepare('INSERT INTO events(value) VALUES (?)').run(row.value);
        this.db.prepare('DELETE FROM quarantined_events WHERE seq=?').run(seq);
        restored++;
      }
    });
    return restored;
  }
  auth() {
    const creds = this.get('creds', 'auth') || initAuthCreds();
    return {
      state: { creds, keys: {
        get: async (type, ids) => Object.fromEntries(ids.map(id => {
          let value = this.get(`${type}:${id}`, 'auth');
          if (value && type === 'app-state-sync-key') value = proto.Message.AppStateSyncKeyData.fromObject(value);
          return [id, value];
        })),
        set: async data => this.transaction(() => {
          for (const [type, entries] of Object.entries(data))
            for (const [id, value] of Object.entries(entries)) this.set(`${type}:${id}`, value, 'auth');
        }),
      } },
      save: () => this.set('creds', creds, 'auth'),
    };
  }
}
