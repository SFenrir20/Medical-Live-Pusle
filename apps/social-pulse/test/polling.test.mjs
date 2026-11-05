import test from "node:test";
import assert from "node:assert/strict";
import { setImmediate } from "node:timers/promises";
import { pollVisible } from "../src/features/chats/polling.ts";

function browser(t) {
  const originals = new Map(
    ["document", "window", "navigator"].map((k) => [
      k,
      Object.getOwnPropertyDescriptor(globalThis, k),
    ]),
  );
  const document = Object.assign(new EventTarget(), { hidden: false });
  const window = new EventTarget();
  for (const [key, value] of Object.entries({ document, window, navigator: { onLine: true } }))
    Object.defineProperty(globalThis, key, { value, configurable: true });
  t.after(() => {
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  });
  t.mock.timers.enable({ apis: ["setTimeout"] });
  return { document, window };
}

test("resume catches up once and never overlaps a running request", async (t) => {
  const { window } = browser(t);
  let calls = 0,
    release;
  const stop = pollVisible(
    async () => {
      calls++;
      await new Promise((resolve) => {
        release = resolve;
      });
    },
    4000,
    assert.fail,
  );
  t.after(stop);
  t.mock.timers.tick(0);
  assert.equal(calls, 1);
  window.dispatchEvent(new Event("online"));
  window.dispatchEvent(new Event("focus"));
  assert.equal(calls, 1);
  release();
  await setImmediate();
  t.mock.timers.tick(0);
  assert.equal(calls, 2);
  release();
  await setImmediate();
  t.mock.timers.tick(3999);
  assert.equal(calls, 2);
});

test("hidden tabs pause; cleanup aborts in-flight work and removes resume listeners", async (t) => {
  const { document, window } = browser(t);
  document.hidden = true;
  let calls = 0,
    signal,
    release;
  const stop = pollVisible(
    async (s) => {
      calls++;
      signal = s;
      await new Promise((resolve) => {
        release = resolve;
      });
    },
    4000,
    assert.fail,
  );
  t.mock.timers.tick(0);
  await setImmediate();
  assert.equal(calls, 0);
  document.hidden = false;
  document.dispatchEvent(new Event("visibilitychange"));
  assert.equal(calls, 1);
  stop();
  assert.equal(signal.aborted, true);
  release();
  await setImmediate();
  window.dispatchEvent(new Event("online"));
  t.mock.timers.tick(10_000);
  assert.equal(calls, 1);
});
