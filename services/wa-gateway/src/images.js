import { createHash } from 'node:crypto';
import { downloadMediaMessage } from '@whiskeysockets/baileys';
import pino from 'pino';

export const MAX_IMAGE = 8 * 1024 * 1024;
export function isViewOnce(content, depth = 0) {
  if (!content || depth > 8) return false;
  if (content.viewOnceMessage || content.viewOnceMessageV2 || content.viewOnceMessageV2Extension ||
      content.imageMessage?.viewOnce || content.videoMessage?.viewOnce ||
      content.audioMessage?.viewOnce) return true;
  return isViewOnce(content.ephemeralMessage?.message, depth + 1) ||
    isViewOnce(content.documentWithCaptionMessage?.message, depth + 1);
}
export function imageMime(bytes) {
  if (bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return 'image/jpeg';
  if (bytes.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex'))) return 'image/png';
  if (bytes.toString('ascii', 0, 4) === 'RIFF' && bytes.toString('ascii', 8, 12) === 'WEBP') return 'image/webp';
  throw new Error('unsupported_image');
}
export function uploadImage(store, phone, data) {
  if (!/^\+[1-9]\d{7,14}$/.test(phone || '') || typeof data !== 'string' ||
      data.length > Math.ceil(MAX_IMAGE / 3) * 4 || !/^[A-Za-z0-9+/]+={0,2}$/.test(data)) throw new Error('invalid_image');
  const bytes = Buffer.from(data, 'base64');
  if (!bytes.length || bytes.length > MAX_IMAGE) throw new Error('image_too_large');
  const mime = imageMime(bytes);
  const id = createHash('sha256').update(phone).update(bytes).digest('hex');
  store.set(`image:${id}`, { phone, mime, data: bytes.toString('base64') });
  return { media_id: id };
}
export function registerImage(store, phone, message) {
  const id = createHash('sha256').update(`${phone}:${message.key.id}`).digest('hex');
  if (!store.get(`image:${id}`)) store.set(`image:${id}`, { phone, message });
  return id;
}
export async function loadImage(store, socket, id, downloader = downloadMediaMessage) {
  if (!/^[a-f0-9]{64}$/.test(id || '')) throw new Error('invalid_image_id');
  const saved = store.get(`image:${id}`);
  if (!saved) throw new Error('image_not_found');
  if (saved.data) return saved;
  const controller = new AbortController();
  let stream;
  let rejectTimeout;
  const timeout = new Promise((_, reject) => { rejectTimeout = reject; });
  const timer = setTimeout(() => {
    controller.abort(); stream?.destroy(new Error('image_timeout'));
    rejectTimeout(new Error('image_timeout'));
  }, 15000);
  try {
    return await Promise.race([timeout, (async () => {
      stream = await downloader(saved.message, 'stream', { options: { signal: controller.signal } },
        socket ? { logger: pino({ level: 'silent' }), reuploadRequest: m => socket.updateMediaMessage(m) } : undefined);
      if (controller.signal.aborted) { stream.destroy(); throw new Error('image_timeout'); }
      const chunks = []; let size = 0;
      for await (const part of stream) {
        size += part.length;
        if (size > MAX_IMAGE) throw new Error('image_too_large');
        chunks.push(part);
      }
      const bytes = Buffer.concat(chunks);
      const image = { phone: saved.phone, mime: imageMime(bytes), data: bytes.toString('base64') };
      store.set(`image:${id}`, image);
      return image;
    })()]);
  } finally { clearTimeout(timer); stream?.destroy(); }
}
