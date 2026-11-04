import { useEffect, useState } from "react";
import apiClient from "@/services/api";
import type { LiveCardItem } from "./LivesCard";

export function useActiveLives() {
  const [lives, setLives] = useState<LiveCardItem[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let stopped = false;
    const load = async () => {
      try {
        const { data } = await apiClient.get<{ items: LiveCardItem[] }>("/crm/active-lives");
        if (!stopped) {
          setLives(data.items);
          setError("");
        }
      } catch {
        if (!stopped) setError("No se pudo actualizar el estado de las transmisiones.");
      }
    };
    void load();
    const timer = window.setInterval(load, 15000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);
  return { lives, error };
}
