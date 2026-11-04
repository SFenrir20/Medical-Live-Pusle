import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { Readable } from 'node:stream';
import { Store } from '../src/store.js';
import { Mirror } from '../src/mirror.js';
import { uploadImage, registerImage, loadImage, MAX_IMAGE } from '../src/images.js';

const phone = '+51911111111', business = '+51900000000';
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==', 'base64');
function setup(t) {
  const store = new Store(':memory:', 'ab'.repeat(32)); t.after(() => store.close());
  const mirror = new Mirror(store, business);
  mirror.socket = { user: { id: business.slice(1) + '@s.whatsapp.net' } };
  mirror.state = 'connected';
  return { store, mirror };
}

test('image upload is bound to contact, encrypted, and send retries do not resend', async t => {
  const { store, mirror } = setup(t);
  const { media_id } = uploadImage(store, phone, png.toString('base64'));
  const ciphertext = store.db.prepare('SELECT value FROM kv WHERE key=?').get(store.hash(`image:${media_id}`)).value;
  assert.equal(Buffer.from(ciphertext).includes(Buffer.from(png.toString('base64'))), false);
  let sends = 0;
  mirror.socket.sendMessage = async (jid, content, options) => {
    sends++; assert.deepEqual(content.image, png); assert.equal(content.caption, 'Descripción');
    return { key: { id: options.messageId, remoteJid: jid, fromMe: true }, messageTimestamp: 1800000000,
      message: { imageMessage: { caption: content.caption, mimetype: content.mimetype } } };
  };
  const request = { request_id: randomUUID(), phone, text: 'Descripción', media_id };
  assert.equal((await mirror.send(request)).state, 'sent');
  assert.equal((await mirror.send(request)).state, 'sent');
  assert.equal(sends, 1);
  assert.equal(store.events()[0].media_id, media_id);
  await assert.rejects(mirror.send({ ...request, request_id: randomUUID(), phone: '+51922222222' }), /image_phone_mismatch/);
  assert.equal(sends, 1);
});

test('download is persisted for subsequent views, and failed downloads remain retryable', async t => {
  const { store } = setup(t);
  const message = { key: { id: 'incoming' }, message: { imageMessage: {} } };
  const id = registerImage(store, phone, message);
  await assert.rejects(loadImage(store, null, id, async () => { throw new Error('offline'); }), /offline/);
  assert.ok(store.get(`image:${id}`).message);
  let downloads = 0;
  const downloader = async () => { downloads++; return Readable.from([png]); };
  const image = await loadImage(store, null, id, downloader);
  assert.equal(image.mime, 'image/png');
  assert.equal(image.data, png.toString('base64'));
  await loadImage(store, null, id, downloader);
  assert.equal(downloads, 1);
});

test('oversize/unsupported attachments are rejected; view-once and stickers have no image attachment', async t => {
  const { store, mirror } = setup(t);
  assert.throws(() => uploadImage(store, phone, Buffer.from('<svg/>').toString('base64')), /unsupported_image/);
  const id = registerImage(store, phone, { key: { id: 'large' }, message: { imageMessage: {} } });
  await assert.rejects(loadImage(store, null, id, async () => Readable.from([Buffer.alloc(MAX_IMAGE + 1)])), /image_too_large/);
  for (const message of [{ viewOnceMessage: { message: { imageMessage: { caption: 'privada' } } } },
    { ephemeralMessage: { message: { viewOnceMessageV2: { message: { imageMessage: {} } } } } },
    { stickerMessage: { mimetype: 'image/webp' } }]) {
    await mirror.message({ key: { id: randomUUID(), remoteJid: phone.slice(1) + '@s.whatsapp.net' },
      messageTimestamp: 1800000000, message });
  }
  assert.equal(store.events().length, 3);
  assert.ok(store.events().every(e => e.media_id === null));
});
