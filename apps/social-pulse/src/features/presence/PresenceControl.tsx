import { Pause, Play } from "lucide-react";
import { PresenceState } from "./api";

const LIGHT = {
  online: { dot: "bg-emerald-500", ring: "ring-emerald-200", text: "text-emerald-700" },
  paused: { dot: "bg-amber-500", ring: "ring-amber-200", text: "text-amber-700" },
  offline: { dot: "bg-red-500", ring: "ring-red-200", text: "text-red-700" },
} as const;

/** The agent's light and her pause button. Green = connected and receiving contacts. */
export function PresenceControl({
  presence,
  failed,
  onChange,
}: {
  presence: PresenceState | null;
  failed: boolean;
  onChange: (status: "available" | "paused") => void;
}) {
  const state = failed || !presence ? "offline" : presence.state;
  const light = LIGHT[state];
  const label =
    failed || !presence
      ? "Sin conexión"
      : state === "paused"
        ? "En pausa"
        : presence.auto_assignment
          ? "Recibiendo contactos"
          : "Conectado";
  const paused = presence?.status === "paused";
  return (
    <div className="flex items-center gap-2">
      <span
        className="flex items-center gap-2 rounded-full border border-line bg-white px-3 py-1.5"
        title={
          failed
            ? "No se pudo avisar que estás conectado. Revisa tu internet."
            : "Mientras tengas esta pantalla abierta, el sistema te considera conectado."
        }
      >
        <span className={`size-2.5 rounded-full ring-4 ${light.dot} ${light.ring}`} />
        <span className={`hidden text-xs font-bold sm:inline ${light.text}`}>{label}</span>
      </span>
      {presence && !failed && presence.auto_assignment && (
        <button
          type="button"
          onClick={() => onChange(paused ? "available" : "paused")}
          className="flex items-center gap-1.5 rounded-full border border-line bg-white px-3 py-1.5 text-xs font-semibold text-muted hover:text-primary"
          title={
            paused
              ? "Volver a recibir contactos"
              : "Dejar de recibir contactos (tus pendientes se reparten a los demás)"
          }
        >
          {paused ? <Play size={13} /> : <Pause size={13} />}
          <span className="hidden sm:inline">{paused ? "Reanudar" : "Pausar"}</span>
        </button>
      )}
    </div>
  );
}
