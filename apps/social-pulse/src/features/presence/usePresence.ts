import { useCallback, useEffect, useRef, useState } from "react";
import { fetchTeamPresence, PresenceState, sendHeartbeat, TeamPresenceResponse } from "./api";

/** The person counts as "in front of the CRM" if the tab is visible and she touched it recently. */
const ACTIVE_WINDOW_MS = 2 * 60 * 1000;
const EVENTS = ["mousemove", "keydown", "click", "touchstart", "scroll"] as const;

/** Heartbeat of a sales agent. While this runs she shows as connected (green) and receives new
 *  contacts in rotation; closing the app, or no heartbeat for ~1 min, turns her red and what she
 *  has not worked yet is handed to the others. */
export function usePresence(enabled: boolean) {
  const [presence, setPresence] = useState<PresenceState | null>(null);
  const [failed, setFailed] = useState(false);
  const lastActivity = useRef(Date.now());

  const beat = useCallback(async (status?: "available" | "paused") => {
    const visible =
      document.visibilityState === "visible" &&
      Date.now() - lastActivity.current < ACTIVE_WINDOW_MS;
    try {
      setPresence(await sendHeartbeat(visible, status));
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const touch = () => {
      lastActivity.current = Date.now();
    };
    EVENTS.forEach((name) => window.addEventListener(name, touch, { passive: true }));
    const onVisible = () => {
      if (document.visibilityState === "visible") void beat();
    };
    document.addEventListener("visibilitychange", onVisible);
    void beat();
    const timer = window.setInterval(() => void beat(), 20000);
    return () => {
      EVENTS.forEach((name) => window.removeEventListener(name, touch));
      document.removeEventListener("visibilitychange", onVisible);
      window.clearInterval(timer);
    };
  }, [enabled, beat]);

  return { presence, failed, setStatus: (status: "available" | "paused") => void beat(status) };
}

/** Supervisor view: lights, load and time connected of every agent. */
export function useTeamPresence(enabled: boolean) {
  const [data, setData] = useState<TeamPresenceResponse | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const load = async () => {
      try {
        const next = await fetchTeamPresence();
        if (!cancelled) setData(next);
      } catch {
        /* the board keeps the last values; the next tick retries */
      }
    };
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [enabled]);

  return data;
}
