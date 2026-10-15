import { useEffect, useState } from "react";
import { errorMessage, fetchLives, fetchSummary, LiveApi, Summary } from "./api";

/** Supervisor/marketing board: unassigned load, team and broadcasts, straight from the API. */
export function useBoard(withLives: boolean) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [lives, setLives] = useState<LiveApi[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [nextSummary, nextLives] = await Promise.all([
          fetchSummary(),
          withLives ? fetchLives() : Promise.resolve([] as LiveApi[]),
        ]);
        if (cancelled) return;
        setSummary(nextSummary);
        setLives(nextLives);
        setError(null);
      } catch (err) {
        if (!cancelled) setError(errorMessage(err, "No se pudo cargar el panel."));
      } finally {
        if (!cancelled) setLoading(false);
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
  }, [withLives]);

  return { summary, lives, error, loading };
}
