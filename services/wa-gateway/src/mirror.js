import { registerImage, loadImage, isViewOnce } from './images.js';
import { mediaOf, registerMedia, loadMedia, KINDS } from './media.js';
import makeWASocket, { DisconnectReason, jidDecode, normalizeMessageContent, getContentType,
  generateMessageIDV2 } from '@whiskeysockets/baileys';
import pino from 'pino';
import QRCode from 'qrcode';

export function phoneFromJid(jid) {
  const decoded = jidDecode(jid || '');
  // A LID looks numeric but is NOT a telephone number.
  return decoded?.server === 's.whatsapp.net' && /^[1-9]\d{7,14}$/.test(decoded.user)
    ? '+' + decoded.user : null;
}
const timestamp = value => {
  const seconds = Number(value);
  return seconds > 0 && Number.isFinite(seconds) ? new Date(seconds * 1000).toISOString() : null;
};
export class Mirror {
  constructor(store, expectedPhone, socketFactory = makeWASocket, { now = Date.now, random = Math.random } = {}) {
    expectedPhone = expectedPhone?.trim() || null;
    if (expectedPhone && !/^\+[1-9]\d{7,14}$/.test(expectedPhone)) throw new Error('WA_EXPECTED_PHONE must be E.164 when set');
    this.store = store; this.socketFactory = socketFactory;
    const previous = store.get('account');
    if (previous && expectedPhone && previous !== expectedPhone) throw new Error('This volume belongs to another WhatsApp number');
    this.expectedPhone = previous || expectedPhone;
    this.state = 'disconnected'; this.qr = null; this.socket = null;
    this.eventsTail = Promise.resolve(); this.sendTail = Promise.resolve();
    this.retryTimer = null; this.attempt = 0;
    this.now = now; this.random = random; this.stopped = false;
    this.connectStartedAt = null; this.connectedAt = null; this.nextRetryAt = null;
    this.lastDisconnectCode = null; this.recoveryReason = null;
    this.imageDownloads = new Map();
    this.mediaDownloads = new Map();
    this.imageSlots = [Promise.resolve(), Promise.resolve()];
    this.nextImageSlot = 0;
  }
  status() {
    return { state: this.state, phone: this.expectedPhone, qr: this.qr,
      unresolved: this.store.pendingCount(), connected_at: this.connectedAt,
      retry_at: this.nextRetryAt, reconnect_attempt: this.attempt,
      last_disconnect_code: this.lastDisconnectCode, recovery_reason: this.recoveryReason,
      history_received_at: this.store.get('history_received_at') };
  }
  // Never infer a dead connection from a quiet inbox. Baileys owns protocol heartbeats;
  // this watchdog only recovers an expired handshake or a visibly closed transport.
  checkConnection() {
    if (this.stopped || ['relink_required', 'wrong_number'].includes(this.state)) return;
    const expired = this.state === 'connecting' && this.connectStartedAt !== null &&
      this.now() - this.connectStartedAt > 60_000;
    const closed = ['connected', 'qr'].includes(this.state) && this.socket?.ws?.isOpen === false;
    if (expired || closed) {
      this.recoveryReason = expired ? 'connection_timeout' : 'transport_closed';
      this.scheduleReconnect();
    }
  }
  retireSocket() {
    const previous = this.socket;
    this.socket = null; // Retire callbacks before end() can emit connection.close.
    try { previous?.end?.(new Error('Connector reconnecting')); } catch { /* already closed */ }
  }
  scheduleReconnect() {
    if (this.stopped || this.retryTimer) return;
    this.retireSocket();
    this.state = 'disconnected'; this.qr = null; this.connectStartedAt = null;
    const base = Math.min(60_000, 2_000 * 2 ** Math.min(this.attempt++, 5));
    const delay = Math.min(60_000, Math.round(base * (0.8 + this.random() * 0.4)));
    this.nextRetryAt = new Date(this.now() + delay).toISOString();
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.connect();
    }, delay);
    this.retryTimer.unref?.();
  }
  stop() {
    this.stopped = true;
    clearTimeout(this.retryTimer); this.retryTimer = null; this.nextRetryAt = null;
    // Keep the identity available while already accepted events drain to disk.
    // New callbacks are rejected by handler(); closing is not a WhatsApp logout.
    try { this.socket?.end?.(new Error('Connector stopping')); } catch { /* already closed */ }
    this.state = 'disconnected'; this.qr = null;
  }
  bindAccount(jid) {
    const phone = phoneFromJid(jid);
    if (!phone || (this.expectedPhone && phone !== this.expectedPhone)) return false;
    // The first successful QR pairing owns this volume. Relinking must keep that identity.
    this.store.set('account', phone);
    this.expectedPhone = phone;
    return true;
  }
  matchesAccount() {
    return !!this.expectedPhone && phoneFromJid(this.socket?.user?.id) === this.expectedPhone;
  }
  handler(fn, socket) {
    return data => {
      if (this.stopped || (socket && socket !== this.socket)) return;
      this.eventsTail = this.eventsTail.then(() => {
        if (socket && socket !== this.socket) return;
        return fn(data);
      }).catch(() => {
        // Do not continue acknowledging messages if persistence failed.
        console.error('WhatsApp event persistence failed; restarting connector');
        process.exitCode = 1;
        this.socket?.end(new Error('Persistence failure'));
        setTimeout(() => process.exit(1), 100).unref();
      });
    };
  }
  connect() {
    if (this.stopped) return;
    if (['connected', 'connecting', 'qr'].includes(this.state)) return;
    if (['relink_required', 'wrong_number'].includes(this.state)) this.store.resetAuth();
    clearTimeout(this.retryTimer);
    this.retryTimer = null; this.nextRetryAt = null;
    this.retireSocket();
    this.state = 'connecting'; this.qr = null;
    this.connectStartedAt = this.now();
    const auth = this.store.auth();
    let socket;
    try { socket = this.socketFactory({ auth: auth.state, logger: pino({ level: 'silent' }),
      browser: ['Medical Social Pulse', 'Chrome', '1.0.0'], markOnlineOnConnect: false,
      syncFullHistory: true, shouldSyncHistoryMessage: () => true,
      getMessage: async key => this.store.get(`message:${key.id}`),
      connectTimeoutMs: 30_000, defaultQueryTimeoutMs: 30_000, keepAliveIntervalMs: 25_000,
    }); } catch {
      this.recoveryReason = 'connection_start_failed';
      this.scheduleReconnect(); return;
    }
    this.socket = socket;
    socket.ev.on('creds.update', this.handler(() => auth.save(), socket));
    socket.ev.on('connection.update', this.handler(async update => {
      if (this.stopped || socket !== this.socket) return;
      if (update.qr) { this.state = 'qr'; this.qr = await QRCode.toDataURL(update.qr); }
      if (update.connection === 'open') {
        if (!this.bindAccount(socket.user?.id)) {
          this.state = 'wrong_number'; this.qr = null;
          await socket.logout(); return;
        }
        this.state = 'connected'; this.qr = null; this.attempt = 0;
        this.connectedAt = new Date(this.now()).toISOString();
        this.connectStartedAt = null; this.recoveryReason = null;
        await this.retryPending();
      }
      if (update.connection === 'close') {
        this.qr = null;
        const code = update.lastDisconnect?.error?.output?.statusCode;
        this.lastDisconnectCode = Number.isInteger(code) ? code : null;
        if (this.state === 'wrong_number') return;
        if ([DisconnectReason.loggedOut, DisconnectReason.badSession, DisconnectReason.connectionReplaced].includes(code)) {
          this.state = 'relink_required'; this.retireSocket(); return;
        }
        this.scheduleReconnect();
      }
    }, socket));
    socket.ev.on('messages.upsert', this.handler(async ({ messages }) => {
      for (const message of messages) await this.message(message);
    }, socket));
    socket.ev.on('messaging-history.set', this.handler(async ({ messages = [] }) => {
      for (const message of messages) await this.message(message, true);
      this.store.set('history_received_at', new Date(this.now()).toISOString());
    }, socket));
    socket.ev.on('lid-mapping.update', this.handler(() => this.retryPending(), socket));
    socket.ev.on('messages.update', this.handler(async updates => {
      for (const { key, update } of updates) {
        if (!key.fromMe || ![2, 3, 4, 5].includes(update.status)) continue;
        const status = update.status >= 4 ? 'read' : update.status === 3 ? 'delivered' : 'sent';
        await this.receipt(key, status, new Date().toISOString(), 'observed');
      }
    }, socket));
    socket.ev.on('message-receipt.update', this.handler(async updates => {
      for (const { key, receipt } of updates) {
        if (!key.fromMe) continue;
        if (receipt.receiptTimestamp) await this.receipt(key, 'delivered', timestamp(receipt.receiptTimestamp), 'provider');
        if (receipt.readTimestamp) await this.receipt(key, 'read', timestamp(receipt.readTimestamp), 'provider');
      }
    }, socket));
  }
  async resolve(key) {
    if (!key.remoteJid || !/@(s\.whatsapp\.net|lid)$/.test(key.remoteJid)) return null;
    return phoneFromJid(key.remoteJid) || phoneFromJid(key.remoteJidAlt) ||
      phoneFromJid(await this.socket.signalRepository.lidMapping.getPNForLID(key.remoteJid));
  }
  async retryPending() {
    for (const pending of this.store.pending()) {
      if (pending.type === 'message') await this.message(pending.message, pending.historical === true);
      else await this.receipt(pending.key, pending.status, pending.at, pending.clock);
    }
  }
  async requestHistory({ phone, external_id, from_me, at, restart = false }) {
    if (!/^\+[1-9]\d{7,14}$/.test(phone || '') || typeof external_id !== 'string' ||
      !external_id || external_id.length > 128 || typeof from_me !== 'boolean' ||
      !Number.isSafeInteger(at) || at <= 0 || typeof restart !== 'boolean') throw new Error('invalid_history_request');
    if (this.state !== 'connected' || !this.matchesAccount()) return { state: 'offline' };
    const name = `history:${phone}`;
    const previous = this.store.get(name);
    // Reserve before awaiting the network: repeated clicks cannot issue overlapping requests.
    if (previous && this.now() - previous.requested_at < 60_000) return { state: 'waiting' };
    const seed = this.store.get(`message-meta:${external_id}`);
    const cursor = !restart && previous?.cursor ? previous.cursor :
      seed?.phone === phone ? seed : { phone, key: { id: external_id, fromMe: from_me,
        remoteJid: phone.slice(1) + '@s.whatsapp.net' }, at };
    this.store.set(name, { cursor, requested_at: this.now() });
    let timer;
    try {
      await Promise.race([
        this.socket.fetchMessageHistory(50, cursor.key, cursor.at),
        new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('history_timeout')), 15_000); }),
      ]);
      return { state: 'requested' }; // Acceptance does not mean the phone delivered any history.
    } catch {
      return { state: 'unconfirmed' }; // Keep cooldown: a late response may still arrive.
    } finally { clearTimeout(timer); }
  }
  async message(message, historical = false) {
    if (!this.matchesAccount()) return;
    const { key } = message;
    if (!key.id || !message.message) return;
    const content = normalizeMessageContent(message.message), type = getContentType(content);
    if (!type || ['protocolMessage', 'senderKeyDistributionMessage', 'reactionMessage'].includes(type)) return;
    if (historical && !timestamp(message.messageTimestamp)) return; // Never date old messages as today.
    const phone = await this.resolve(key);
    if (!phone) {
      if (key.remoteJid?.endsWith('@lid')) this.store.set(`m:${key.id}`, { type: 'message', message, historical }, 'pending');
      return;
    }
    const at = timestamp(message.messageTimestamp) || new Date().toISOString();
    const caption = content.imageMessage?.caption || content.videoMessage?.caption ||
      content.documentMessage?.caption || '';
    const label = { imageMessage: 'Imagen', videoMessage: 'Video', audioMessage: 'Audio',
      documentMessage: 'Documento', stickerMessage: 'Sticker', contactMessage: 'Contacto',
      contactsArrayMessage: 'Contactos', locationMessage: 'Ubicación' }[type] || 'Mensaje no textual';
    const body = content.conversation || content.extendedTextMessage?.text ||
      `[${label}: consultar en el teléfono]${caption ? '\n' + caption : ''}`;
    const intent = this.store.get(`outgoing:${key.id}`);
    // View-once media stays on the phone; never persist it as a normal attachment.
    const once = isViewOnce(message.message);
    const media_id = !once && type === 'imageMessage'
      ? (intent?.media_id || registerImage(this.store, phone, message)) : null;
    // Audio, voice notes, video, documents and stickers (not view-once) are kept like images.
    const info = !once ? mediaOf(content, type) : null;
    const file_id = info ? registerMedia(this.store, phone, message, info) : null;
    this.store.transaction(() => {
      this.store.set(`m:${key.id}`, null, 'pending');
      this.store.set(`message:${key.id}`, message.message);
      const meta = { phone, key, at: Math.floor(new Date(at).getTime() / 1000) };
      this.store.set(`message-meta:${key.id}`, meta);
      const request = historical && this.store.get(`history:${phone}`);
      if (request && meta.at < request.cursor.at) {
        this.store.set(`history:${phone}`, { ...request, cursor: meta });
      }
      this.store.event({ type: 'message', external_id: key.id, phone,
        body: media_id ? (caption || '[Imagen]') : info ? info.caption.slice(0, 20000) : body.slice(0, 20000),
        from_me: !!key.fromMe, request_id: intent?.request_id || null, at, historical,
        name: key.fromMe ? null : message.pushName, media_type: type, media_id: media_id || file_id,
        media_kind: media_id ? 'image' : info?.kind ?? null, media_seconds: info?.seconds ?? null,
        media_name: info?.name ?? null, media_size: info?.size ?? null });
      if (intent) this.store.set(`request:${intent.request_id}`, { ...intent, state: 'sent', at });
    });
    if (media_id && !historical) void this.image(media_id).catch(() => {}); // Historical media downloads on view.
    if (file_id && !historical && KINDS[info.kind].eager) void this.media(file_id).catch(() => {});
  }
  media(id) {
    if (!this.mediaDownloads.has(id)) {
      const cached = this.store.get(`media:${id}`);
      if (cached?.data) return Promise.resolve(cached);
      const slot = this.nextImageSlot++ % this.imageSlots.length;  // same two download slots as images
      const task = this.imageSlots[slot].then(() => loadMedia(this.store, this.socket, id))
        .finally(() => this.mediaDownloads.delete(id));
      this.imageSlots[slot] = task.catch(() => {});
      this.mediaDownloads.set(id, task);
    }
    return this.mediaDownloads.get(id);
  }
  /** Attach media to a message that was stored before media was supported. The raw message is
   *  still in the encrypted store, so it can be downloaded again while WhatsApp still serves it. */
  adopt(phone, externalId) {
    if (!/^\+[1-9]\d{7,14}$/.test(phone || '') || typeof externalId !== 'string' ||
      !externalId || externalId.length > 128) throw new Error('invalid_adopt');
    const raw = this.store.get(`message:${externalId}`);
    if (!raw) return { adopted: false, reason: 'not_stored' };
    if (isViewOnce(raw)) return { adopted: false, reason: 'view_once' };
    const content = normalizeMessageContent(raw), type = getContentType(content);
    const message = { key: { id: externalId, remoteJid: phone.slice(1) + '@s.whatsapp.net' }, message: raw };
    if (type === 'imageMessage') {
      const media_id = registerImage(this.store, phone, message);
      void this.image(media_id).catch(() => {});
      return { adopted: true, media_id, media_kind: 'image', media_seconds: null, media_name: null, media_size: null };
    }
    const info = mediaOf(content, type);
    if (!info) return { adopted: false, reason: 'not_media' };
    const media_id = registerMedia(this.store, phone, message, info);
    if (KINDS[info.kind].eager) void this.media(media_id).catch(() => {});
    return { adopted: true, media_id, media_kind: info.kind, media_seconds: info.seconds,
      media_name: info.name, media_size: info.size };
  }
  image(id) {
    if (!this.imageDownloads.has(id)) {
      const cached = this.store.get(`image:${id}`);
      if (cached?.data) return Promise.resolve(cached);
      const slot = this.nextImageSlot++ % this.imageSlots.length;
      const task = this.imageSlots[slot].then(() => loadImage(this.store, this.socket, id))
        .finally(() => this.imageDownloads.delete(id));
      this.imageSlots[slot] = task.catch(() => {});
      this.imageDownloads.set(id, task);
    }
    return this.imageDownloads.get(id);
  }
  async receipt(key, status, at, clock) {
    if (!this.matchesAccount()) return;
    const phone = await this.resolve(key);
    if (!at) return;
    const pendingKey = `r:${key.id}:${status}`;
    if (!phone) {
      if (key.remoteJid?.endsWith('@lid')) this.store.set(pendingKey, { type: 'receipt', key, status, at, clock }, 'pending');
      return;
    }
    this.store.transaction(() => {
      this.store.set(pendingKey, null, 'pending');
      this.store.event({ type: 'receipt', external_id: key.id, phone, status, at, clock });
    });
  }
  send(input) {
    const operation = this.sendTail.then(() => this.sendOnce(input));
    this.sendTail = operation.catch(() => {});
    return operation;
  }
  async sendOnce({ request_id, phone, text, media_id = null }) {
    if (!/^[a-f0-9-]{36}$/i.test(request_id || '') || !/^\+[1-9]\d{7,14}$/.test(phone || '') ||
      typeof text !== 'string' || (!text.trim() && !media_id) || text.length > 4000 ||
      (media_id && !/^[a-f0-9]{64}$/.test(media_id))) throw new Error('invalid_send');
    const previous = this.store.get(`request:${request_id}`);
    if (previous) {
      if (previous.phone !== phone || previous.text !== text || (previous.media_id || null) !== media_id) throw new Error('request_conflict');
      return previous; // Never re-send an ambiguous attempt after a crash or timeout.
    }
    if (this.state !== 'connected' || !this.matchesAccount()) return { state: 'offline' };
    const image = media_id ? await this.image(media_id) : null;
    if (image && image.phone !== phone) throw new Error('image_phone_mismatch');
    // A media download can outlive the socket. Do not create an ambiguous intent
    // until we still have a live, correctly bound transport to attempt the send.
    if (this.state !== 'connected' || !this.matchesAccount()) return { state: 'offline' };
    const socket = this.socket;
    const external_id = generateMessageIDV2(socket.user.id);
    const intent = { request_id, phone, text, media_id, external_id, state: 'unknown' };
    this.store.transaction(() => {
      this.store.set(`request:${request_id}`, intent);
      this.store.set(`outgoing:${external_id}`, intent);
    });
    try {
      let timer;
      const attempt = socket.sendMessage(phone.slice(1) + '@s.whatsapp.net', image
        ? { image: Buffer.from(image.data, 'base64'), mimetype: image.mime, caption: text } : { text }, { messageId: external_id });
      // Preserve a late success even if the HTTP caller timed out.
      attempt.then(message => this.message(message)).catch(() => {});
      const message = await Promise.race([attempt, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('Unconfirmed send')), 45000);
      })]).finally(() => clearTimeout(timer));
      // sendMessage returning means submitted, not delivered/read.
      const result = { ...intent, state: 'sent', at: timestamp(message.messageTimestamp) || new Date().toISOString() };
      this.store.set(`request:${request_id}`, result);
      await this.message({ ...message, key: { ...message.key, remoteJid: phone.slice(1) + '@s.whatsapp.net' } });
      return result;
    } catch { return this.store.get(`request:${request_id}`); }
  }
}
