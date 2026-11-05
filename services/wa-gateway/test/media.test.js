import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { Readable } from 'node:stream';
import { Store } from '../src/store.js';
import { Mirror } from '../src/mirror.js';
import { mediaOf, sniff, registerMedia, loadMedia, KINDS } from '../src/media.js';

const phone = '+51911111111', business = '+51900000000';
const ogg = Buffer.concat([Buffer.from('OggS'), Buffer.alloc(40, 1)]);
const mp4 = Buffer.concat([Buffer.alloc(4), Buffer.from('ftypisom'), Buffer.alloc(40)]);
const webp = Buffer.concat([Buffer.from('RIFF'), Buffer.alloc(4), Buffer.from('WEBP'), Buffer.alloc(20)]);
function setup(t) {
  const store = new Store(':memory:', 'ab'.repeat(32)); t.after(() => store.close());
  const mirror = new Mirror(store, business);
  mirror.socket = { user: { id: business.slice(1) + '@s.whatsapp.net' },
    signalRepository: { lidMapping: { getPNForLID: async () => null } } };
  mirror.state = 'connected';
  return { store, mirror };
}
const incoming = message => ({ key: { id: randomUUID(), remoteJid: phone.slice(1) + '@s.whatsapp.net' },
  messageTimestamp: 1800000000, message });

test('each media message is classified, voice notes apart from audio files', () => {
  assert.equal(mediaOf({ audioMessage: { ptt: true, seconds: 23 } }, 'audioMessage').kind, 'voice');
  assert.equal(mediaOf({ audioMessage: { ptt: true, seconds: 23 } }, 'audioMessage').seconds, 23);
  assert.equal(mediaOf({ audioMessage: { seconds: 5 } }, 'audioMessage').kind, 'audio');
  const doc = mediaOf({ documentMessage: { fileName: 'receta\u0000.pdf', fileLength: 2048, caption: 'Hola' } }, 'documentMessage');
  assert.deepEqual([doc.kind, doc.name, doc.size, doc.caption], ['document', 'receta.pdf', 2048, 'Hola']);
  assert.equal(mediaOf({ videoMessage: { seconds: 9 } }, 'videoMessage').kind, 'video');
  assert.equal(mediaOf({ stickerMessage: {} }, 'stickerMessage').kind, 'sticker');
  assert.equal(mediaOf({ conversation: 'hola' }, 'conversation'), null);
  assert.equal(mediaOf({ locationMessage: {} }, 'locationMessage'), null);
});

test('the type comes from the bytes, never from what the sender declared', () => {
  assert.equal(sniff('voice', ogg), 'audio/ogg');
  assert.equal(sniff('audio', Buffer.concat([Buffer.from('ID3'), Buffer.alloc(20)])), 'audio/mpeg');
  assert.equal(sniff('audio', mp4), 'audio/mp4');
  assert.equal(sniff('video', mp4), 'video/mp4');
  assert.equal(sniff('sticker', webp), 'image/webp');
  assert.equal(sniff('document', Buffer.from('%PDF-1.7 ...')), 'application/pdf');
  // A page or script posing as a document is only ever a download.
  assert.equal(sniff('document', Buffer.from('<html><script>x</script>'), 'text/html'), 'application/octet-stream');
  assert.equal(sniff('document', Buffer.from('PK\u0003\u0004'), 'application/zip'), 'application/zip');
  assert.throws(() => sniff('voice', Buffer.from('<svg/>')), /unsupported_media/);
  assert.throws(() => sniff('sticker', ogg), /unsupported_media/);
});

test('a voice note is downloaded on arrival and a failed download stays retryable', async t => {
  const { store } = setup(t);
  const message = incoming({ audioMessage: { ptt: true, seconds: 12 } });
  const id = registerMedia(store, phone, message, mediaOf(message.message, 'audioMessage'));
  await assert.rejects(loadMedia(store, null, id, async () => { throw new Error('offline'); }), /offline/);
  assert.ok(store.get(`media:${id}`).message);
  let downloads = 0;
  const downloader = async () => { downloads++; return Readable.from([ogg]); };
  const media = await loadMedia(store, null, id, downloader);
  assert.deepEqual([media.kind, media.mime, media.seconds, media.phone], ['voice', 'audio/ogg', 12, phone]);
  assert.equal(media.data, ogg.toString('base64'));
  await loadMedia(store, null, id, downloader);
  assert.equal(downloads, 1);
  const ciphertext = store.db.prepare('SELECT value FROM kv WHERE key=?').get(store.hash(`media:${id}`)).value;
  assert.equal(Buffer.from(ciphertext).includes(Buffer.from(ogg.toString('base64'))), false);
});

test('too large or unrecognised files are refused', async t => {
  const { store } = setup(t);
  const sticker = incoming({ stickerMessage: {} });
  const big = registerMedia(store, phone, sticker, mediaOf(sticker.message, 'stickerMessage'));
  await assert.rejects(loadMedia(store, null, big, async () => Readable.from([Buffer.alloc(KINDS.sticker.limit + 1)])), /media_too_large/);
  const audio = incoming({ audioMessage: {} });
  const odd = registerMedia(store, phone, audio, mediaOf(audio.message, 'audioMessage'));
  await assert.rejects(loadMedia(store, null, odd, async () => Readable.from([Buffer.from('not audio at all')])), /unsupported_media/);
  await assert.rejects(loadMedia(store, null, 'nope'), /invalid_media_id/);
});

test('the connector reports each kind with its duration, name and size, and keeps view-once out', async t => {
  const { store, mirror } = setup(t);
  mirror.media = async () => ({}); // downloads are not what this test is about
  await mirror.message(incoming({ audioMessage: { ptt: true, seconds: 31 } }));
  await mirror.message(incoming({ videoMessage: { seconds: 7, caption: 'Mira' } }));
  await mirror.message(incoming({ documentMessage: { fileName: 'examenes.pdf', fileLength: 5000 } }));
  await mirror.message(incoming({ stickerMessage: {} }));
  await mirror.message(incoming({ viewOnceMessage: { message: { audioMessage: { seconds: 3 } } } }));
  await mirror.message(incoming({ conversation: 'hola' }));
  const [voice, video, document, sticker, once, text] = store.events();
  assert.deepEqual([voice.media_kind, voice.media_seconds, voice.body], ['voice', 31, '']);
  assert.deepEqual([video.media_kind, video.media_seconds, video.body], ['video', 7, 'Mira']);
  assert.deepEqual([document.media_kind, document.media_name, document.media_size], ['document', 'examenes.pdf', 5000]);
  assert.equal(sticker.media_kind, 'sticker');
  assert.match(voice.media_id, /^[a-f0-9]{64}$/);
  assert.deepEqual([once.media_id, once.media_kind], [null, null]);       // stays on the phone
  assert.equal(text.media_kind, null);
  assert.equal(text.body, 'hola');
});

test('a message stored before media support can be adopted while WhatsApp still serves it', async t => {
  const { store, mirror } = setup(t);
  mirror.media = async () => ({});
  mirror.image = async () => ({});
  store.set('message:old-audio', { audioMessage: { ptt: true, seconds: 8 } });
  store.set('message:old-photo', { imageMessage: { caption: 'foto' } });
  store.set('message:old-once', { viewOnceMessage: { message: { audioMessage: {} } } });
  store.set('message:old-text', { conversation: 'hola' });
  const audio = mirror.adopt(phone, 'old-audio');
  assert.deepEqual([audio.adopted, audio.media_kind, audio.media_seconds], [true, 'voice', 8]);
  assert.match(audio.media_id, /^[a-f0-9]{64}$/);
  assert.equal(mirror.adopt(phone, 'old-photo').media_kind, 'image');
  assert.equal(mirror.adopt(phone, 'old-once').reason, 'view_once');
  assert.equal(mirror.adopt(phone, 'old-text').reason, 'not_media');
  assert.equal(mirror.adopt(phone, 'never-seen').reason, 'not_stored');
  assert.throws(() => mirror.adopt('no-phone', 'old-audio'), /invalid_adopt/);
});
