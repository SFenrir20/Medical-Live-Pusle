import { Inbox, MessageCircleWarning, UserCheck, UserX } from "lucide-react";
import type { ConversationItem, Counts, Scope } from "./api";
import { Avatar } from "./ConversationList";
import { ago, nice, previewOf, WAIT_LONG_MINUTES, waitedMinutes } from "./format";

const CARDS: { scope: Scope; label: string; hint: string; icon: typeof Inbox; tone: string }[] = [
  {
    scope: "waiting",
    label: "Sin responder",
    hint: "Te escribieron y nadie contestó",
    icon: MessageCircleWarning,
    tone: "text-red-600 bg-red-50",
  },
  {
    scope: "unread",
    label: "No leídos",
    hint: "Mensajes nuevos por revisar",
    icon: Inbox,
    tone: "text-primary bg-primary-soft",
  },
  {
    scope: "unassigned",
    label: "Sin asignar",
    hint: "Libres para tomar",
    icon: UserX,
    tone: "text-amber-700 bg-amber-50",
  },
  {
    scope: "mine",
    label: "Míos",
    hint: "Los que atiendes tú",
    icon: UserCheck,
    tone: "text-emerald-700 bg-emerald-50",
  },
];

/** What the middle of the inbox shows while no conversation is open: where the work is. */
export function ChatsHome({
  counts,
  waiting,
  loaded,
  onScope,
  onSelect,
}: {
  counts: Counts;
  waiting: ConversationItem[];
  loaded: boolean;
  onScope: (scope: Scope) => void;
  onSelect: (id: number) => void;
}) {
  return (
    <section className="flex min-h-0 min-w-0 flex-col overflow-y-auto bg-[#f0f2f5] p-6 sm:p-8">
      <div className="mx-auto w-full max-w-2xl space-y-6">
        <div>
          <h2 className="text-xl font-bold">Bandeja omnicanal</h2>
          <p className="mt-1 text-sm text-muted">
            Elige una conversación de la lista, o empieza por lo que está esperando respuesta.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {CARDS.map(({ scope, label, hint, icon: Icon, tone }) => (
            <button
              key={scope}
              type="button"
              onClick={() => onScope(scope)}
              className="rounded-xl border border-line bg-white p-4 text-left shadow-sm transition hover:border-primary/40 hover:shadow"
            >
              <span className={`grid size-9 place-items-center rounded-lg ${tone}`}>
                <Icon size={18} />
              </span>
              <span className="mt-3 block text-2xl font-bold tabular-nums">
                {loaded ? counts[scope] : "–"}
              </span>
              <span className="block text-sm font-semibold">{label}</span>
              <span className="block text-xs text-muted">{hint}</span>
            </button>
          ))}
        </div>

        <div className="rounded-xl border border-line bg-white shadow-sm">
          <h3 className="border-b border-line px-4 py-3 text-sm font-bold">
            Esperando respuesta{" "}
            {counts.waiting > 0 && <span className="text-muted">· {counts.waiting}</span>}
          </h3>
          <ul>
            {waiting.map((c) => {
              const late = waitedMinutes(c.last?.at) >= WAIT_LONG_MINUTES;
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(c.id)}
                    className="flex w-full items-center gap-3 border-b border-slate-100 px-4 py-3 text-left last:border-0 hover:bg-slate-50"
                  >
                    <Avatar name={c.name} phone={c.phone} size="size-10" badge={false} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold">
                        {c.name || nice(c.phone)}
                      </span>
                      <span className="block truncate text-xs text-muted">
                        {c.last ? previewOf(c.last).text : ""}
                      </span>
                    </span>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${late ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700"}`}
                    >
                      {ago(c.last?.at)}
                    </span>
                  </button>
                </li>
              );
            })}
            {loaded && !waiting.length && (
              <li className="px-4 py-8 text-center text-sm text-muted">
                Todo al día: no hay conversaciones esperando respuesta.
              </li>
            )}
            {!loaded && <li className="px-4 py-8 text-center text-sm text-muted">Cargando…</li>}
          </ul>
        </div>
      </div>
    </section>
  );
}
