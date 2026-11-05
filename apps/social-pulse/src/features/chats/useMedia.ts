import { useCallback, useEffect, useState } from "react";
import { chatApi } from "./api";

/** Files of WhatsApp messages. The browser cannot send the login header from <audio src>, so each
 *  file is fetched as a blob and played from an object URL. To keep the inbox fluid:
 *  - at most 3 downloads run at once (a chat full of voice notes does not freeze the page);
 *  - a file already downloaded is reused when you scroll back or reopen the chat;
 *  - object URLs not in use are released beyond a limit, so memory does not grow. */
type Entry = { url: string; type: string; refs: number };

const MAX_CACHED = 80;
const MAX_PARALLEL = 3;

const entries = new Map<number, Entry>(); // insertion order = least recently used first
const loading = new Map<number, Promise<Entry>>();
const waiting: (() => void)[] = [];
let active = 0;

function slot(): Promise<void> {
  if (active < MAX_PARALLEL) {
    active += 1;
    return Promise.resolve();
  }
  return new Promise((resolve) =>
    waiting.push(() => {
      active += 1;
      resolve();
    }),
  );
}
function release() {
  active -= 1;
  waiting.shift()?.();
}

function trim() {
  for (const [id, entry] of entries) {
    if (entries.size <= MAX_CACHED) break;
    if (entry.refs > 0) continue;
    URL.revokeObjectURL(entry.url);
    entries.delete(id);
  }
}

function load(id: number): Promise<Entry> {
  const known = entries.get(id);
  if (known) {
    entries.delete(id); // touched: now the most recent
    entries.set(id, known);
    return Promise.resolve(known);
  }
  const running = loading.get(id);
  if (running) return running;
  const job = (async () => {
    await slot();
    try {
      const blob = await chatApi.media(id);
      const entry: Entry = { url: URL.createObjectURL(blob), type: blob.type, refs: 0 };
      entries.set(id, entry);
      trim();
      return entry;
    } finally {
      release();
    }
  })().finally(() => loading.delete(id));
  loading.set(id, job);
  return job;
}

export type MediaState = {
  url: string;
  type: string;
  status: "idle" | "loading" | "ready" | "error";
  retry: () => void;
};

/** Downloads the file of a message once `enabled` is true (e.g. when it scrolls into view). */
export function useMedia(messageId: number, enabled: boolean): MediaState {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<Omit<MediaState, "retry">>(() => {
    const known = entries.get(messageId);
    return known
      ? { url: known.url, type: known.type, status: "ready" }
      : { url: "", type: "", status: "idle" };
  });

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let held: Entry | null = null;
    setState((old) => (old.status === "ready" ? old : { url: "", type: "", status: "loading" }));
    load(messageId)
      .then((entry) => {
        if (cancelled) return;
        entry.refs += 1;
        held = entry;
        setState({ url: entry.url, type: entry.type, status: "ready" });
      })
      .catch(() => {
        if (!cancelled) setState({ url: "", type: "", status: "error" });
      });
    return () => {
      cancelled = true;
      if (held) {
        held.refs -= 1;
        trim();
      }
    };
  }, [messageId, enabled, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, retry };
}

/** True once the element has come near the visible area (and stays true). */
export function useNearScreen(margin = "300px") {
  const [near, setNear] = useState(false);
  const [node, setNode] = useState<Element | null>(null);
  useEffect(() => {
    if (!node || near) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin: margin },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [node, near, margin]);
  return { near, ref: setNode };
}

/** Saves a downloaded file under its real name. */
export async function saveAs(messageId: number, name: string) {
  const entry = await load(messageId);
  const link = document.createElement("a");
  link.href = entry.url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
}
