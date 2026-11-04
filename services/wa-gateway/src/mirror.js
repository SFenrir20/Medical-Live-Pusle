import { registerImage, loadImage, isViewOnce } from './images.js';
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
  constructor(store, expectedPhone, socketFactory = makeWASocket) {
    expectedPhone = expectedPhone?.trim() || null;
    if (expectedPhone && !/^\+[1-9]\d{7,14}$/.test(expectedPhone)) throw new Error('WA_EXPECTED_PHONE must be E.164 when set');
    this.store = store; this.socketFactory = socketFactory;
    const previous = store.get('account');
    if (previous && expectedPhone && previous !== expectedPhone) throw new Error('This volume belongs to another WhatsApp number');
    this.expectedPhone = previous || expectedPhone;
    this.state = 'disconnected'; this.qr = null; this.socket = null;
    this.eventsTail = Promise.resolve(); this.sendTail = Promise.resolve();
    this.retryTimer = null; this.attempt = 0;
    this.imageDownloads = new Map();
    this.imageSlots = [Promise.resolve(), Promise.resolve()];
    this.nextImageSlot = 0;
  }
  status() { return { state: this.state, phone: this.expectedPhone, qr: this.qr, unresolved: this.store.pendingCount() }; }
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
  handler(fn) {
    return data => {
      this.eventsTail = this.eventsTail.then(() => fn(data)).catch(() => {
        // Do not continue acknowledging messages if persistence failed.
        console.error('WhatsApp event persistence failed; restarting connector');
        process.exitCode = 1;
        this.socket?.end(new Error('Persistence failure'));
        setTimeout(() => process.exit(1), 100).unref();
      });
    };
  }
  connect() {
    if (['connected', 'connecting', 'qr'].includes(this.state)) return;
    if (['relink_required', 'wrong_number'].includes(this.state)) this.store.resetAuth();
    clearTimeout(this.retryTimer);
    this.state = 'connecting'; this.qr = null;
    const auth = this.store.auth();
    const socket = this.socketFactory({ auth: auth.state, logger: pino({ level: 'silent' }),
      browser: ['Medical Social Pulse', 'Chrome', '1.0.0'], markOnlineOnConnect: false,
      syncFullHistory: false, shouldSyncHistoryMessage: () => false,
      getMessage: async key => this.store.get(`message:${key.id}`),
    });
    this.socket = socket;
    socket.ev.on('creds.update', () => { if (socket === this.socket) auth.save(); });
    socket.ev.on('connection.update', this.handler(async update => {
      if (socket !== this.socket) return;
      if (update.qr) { this.state = 'qr'; this.qr = await QRCode.toDataURL(update.qr); }
      if (update.connection === 'open') {
        if (!this.bindAccount(socket.user?.id)) {
          this.state = 'wrong_number'; this.qr = null;
          await socket.logout(); return;
        }
        this.state = 'connected'; this.qr = null; this.attempt = 0;
        await this.retryPending();
      }
      if (update.connection === 'close') {
        this.qr = null;
        const code = update.lastDisconnect?.error?.output?.statusCode;
        if (this.state === 'wrong_number') return;
        if ([DisconnectReason.loggedOut, DisconnectReason.badSession, DisconnectReason.connectionReplaced].includes(code)) {
          this.state = 'relink_required'; return;
        }
        this.state = 'disconnected';
        this.retryTimer = setTimeout(() => this.connect(), Math.min(60000, 2000 * 2 ** this.attempt++));
      }
    }));
    socket.ev.on('messages.upsert', this.handler(async ({ messages }) => {
      for (const message of messages) await this.message(message);
    }));
    socket.ev.on('lid-mapping.update', this.handler(() => this.retryPending()));
    socket.ev.on('messages.update', this.handler(async updates => {
      for (const { key, update } of updates) {
        if (!key.fromMe || ![2, 3, 4, 5].includes(update.status)) continue;
        const status = update.status >= 4 ? 'read' : update.status === 3 ? 'delivered' : 'sent';
        await this.receipt(key, status, new Date().toISOString(), 'observed');
      }
    }));
    socket.ev.on('message-receipt.update', this.handler(async updates => {
      for (const { key, receipt } of updates) {
        if (!key.fromMe) continue;
        if (receipt.receiptTimestamp) await this.receipt(key, 'delivered', timestamp(receipt.receiptTimestamp), 'provider');
        if (receipt.readTimestamp) await this.receipt(key, 'read', timestamp(receipt.readTimestamp), 'provider');
      }
    }));
  }
  async resolve(key) {
    if (!key.remoteJid || !/@(s\.whatsapp\.net|lid)$/.test(key.remoteJid)) return null;
    return phoneFromJid(key.remoteJid) || phoneFromJid(key.remoteJidAlt) ||
      phoneFromJid(await this.socket.signalRepository.lidMapping.getPNForLID(key.remoteJid));
  }
  async retryPending() {
    for (const pending of this.store.pending()) {
      if (pending.type === 'message') await this.message(pending.message);
      else await this.receipt(pending.key, pending.status, pending.at, pending.clock);
    }
  }
  async message(message) {
    if (!this.matchesAccount()) return;
    const { key } = message;
    if (!key.id || !message.message) return;
    const content = normalizeMessageContent(message.message), type = getContentType(content);
    if (!type || ['protocolMessage', 'senderKeyDistributionMessage', 'reactionMessage'].includes(type)) return;
    const phone = await this.resolve(key);
    if (!phone) {
      if (key.remoteJid?.endsWith('@lid')) this.store.set(`m:${key.id}`, { type: 'message', message }, 'pending');
      return;
    }
    const at = timestamp(message.messageTimestamp) || new Date().toISOString();
    const caption = content.imageMessage?.caption || content.videoMessage?.caption || '';
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
    this.store.transaction(() => {
      this.store.set(`m:${key.id}`, null, 'pending');
      this.store.set(`message:${key.id}`, message.message);
      this.store.event({ type: 'message', external_id: key.id, phone, body: media_id ? (caption || '[Imagen]') : body.slice(0, 20000),
        from_me: !!key.fromMe, request_id: intent?.request_id || null, at,
        name: key.fromMe ? null : message.pushName, media_type: type, media_id });
      if (intent) this.store.set(`request:${intent.request_id}`, { ...intent, state: 'sent', at });
    });
    if (media_id) void this.image(media_id).catch(() => {}); // Retry on view if temporarily unavailable.
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
    const external_id = generateMessageIDV2(this.socket.user.id);
    const intent = { request_id, phone, text, media_id, external_id, state: 'unknown' };
    this.store.transaction(() => {
      this.store.set(`request:${request_id}`, intent);
      this.store.set(`outgoing:${external_id}`, intent);
    });
    try {
      let timer;
      const attempt = this.socket.sendMessage(phone.slice(1) + '@s.whatsapp.net', image
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
