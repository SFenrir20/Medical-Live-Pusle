import { useAuth } from "@/context/AuthContext";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchTeamPresence, PresenceState, sendHeartbeat, TeamPresenceResponse } from "./api";

/** The person counts as "in front of the CRM" if the tab is visible and she touched it recently. */
const ACTIVE_WINDOW_MS = 5 * 60 * 1000;
const EVENTS = ["mousemove", "keydown", "click", "touchstart", "scroll"] as const;

/** Heartbeat of a sales agent. While this runs she shows as connected (green) and receives new
 *  contacts in rotation; closing the app, or no heartbeat for ~1 min, turns her red and what she
 *  has not worked yet is handed to the others. */
export function usePresence(enabled: boolean) {
  const [presence, setPresence] = useState<PresenceState | null>(null);
  const [failed, setFailed] = useState(false);
  const lastActivity = useRef(Date.now());
  const { user } = useAuth();
  const tabId = useRef(crypto.randomUUID());
  const inFlight = useRef(false);
  const pendingAction = useRef<"available" | "paused" | "offline" | undefined>(undefined);
  const storageKey = `social-pulse-presence:${user?.id ?? "none"}`;
  // Each tab publishes a short lease. A hidden tab must not turn an active tab yellow.
  const visibleInAnyTab = useCallback(() => {
    const now = Date.now();
    const local =
      document.visibilityState === "visible" && now - lastActivity.current < ACTIVE_WINDOW_MS;
    try {
      const tabs = JSON.parse(localStorage.getItem(storageKey) || "{}") as Record<
        string,
        { at: number; active: boolean }
      >;
      for (const id of Object.keys(tabs)) if (now - tabs[id].at > 45000) delete tabs[id];
      tabs[tabId.current] = { at: now, active: local };
      localStorage.setItem(storageKey, JSON.stringify(tabs));
      return Object.values(tabs).some((t) => t.active);
    } catch {
      return local;
    }
  }, [storageKey]);

  const beat = useCallback(
    async function heartbeat(status?: "available" | "paused" | "offline") {
      if (inFlight.current) {
        if (status) pendingAction.current = status;
        return;
      }
      inFlight.current = true;
      if (status === "available") lastActivity.current = Date.now();
      try {
        setPresence(await sendHeartbeat(visibleInAnyTab(), status));
        setFailed(false);
      } catch {
        setFailed(true);
      } finally {
        inFlight.current = false;
        const pending = pendingAction.current;
        pendingAction.current = undefined;
        if (pending) void heartbeat(pending);
      }
    },
    [visibleInAnyTab],
  );

  useEffect(() => {
    if (!enabled) return;
    const touch = () => {
      lastActivity.current = Date.now();
    };
    EVENTS.forEach((name) => window.addEventListener(name, touch, { passive: true }));
    const onVisible = () => {
      void beat();
    };
    document.addEventListener("visibilitychange", onVisible);
    void beat();
    const timer = window.setInterval(() => void beat(), 20000);
    return () => {
      EVENTS.forEach((name) => window.removeEventListener(name, touch));
      document.removeEventListener("visibilitychange", onVisible);
      window.clearInterval(timer);
      try {
        const tabs = JSON.parse(localStorage.getItem(storageKey) || "{}");
        delete tabs[tabId.current];
        localStorage.setItem(storageKey, JSON.stringify(tabs));
      } catch {
        /* browser storage unavailable */
      }
    };
  }, [enabled, beat, storageKey]);

  return {
    presence,
    failed,
    setStatus: (status: "available" | "paused" | "offline") => void beat(status),
  };
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
