import { createHash } from 'node:crypto';
import { downloadMediaMessage } from '@whiskeysockets/baileys';
import pino from 'pino';

// Audio, voice notes, video, documents and stickers (images keep their own path in images.js).
// Same rules as images: the file is bound to its contact, stored encrypted, downloaded when it
// arrives (small kinds) or on first view (large kinds), and view-once media is never kept.
export const KINDS = {
  voice:    { label: 'Nota de voz', limit: 16 * 1024 * 1024, eager: true },
  audio:    { label: 'Audio', limit: 16 * 1024 * 1024, eager: true },
  sticker:  { label: 'Sticker', limit: 1024 * 1024, eager: true },
  video:    { label: 'Video', limit: 24 * 1024 * 1024, eager: false },
  document: { label: 'Documento', limit: 24 * 1024 * 1024, eager: false },
};
const TYPES = { audioMessage: 'audio', videoMessage: 'video', documentMessage: 'document',
  stickerMessage: 'sticker' };
const SAFE_DOCUMENT = /^(application\/(msword|rtf|zip|vnd\.ms-(excel|powerpoint)|vnd\.openxmlformats-officedocument\.[a-z.]+)|text\/(plain|csv))$/;

const count = value => {
  const n = Number(value?.toNumber ? value.toNumber() : value);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : null;
};

/** What a non-image media message is, or null when it is not one (text, contact, location...). */
export function mediaOf(content, type) {
  const kind = TYPES[type];
  if (!kind || !content?.[type]) return null;
  const part = content[type];
  return {
    kind: kind === 'audio' && part.ptt ? 'voice' : kind,
    seconds: count(part.seconds),
    name: kind === 'document' ? String(part.fileName || '').replace(/[\u0000-\u001f]/g, '').slice(0, 200) || null : null,
    size: count(part.fileLength),
    caption: String(part.caption || ''),
  };
}

const ascii = (bytes, from, to) => bytes.toString('latin1', from, to);
const brand = bytes => ascii(bytes, 8, 12);

/** The real type of the bytes, from their content and never from what the sender declared. */
export function sniff(kind, bytes, declared = '') {
  const head = bytes.subarray(0, 16);
  if (kind === 'sticker') {
    if (ascii(head, 0, 4) === 'RIFF' && ascii(head, 8, 12) === 'WEBP') return 'image/webp';
  } else if (kind === 'audio' || kind === 'voice') {
    if (ascii(head, 0, 4) === 'OggS') return 'audio/ogg';
    if (ascii(head, 0, 3) === 'ID3' || (head[0] === 0xff && (head[1] & 0xe0) === 0xe0)) return 'audio/mpeg';
    if (ascii(head, 4, 8) === 'ftyp') return 'audio/mp4';
    if (head.subarray(0, 4).equals(Buffer.from('1a45dfa3', 'hex'))) return 'audio/webm';
    if (ascii(head, 0, 4) === 'RIFF' && ascii(head, 8, 12) === 'WAVE') return 'audio/wav';
    if (ascii(head, 0, 5) === '#!AMR') return 'audio/amr';
  } else if (kind === 'video') {
    if (ascii(head, 4, 8) === 'ftyp') return brand(head).startsWith('3g') ? 'video/3gpp' : 'video/mp4';
    if (head.subarray(0, 4).equals(Buffer.from('1a45dfa3', 'hex'))) return 'video/webm';
  } else if (kind === 'document') {
    if (ascii(head, 0, 4) === '%PDF') return 'application/pdf';
    // Anything else is only ever offered as a download, never rendered by the browser.
    return SAFE_DOCUMENT.test(declared) ? declared : 'application/octet-stream';
  }
  throw new Error('unsupported_media');
}

export function mediaId(phone, messageId) {
  return createHash('sha256').update(`media:${phone}:${messageId}`).digest('hex');
}

export function registerMedia(store, phone, message, info) {
  const id = mediaId(phone, message.key.id);
  const { caption, ...record } = info;
  if (!store.get(`media:${id}`)) store.set(`media:${id}`, { phone, message, ...record });
  return id;
}

export async function loadMedia(store, socket, id, downloader = downloadMediaMessage) {
  if (!/^[a-f0-9]{64}$/.test(id || '')) throw new Error('invalid_media_id');
  const saved = store.get(`media:${id}`);
  if (!saved) throw new Error('media_not_found');
  if (saved.data) return saved;
  const limit = KINDS[saved.kind].limit;
  const controller = new AbortController();
  let stream;
  let rejectTimeout;
  const timeout = new Promise((_, reject) => { rejectTimeout = reject; });
  const timer = setTimeout(() => {
    controller.abort(); stream?.destroy(new Error('media_timeout'));
    rejectTimeout(new Error('media_timeout'));
  }, 30000);
  try {
    return await Promise.race([timeout, (async () => {
      stream = await downloader(saved.message, 'stream', { options: { signal: controller.signal } },
        socket ? { logger: pino({ level: 'silent' }), reuploadRequest: m => socket.updateMediaMessage(m) } : undefined);
      if (controller.signal.aborted) { stream.destroy(); throw new Error('media_timeout'); }
      const chunks = []; let size = 0;
      for await (const part of stream) {
        size += part.length;
        if (size > limit) throw new Error('media_too_large');
        chunks.push(part);
      }
      const bytes = Buffer.concat(chunks);
      const declared = saved.message?.message?.documentMessage?.mimetype || '';
      const media = { phone: saved.phone, kind: saved.kind, name: saved.name, seconds: saved.seconds,
        mime: sniff(saved.kind, bytes, declared), data: bytes.toString('base64') };
      store.set(`media:${id}`, media);
      return media;
    })()]);
  } finally { clearTimeout(timer); stream?.destroy(); }
}
