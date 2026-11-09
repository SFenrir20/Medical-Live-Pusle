import { FormEvent, memo, useState } from "react";
import {
  Camera,
  Check,
  CheckCheck,
  Clock,
  File,
  Mic,
  Music,
  Search,
  Smile,
  Video,
} from "lucide-react";
import type { ConversationItem, Counts, Scope } from "./api";
import {
  ago,
  initials,
  nice,
  previewOf,
  shortTime,
  stageOf,
  WAIT_LONG_MINUTES,
  waitedMinutes,
} from "./format";

export const TABS: { key: Scope; label: string }[] = [
  { key: "all", label: "Todos" },
  { key: "mine", label: "Míos" },
  { key: "unread", label: "No leídos" },
  { key: "waiting", label: "Sin responder" },
  { key: "unassigned", label: "Sin asignar" },
  { key: "archived", label: "Archivados" },
];

export function Avatar({
  name,
  phone,
  size = "size-11",
  badge = true,
}: {
  name: string | null;
  phone: string;
  size?: string;
  badge?: boolean;
}) {
  return (
    <span
      className={`relative grid ${size} shrink-0 place-items-center rounded-full text-sm font-bold text-primary bg-primary-soft`}
    >
      {initials(name, phone)}
      {badge && (
        <span className="absolute -bottom-0.5 -right-0.5 grid size-4 place-items-center rounded-full border-2 border-white bg-[#25d366]">
          <svg viewBox="0 0 24 24" className="size-2.5 fill-white" aria-hidden>
            <path d="M12 2a10 10 0 0 0-8.6 15L2 22l5.2-1.4A10 10 0 1 0 12 2z" />
          </svg>
        </span>
      )}
    </span>
  );
}

const KIND_ICON = {
  image: Camera,
  voice: Mic,
  audio: Music,
  video: Video,
  document: File,
  sticker: Smile,
} as const;

export function Preview({ c }: { c: ConversationItem }) {
  if (!c.last) return <span className="truncate">Sin mensajes aún</span>;
  const { kind, text } = previewOf(c.last);
  const Icon = kind ? KIND_ICON[kind] : null;
  const out = c.last.direction === "out";
  const status = c.last.status;
  return (
    <span className="flex min-w-0 items-center gap-1">
      {out &&
        (status === "read" ? (
          <CheckCheck size={14} className="shrink-0 text-[#53bdeb]" aria-label="Leído" />
        ) : status === "delivered" ? (
          <CheckCheck size={14} className="shrink-0 text-slate-400" aria-label="Entregado" />
        ) : status === "sent" ? (
          <Check size={14} className="shrink-0 text-slate-400" aria-label="Enviado" />
        ) : (
          <Clock size={12} className="shrink-0 text-slate-400" aria-label="En cola" />
        ))}
      {Icon && <Icon size={14} className="shrink-0" aria-hidden />}
      <span className="truncate">{text || (kind ? "" : "Mensaje")}</span>
    </span>
  );
}

/** One row. Memoised: the list refreshes every few seconds and unchanged rows are not redrawn. */
const Row = memo(function Row({
  c,
  active,
  onSelect,
}: {
  c: ConversationItem;
  active: boolean;
  onSelect: (id: number) => void;
}) {
  const unread = c.unread > 0;
  const stage = stageOf(c.stage);
  const minutes = c.waiting ? waitedMinutes(c.last?.at) : 0;
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(c.id)}
        className={`flex w-full items-start gap-3 border-b border-slate-100 border-l-[3px] px-3 py-3 text-left ${
          active ? "border-l-primary bg-primary-soft" : "border-l-transparent hover:bg-slate-50"
        }`}
      >
        <Avatar name={c.name} phone={c.phone} size="size-12" />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-2">
            <span
              className={`truncate text-[14.5px] text-[#111b21] ${unread ? "font-bold" : "font-medium"}`}
            >
              {c.name || nice(c.phone)}
            </span>
            <span
              className={`shrink-0 text-xs ${unread ? "font-semibold text-[#00a884]" : "text-muted"}`}
            >
              {shortTime(c.last_message_at)}
            </span>
          </span>
          <span className="mt-0.5 flex items-center justify-between gap-2">
            <span
              className={`min-w-0 flex-1 text-[13px] ${unread ? "font-medium text-[#111b21]" : "text-[#667781]"}`}
            >
              <Preview c={c} />
            </span>
            {unread && (
              <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-[#25d366] px-1.5 text-[11px] font-bold text-white">
                {c.unread > 99 ? "99+" : c.unread}
              </span>
            )}
          </span>
          <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${stage.chip}`}>
              {stage.label}
            </span>
            {c.waiting && !c.archived && (
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                  minutes >= WAIT_LONG_MINUTES
                    ? "bg-red-50 text-red-700"
                    : "bg-amber-50 text-amber-700"
                }`}
              >
                Sin responder · {ago(c.last?.at)}
              </span>
            )}
            <span className="truncate text-[10.5px] text-muted">
              {c.is_mine ? "Tuyo" : c.advisor_name ? c.advisor_name : "Sin asignar"}
            </span>
          </span>
        </span>
      </button>
    </li>
  );
});

export function ConversationList({
  items,
  loaded,
  counts,
  scope,
  onScope,
  search,
  onSearch,
  selected,
  onSelect,
  hasMore,
  offset,
  onOffset,
  onOpenPhone,
  opening,
}: {
  items: ConversationItem[];
  loaded: boolean;
  counts: Counts;
  scope: Scope;
  onScope: (scope: Scope) => void;
  search: string;
  onSearch: (value: string) => void;
  selected: number | null;
  onSelect: (id: number) => void;
  hasMore: boolean;
  offset: number;
  onOffset: (value: number) => void;
  onOpenPhone: (phone: string) => void;
  opening: boolean;
}) {
  const [phone, setPhone] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = phone.replace(/[\s-]/g, "");
    onOpenPhone(/^\+/.test(value) ? value : `+51${value.replace(/^0+/, "")}`);
    setPhone("");
  };
  return (
    <aside className="flex min-h-0 flex-col border-r border-line bg-white">
      <div className="space-y-2.5 border-b border-line px-3 pb-2 pt-3">
        <div className="flex items-baseline justify-between gap-2 px-1">
          <h2 className="text-base font-bold">Conversaciones</h2>
          <span className="text-[11px] text-muted">WhatsApp · {counts.all}</span>
        </div>
        <label className="relative block">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            aria-label="Buscar contactos y mensajes"
            className="w-full rounded-lg bg-[#f0f2f5] py-2 pl-9 pr-3 text-sm outline-none ring-primary focus:bg-white focus:ring-1"
            placeholder="Buscar o empezar un chat nuevo"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
          />
        </label>
        <div role="tablist" className="flex flex-wrap gap-1.5 pb-1">
          {TABS.map((tab) => {
            const count = counts[tab.key];
            const active = scope === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => onScope(tab.key)}
                className={`flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ${
                  active
                    ? "bg-primary text-white"
                    : "bg-[#f0f2f5] text-[#54656f] hover:bg-slate-200"
                }`}
              >
                {tab.label}
                {tab.key !== "all" && count > 0 && (
                  <span
                    className={`rounded-full px-1.5 text-[10.5px] ${
                      active
                        ? "bg-white/25"
                        : tab.key === "waiting"
                          ? "bg-red-100 text-red-700"
                          : "bg-slate-200"
                    }`}
                  >
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto">
        {items.map((c) => (
          <Row key={c.id} c={c} active={selected === c.id} onSelect={onSelect} />
        ))}
        {!loaded &&
          Array.from({ length: 7 }, (_, i) => (
            <li
              key={i}
              className="flex animate-pulse items-center gap-3 border-b border-slate-100 px-3 py-4"
            >
              <span className="size-12 rounded-full bg-slate-100" />
              <span className="flex-1 space-y-2">
                <span className="block h-3 w-1/2 rounded bg-slate-100" />
                <span className="block h-3 w-4/5 rounded bg-slate-100" />
              </span>
            </li>
          ))}
        {loaded && !items.length && (
          <li className="p-8 text-center text-sm text-muted">
            {search ? "Nada coincide con tu búsqueda." : "No hay conversaciones en esta vista."}
          </li>
        )}
        {(offset > 0 || hasMore) && (
          <li className="flex justify-between px-4 py-3 text-sm font-semibold text-primary">
            <button
              type="button"
              disabled={!offset}
              onClick={() => onOffset(Math.max(0, offset - 50))}
              className="disabled:opacity-30"
            >
              Anterior
            </button>
            <button
              type="button"
              disabled={!hasMore}
              onClick={() => onOffset(offset + 50)}
              className="disabled:opacity-30"
            >
              Siguiente
            </button>
          </li>
        )}
      </ul>

      <form onSubmit={submit} className="flex gap-2 border-t border-line bg-[#f0f2f5] p-2.5">
        <input
          aria-label="Teléfono del contacto"
          className="min-w-0 flex-1 rounded-lg bg-white px-3 py-2 text-sm outline-none ring-primary focus:ring-1"
          placeholder="Abrir un número (+51…)"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          inputMode="tel"
          required
        />
        <button
          disabled={opening}
          className="rounded-lg bg-primary px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
        >
          Abrir
        </button>
      </form>
    </aside>
  );
}
