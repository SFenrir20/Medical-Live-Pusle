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
  onChange: (status: "available" | "paused" | "offline") => void;
}) {
  const state = failed || !presence ? "offline" : presence.state;
  const light = LIGHT[state];
  const label =
    failed || !presence
      ? "Sin conexión"
      : state === "offline"
        ? "Desconectado"
        : state === "paused"
          ? presence.status === "paused"
            ? "En pausa"
            : "Inactivo"
          : presence.auto_assignment
            ? "Recibiendo contactos"
            : "Conectado";
  const paused = state !== "online";
  return (
    <div className="flex items-center gap-2">
      <span
        className="flex items-center gap-2 rounded-full border border-line bg-white px-3 py-1.5"
        title={
          failed
            ? "No se pudo avisar que estás conectado. Revisa tu internet."
            : "Verde: actividad reciente. Amarillo: inactividad o pestaña oculta. Tras 15 minutos en amarillo debes reconectarte."
        }
      >
        <span className={`size-2.5 rounded-full ring-4 ${light.dot} ${light.ring}`} />
        <span className={`hidden text-xs font-bold sm:inline ${light.text}`}>{label}</span>
      </span>
      {presence && !failed && state !== "offline" && (
        <span
          className="hidden text-[11px] text-muted lg:inline"
          title="Tiempo conectado en esta sesión de trabajo"
        >
          Sesión {Math.floor((presence.session_seconds ?? 0) / 3600)} h{" "}
          {Math.floor((presence.session_seconds ?? 0) / 60) % 60} min
        </span>
      )}
      {presence && !failed && (
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
          <span className="hidden sm:inline">
            {state === "offline" ? "Conectarme" : paused ? "Reanudar" : "Pausar"}
          </span>
        </button>
      )}
      {presence && !failed && state !== "offline" && (
        <button
          type="button"
          onClick={() => onChange("offline")}
          className="text-xs text-muted hover:text-red-600"
        >
          Desconectarme
        </button>
      )}
    </div>
  );
}
