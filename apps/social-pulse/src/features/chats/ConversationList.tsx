import { FormEvent, useState } from "react";
import { Search, Filter } from "lucide-react";
import type { ConversationItem, Counts, Scope } from "./api";
import { colorOf, initials, nice, shortTime, stageOf } from "./format";

const TABS: { key: Scope; label: string }[] = [
  { key: "all", label: "Todos" },
  { key: "mine", label: "Asignados a mí" },
  { key: "unread", label: "No leídos" },
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

export function ConversationList({
  items,
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
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [phone, setPhone] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = phone.replace(/[\s-]/g, "");
    onOpenPhone(/^\+/.test(value) ? value : `+51${value.replace(/^0+/, "")}`);
    setPhone("");
  };
  return (
    <aside className="flex min-h-0 flex-col border-r border-line bg-white">
      <div className="space-y-3 border-b border-line p-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-[9px] font-bold uppercase tracking-[0.16em] text-primary">
              Bandeja omnicanal
            </p>
            <h2 className="mt-1 text-sm font-bold">Conversaciones</h2>
          </div>
          <button
            type="button"
            aria-label="Filtrar conversaciones"
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen(!filtersOpen)}
            className="rounded-xl border border-line p-2 text-muted"
          >
            <Filter size={15} />
          </button>
        </div>
        <label className="relative block">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            aria-label="Buscar contactos y mensajes"
            className="w-full rounded-xl border border-line bg-canvas py-2 pl-9 pr-3 text-sm outline-none focus:border-primary"
            placeholder="Buscar contactos y mensajes"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
          />
        </label>
        <p className="text-[10px] text-muted">
          {counts.all} conversaciones · WhatsApp
          {scope !== "all" ? ` · ${TABS.find((t) => t.key === scope)?.label}` : ""}
        </p>
        {filtersOpen && (
          <div className="flex flex-wrap gap-1.5" role="tablist">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={scope === tab.key}
                onClick={() => onScope(tab.key)}
                className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-semibold ${
                  scope === tab.key
                    ? "bg-primary text-white"
                    : "bg-slate-100 text-muted hover:bg-slate-200"
                }`}
              >
                {tab.label}
                {counts[tab.key] > 0 && tab.key !== "all" ? ` ${counts[tab.key]}` : ""}
              </button>
            ))}
          </div>
        )}
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto">
        {items.map((c) => {
          const stage = stageOf(c.stage);
          const unread = c.unread > 0;
          return (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => onSelect(c.id)}
                className={`flex w-full items-center gap-2.5 border-b border-slate-100 border-l-[3px] px-3 py-3.5 text-left ${
                  selected === c.id
                    ? "bg-primary-soft border-l-primary"
                    : unread
                      ? "border-l-transparent hover:bg-slate-50"
                      : "border-l-transparent hover:bg-slate-50"
                }`}
              >
                <Avatar name={c.name} phone={c.phone} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className={`truncate text-xs ${unread ? "font-bold" : "font-semibold"}`}>
                      {c.name || nice(c.phone)}
                    </span>
                    <span className="shrink-0 text-[11px] text-muted">
                      {shortTime(c.last_message_at)}
                    </span>
                  </span>
                  <span className="mt-0.5 flex items-center justify-between gap-2">
                    <span className={`truncate text-[11px] ${unread ? "text-ink" : "text-muted"}`}>
                      {c.last
                        ? `${c.last.direction === "out" ? "Tú: " : ""}${c.last.body}`
                        : "Sin mensajes aún"}
                    </span>
                    {unread && (
                      <span className="grid min-w-5 shrink-0 place-items-center rounded-full bg-primary px-1.5 text-[11px] font-bold text-white">
                        {c.unread}
                      </span>
                    )}
                  </span>
                  <span className="mt-1 block text-[10px] font-semibold text-primary">
                    {nice(c.phone)}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
        {!items.length && (
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

      <form onSubmit={submit} className="flex gap-2 border-t border-line p-3">
        <input
          aria-label="Teléfono del contacto"
          className="min-w-0 flex-1 rounded-xl border border-line px-3 py-2 text-sm outline-none focus:border-primary"
          placeholder="Abrir un número (+51…)"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          inputMode="tel"
          required
        />
        <button
          disabled={opening}
          className="rounded-xl bg-primary px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
        >
          Abrir
        </button>
      </form>
    </aside>
  );
}
