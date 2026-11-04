import type { Stage } from "./api";

export const STAGES: { value: Stage; label: string; dot: string; chip: string }[] = [
  { value: "new", label: "Nuevo", dot: "bg-sky-500", chip: "bg-sky-50 text-sky-700" },
  {
    value: "contacted",
    label: "Contactado",
    dot: "bg-amber-500",
    chip: "bg-amber-50 text-amber-700",
  },
  {
    value: "qualified",
    label: "Cita agendada",
    dot: "bg-emerald-500",
    chip: "bg-emerald-50 text-emerald-700",
  },
  {
    value: "discarded",
    label: "Descartado",
    dot: "bg-slate-400",
    chip: "bg-slate-100 text-slate-600",
  },
];
export const stageOf = (value: Stage) => STAGES.find((s) => s.value === value) ?? STAGES[0];

export const RESULTS: { value: string; label: string }[] = [
  { value: "agendo", label: "Agendó cita" },
  { value: "no_interesado", label: "No interesado" },
  { value: "sin_respuesta", label: "Sin respuesta" },
  { value: "numero_equivocado", label: "Número equivocado" },
];

export const TAG_SUGGESTIONS = ["Compra", "Del Live", "Crédito", "Urgente", "Seguimiento"];

export const STATUS_LABEL: Record<string, string> = {
  queued: "En cola",
  sending: "Confirmando envío",
  sent: "Enviado",
  delivered: "Entregado",
  read: "Leído",
  received: "Recibido",
  unknown: "Envío sin confirmar",
  blocked: "No enviado",
};

const TZ = "America/Lima";
const dayKey = (d: Date) => d.toLocaleDateString("es-PE", { timeZone: TZ });

export function shortTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (dayKey(d) === dayKey(new Date()))
    return d.toLocaleTimeString("es-PE", {
      timeZone: TZ,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  return d
    .toLocaleDateString("es-PE", { timeZone: TZ, day: "2-digit", month: "short" })
    .replace(".", "");
}

export const clock = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleTimeString("es-PE", {
        timeZone: TZ,
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "";

export const fullDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("es-PE", { timeZone: TZ }) : "—";

export function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today.getTime() - 86400000);
  if (dayKey(d) === dayKey(today)) return "HOY";
  if (dayKey(d) === dayKey(yesterday)) return "AYER";
  return d
    .toLocaleDateString("es-PE", { timeZone: TZ, day: "numeric", month: "long", year: "numeric" })
    .toUpperCase();
}

export const dayOf = (iso: string) => dayKey(new Date(iso));

export function initials(name: string | null, phone: string): string {
  const source = (name ?? "").trim();
  if (!source) return phone.slice(-2);
  const parts = source
    .replace(/[^\p{L}\p{N} ]/gu, "")
    .split(/\s+/)
    .filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || phone.slice(-2);
}

const PALETTE = [
  "bg-indigo-500",
  "bg-teal-500",
  "bg-rose-500",
  "bg-amber-500",
  "bg-violet-500",
  "bg-sky-500",
  "bg-emerald-600",
  "bg-pink-500",
];
export const colorOf = (phone: string) => PALETTE[Number(phone.slice(-2)) % PALETTE.length];

export const nice = (phone: string) => phone.replace(/^\+51(\d{3})(\d{3})(\d{3})$/, "+51 $1 $2 $3");

export function duration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = s % 60;
  return [h, m, rest].map((n) => String(n).padStart(2, "0")).join(":");
}
