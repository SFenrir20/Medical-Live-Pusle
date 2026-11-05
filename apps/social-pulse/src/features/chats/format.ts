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

/** 0:23 — length of an audio or video. */
export function clip(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "";
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function bytes(size: number | null | undefined): string {
  if (!size) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

/** "hace 5 min" — how long ago, for the people waiting for an answer. */
export function ago(iso: string | null | undefined): string {
  if (!iso) return "";
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "ahora";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h`;
  return `${Math.floor(hours / 24)} d`;
}

export const WAIT_LONG_MINUTES = 60;
export const waitedMinutes = (iso: string | null | undefined) =>
  iso ? Math.floor((Date.now() - new Date(iso).getTime()) / 60000) : 0;

const PLACEHOLDER =
  /^\[(Imagen|Video|Audio|Documento|Sticker): consultar en el teléfono\]\n?([\s\S]*)$/;
/** Messages saved before attachments were supported read "[Audio: consultar en el teléfono]". */
export function placeholderOf(body: string): { label: string; caption: string } | null {
  const found = PLACEHOLDER.exec(body);
  return found ? { label: found[1], caption: found[2] } : null;
}

export const KIND_LABEL = {
  image: "Foto",
  voice: "Mensaje de voz",
  audio: "Audio",
  video: "Video",
  document: "Documento",
  sticker: "Sticker",
} as const;

/** What the conversation list shows for the last message: the kind of attachment and its text. */
export function previewOf(last: {
  body: string;
  kind?: keyof typeof KIND_LABEL | null;
  seconds?: number | null;
  name?: string | null;
}): { kind: keyof typeof KIND_LABEL | null; text: string } {
  const holder = placeholderOf(last.body);
  const kindOfHolder = holder
    ? (
        {
          Imagen: "image",
          Video: "video",
          Audio: "voice",
          Documento: "document",
          Sticker: "sticker",
        } as const
      )[holder.label as "Imagen" | "Video" | "Audio" | "Documento" | "Sticker"]
    : null;
  const kind = last.kind ?? kindOfHolder;
  const caption = (holder ? holder.caption : last.body === "[Imagen]" ? "" : last.body).trim();
  if (!kind) return { kind: null, text: caption };
  const base =
    kind === "voice" || kind === "audio"
      ? [KIND_LABEL[kind], clip(last.seconds)].filter(Boolean).join(" ")
      : kind === "document"
        ? last.name || KIND_LABEL.document
        : KIND_LABEL[kind];
  return { kind, text: kind === "sticker" || !caption ? base : `${base} · ${caption}` };
}
