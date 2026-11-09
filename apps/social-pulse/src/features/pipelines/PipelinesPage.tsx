import { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  Filter,
  Funnel as FunnelIcon,
  MessageCircle,
  Plus,
  Search,
  Settings,
  UserPlus,
  X,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { AppNav } from "@/features/shell/AppNav";
import { chatApi, type ConversationItem, type LiveLead, problem } from "@/features/chats/api";
import { ConversationDialog } from "@/features/chats/ConversationDialog";
import { LivePanel } from "@/features/chats/LivePanel";
import {
  type Board,
  type Card,
  type Column,
  type Funnel,
  funnelApi,
  money,
  type Template,
} from "./api";
import { AddChatsDialog, NewFunnelDialog } from "./Dialogs";
import { FunnelBuilder } from "./FunnelBuilder";
import { LeadCard } from "./LeadCard";

const STORE = "livepulse.funnel";
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

function remembered(): number | null {
  try {
    const value = Number(window.localStorage.getItem(STORE));
    return Number.isFinite(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}
function remember(id: number) {
  try {
    window.localStorage.setItem(STORE, String(id));
  } catch {
    /* only a convenience */
  }
}

/** Takes a fresh board but keeps unchanged cards (same objects, no redraw) and, in a column where
 *  "Ver más" loaded extra pages, keeps those cards: only counts and values are refreshed. */
function merge(old: Board | null, fresh: Board, expanded: Set<number>): Board {
  if (!old || old.pipeline.id !== fresh.pipeline.id) return fresh;
  const stages = fresh.stages.map((column) => {
    const before = old.stages.find((c) => c.id === column.id);
    if (!before) return column;
    if (expanded.has(column.id))
      return { ...column, cards: before.cards, has_more: before.has_more };
    const known = new Map(before.cards.map((c) => [c.id, c]));
    const cards = column.cards.map((c) =>
      known.get(c.id) && same(known.get(c.id), c) ? known.get(c.id)! : c,
    );
    const identical =
      cards.length === before.cards.length && cards.every((c, i) => c === before.cards[i]);
    return { ...column, cards: identical ? before.cards : cards };
  });
  const next = { ...fresh, stages };
  return same(old, next) ? old : next;
}

/** The card moved to the top of another column, counts and values adjusted (optimistic). */
function relocate(board: Board, card: Card, target: number): Board {
  const from = board.stages.find((c) => c.cards.some((x) => x.id === card.id));
  if (!from || from.id === target) return board;
  return {
    ...board,
    stages: board.stages.map((c) =>
      c.id === from.id
        ? {
            ...c,
            cards: c.cards.filter((x) => x.id !== card.id),
            count: c.count - 1,
            value_cents: c.value_cents - card.value_cents,
          }
        : c.id === target
          ? {
              ...c,
              cards: [card, ...c.cards],
              count: c.count + 1,
              value_cents: c.value_cents + card.value_cents,
            }
          : c,
    ),
  };
}

function withValue(board: Board, card: Card, cents: number): Board {
  const delta = cents - card.value_cents;
  return {
    ...board,
    value_cents: board.value_cents + delta,
    stages: board.stages.map((c) =>
      c.cards.some((x) => x.id === card.id)
        ? {
            ...c,
            value_cents: c.value_cents + delta,
            cards: c.cards.map((x) => (x.id === card.id ? { ...x, value_cents: cents } : x)),
          }
        : c,
    ),
  };
}

/** Funnels as a Kanban board: a column per stage, a card per conversation. */
export function PipelinesPage() {
  const { user } = useAuth();
  const permissions = user?.permissions ?? [];
  const mayRead = permissions.includes("wa:read");
  const mayManage = permissions.includes("crm:manage");

  const [funnels, setFunnels] = useState<Funnel[]>([]);
  const [current, setCurrent] = useState<number | null>(null);
  const [board, setBoard] = useState<Board | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [mine, setMine] = useState(false);
  const [error, setError] = useState("");
  const [picker, setPicker] = useState(false);
  const [dialog, setDialog] = useState<"new" | "builder" | "add" | null>(null);
  const [dragged, setDragged] = useState<Card | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const [loadingMore, setLoadingMore] = useState<number | null>(null);
  const [chat, setChat] = useState<{ id: number; item: ConversationItem | null } | null>(null);
  const [leads, setLeads] = useState<LiveLead[]>([]);
  const [liveOpen, setLiveOpen] = useState(false);
  const [opening, setOpening] = useState(false);
  const expanded = useRef(new Set<number>());
  const currentRef = useRef(current);
  currentRef.current = current;

  useEffect(() => {
    const timer = setTimeout(() => setQ(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const loadFunnels = useCallback(async (prefer?: number) => {
    const items = await funnelApi.list();
    setFunnels(items);
    setCurrent((old) => {
      const wanted = prefer ?? old ?? remembered();
      // Without a choice yet, someone who works at a branch starts in that branch's funnel.
      return (
        items.find((f) => f.id === wanted)?.id ??
        items.find((f) => f.site_id)?.id ??
        items[0]?.id ??
        null
      );
    });
  }, []);
  useEffect(() => {
    if (!mayRead) return;
    void loadFunnels().catch((e) => setError(problem(e)));
    void funnelApi
      .templates()
      .then(setTemplates)
      .catch(() => undefined);
  }, [mayRead, loadFunnels]);

  const refresh = useCallback(async () => {
    const id = currentRef.current;
    if (!id) return;
    const fresh = await funnelApi.board(id, q, mine);
    if (currentRef.current === id) setBoard((old) => merge(old, fresh, expanded.current));
  }, [q, mine]);

  useEffect(() => {
    if (!mayRead || !current) return;
    expanded.current.clear();
    remember(current);
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let first = true;
    const poll = async () => {
      if (!document.hidden || first) {
        first = false;
        try {
          await refresh();
        } catch (e) {
          if (!stopped) setError(problem(e));
        }
      }
      if (!stopped) timer = setTimeout(poll, 8000);
    };
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [mayRead, current, refresh]);

  useEffect(() => {
    if (!mayRead) return;
    let stopped = false;
    const load = () =>
      void chatApi
        .liveLeads()
        .then((rows) => !stopped && setLeads(rows))
        .catch(() => undefined);
    load();
    const timer = window.setInterval(() => !document.hidden && load(), 15000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [mayRead]);

  const act = async (work: () => Promise<unknown>) => {
    setError("");
    try {
      await work();
    } catch (e) {
      setError(problem(e));
    }
    await refresh().catch(() => undefined);
  };

  const move = (card: Card, stageId: number) => {
    const id = current;
    if (!id) return;
    setBoard((b) => (b ? relocate(b, card, stageId) : b));
    void act(() => funnelApi.putCard(id, card.id, { stage_id: stageId }));
  };
  const setValue = (card: Card, cents: number) => {
    const id = current;
    if (!id) return;
    setBoard((b) => (b ? withValue(b, card, cents) : b));
    void act(() => funnelApi.putCard(id, card.id, { value_cents: cents }));
  };
  const remove = (card: Card) => {
    const id = current;
    if (id) void act(() => funnelApi.removeCard(id, card.id));
  };
  const open = (card: Card) => setChat({ id: card.id, item: card });
  // A phone from the TikTok LIVE panel opens its conversation in the same window.
  const openPhone = async (phone: string) => {
    setOpening(true);
    setError("");
    try {
      const { id } = await chatApi.openPhone(phone);
      setLiveOpen(false);
      setChat({ id, item: null });
    } catch (e) {
      setError(problem(e));
    } finally {
      setOpening(false);
    }
  };
  const more = async (column: Column) => {
    if (!current) return;
    setLoadingMore(column.id);
    try {
      const page = await funnelApi.moreCards(current, column.id, column.cards.length, q, mine);
      expanded.current.add(column.id);
      setBoard((b) =>
        b
          ? {
              ...b,
              stages: b.stages.map((c) => {
                if (c.id !== column.id) return c;
                const have = new Set(c.cards.map((x) => x.id));
                return {
                  ...c,
                  cards: [...c.cards, ...page.cards.filter((x) => !have.has(x.id))],
                  has_more: page.has_more,
                };
              }),
            }
          : b,
      );
    } catch (e) {
      setError(problem(e));
    } finally {
      setLoadingMore(null);
    }
  };

  const createFunnel = async (name: string, template: string): Promise<string | null> => {
    try {
      const made = await funnelApi.create(name, template);
      await loadFunnels(made.id);
      setDialog(null);
      return null;
    } catch (e) {
      return problem(e);
    }
  };

  if (!mayRead)
    return (
      <>
        <AppNav />
        <main className="p-8">
          Tu rol no tiene acceso a los embudos.{" "}
          <a className="text-primary" href="/">
            Volver
          </a>
        </main>
      </>
    );

  const funnel = board?.pipeline ?? funnels.find((f) => f.id === current) ?? null;
  const stages = board?.stages ?? [];
  const isDefault = !!funnel?.default;

  return (
    <div className="flex h-dvh flex-col bg-canvas text-ink">
      <AppNav />
      <div className="flex flex-wrap items-center gap-3 px-4 pb-2 pt-3 sm:px-6">
        <div className="relative">
          <button
            type="button"
            aria-expanded={picker}
            onClick={() => setPicker((v) => !v)}
            className="flex items-center gap-2 rounded-xl px-2 py-1 text-left hover:bg-white"
          >
            <span className="grid size-9 place-items-center rounded-xl bg-primary-soft text-primary">
              <FunnelIcon size={18} />
            </span>
            <span>
              <span className="block text-lg font-bold leading-tight">
                {funnel?.name ?? "Embudos"}
              </span>
              {board && (
                <span className="block text-xs text-muted">
                  {board.total} chats · {money(board.value_cents)}
                </span>
              )}
            </span>
            <ChevronDown size={16} className={picker ? "rotate-180" : ""} />
          </button>
          {picker && (
            <div className="absolute left-0 top-full z-30 mt-1 w-64 rounded-xl border border-line bg-white p-1.5 shadow-xl">
              {funnels.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => {
                    setPicker(false);
                    setBoard(null);
                    setCurrent(f.id);
                  }}
                  className={`block w-full rounded-lg px-3 py-2 text-left text-sm font-semibold hover:bg-slate-50 ${f.id === current ? "bg-slate-100" : ""}`}
                >
                  {f.name}
                  {f.default && (
                    <span className="ml-2 text-[11px] font-normal text-muted">
                      estado del contacto
                    </span>
                  )}
                </button>
              ))}
              {mayManage && (
                <button
                  type="button"
                  onClick={() => {
                    setPicker(false);
                    setDialog("new");
                  }}
                  className="mt-1 flex w-full items-center gap-2 rounded-lg border-t border-line px-3 py-2 text-left text-sm font-semibold text-primary hover:bg-primary-soft"
                >
                  <Plus size={15} /> Agregar embudo
                </button>
              )}
            </div>
          )}
        </div>
        {funnel && (
          <button
            type="button"
            onClick={() => setDialog("builder")}
            className="flex items-center gap-2 rounded-xl border border-line bg-white px-3 py-2 text-xs font-bold text-ink hover:bg-slate-50"
          >
            <Settings size={14} /> {mayManage && !isDefault ? "Configuración" : "Etapas y cifras"}
          </button>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <label className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              aria-label="Buscar en el embudo"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar chats"
              className="w-44 rounded-xl border border-line bg-white py-2 pl-8 pr-3 text-sm outline-none focus:border-primary"
            />
          </label>
          <button
            type="button"
            aria-pressed={mine}
            onClick={() => setMine((v) => !v)}
            className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-bold ${mine ? "border-primary bg-primary text-white" : "border-line bg-white"}`}
          >
            <Filter size={14} /> Solo míos
          </button>
          <button
            type="button"
            onClick={() => setLiveOpen(true)}
            className="rounded-xl border border-line bg-white px-3 py-2 text-xs font-bold text-primary min-[80rem]:hidden"
          >
            TikTok LIVE
          </button>
          {!isDefault && funnel && (
            <button
              type="button"
              onClick={() => setDialog("add")}
              className="flex items-center gap-2 rounded-xl bg-primary px-3 py-2 text-xs font-bold text-white"
            >
              <UserPlus size={14} /> Agregar chats
            </button>
          )}
        </div>
      </div>
      {error && (
        <p
          role="alert"
          className="mx-4 mb-2 flex items-start justify-between gap-3 rounded-xl bg-red-50 p-3 text-sm text-red-800 sm:mx-6"
        >
          {error}
          <button type="button" onClick={() => setError("")} aria-label="Cerrar aviso">
            <X size={14} />
          </button>
        </p>
      )}

      <div className="flex min-h-0 flex-1 gap-3 px-4 pb-4 sm:px-6">
        <main className="flex min-h-0 min-w-0 flex-1 gap-3 overflow-x-auto">
          {!board && !error && <p className="m-auto text-sm text-muted">Cargando embudo…</p>}
          {stages.map((column) => (
            <section
              key={column.id}
              aria-label={`Etapa ${column.name}`}
              onDragOver={(e) => {
                if (dragged) {
                  e.preventDefault();
                  setOver(column.id);
                }
              }}
              onDragLeave={() => setOver((v) => (v === column.id ? null : v))}
              onDrop={(e) => {
                e.preventDefault();
                setOver(null);
                if (dragged) move(dragged, column.id);
                setDragged(null);
              }}
              className={`flex h-full w-[300px] shrink-0 flex-col rounded-2xl border bg-slate-100/70 ${over === column.id ? "border-primary ring-2 ring-primary/30" : "border-line"}`}
            >
              <header
                className="rounded-t-2xl border-b-[3px] bg-white px-4 py-3"
                style={{ borderColor: column.color }}
              >
                <div className="flex items-center justify-between gap-2">
                  <h2
                    className="truncate text-sm font-bold"
                    title={column.description ?? undefined}
                  >
                    {column.name}
                  </h2>
                  <span className="flex items-center gap-1 text-xs font-semibold text-muted">
                    <MessageCircle size={13} /> {column.count}
                  </span>
                </div>
              </header>
              <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
                {column.cards.map((card) => (
                  <LeadCard
                    key={card.id}
                    card={card}
                    stageId={column.id}
                    stages={stages}
                    isDefault={isDefault}
                    onMove={move}
                    onValue={setValue}
                    onRemove={remove}
                    onOpen={open}
                    dragging={dragged?.id === card.id}
                    onDragStart={setDragged}
                    onDragEnd={() => {
                      setDragged(null);
                      setOver(null);
                    }}
                  />
                ))}
                {!column.cards.length && (
                  <p className="rounded-xl border border-dashed border-slate-300 p-4 text-center text-xs text-muted">
                    {q || mine ? "Nada coincide con el filtro." : "Sin chats. Arrastra uno aquí."}
                  </p>
                )}
                {column.has_more && (
                  <button
                    type="button"
                    disabled={loadingMore === column.id}
                    onClick={() => void more(column)}
                    className="w-full rounded-lg py-2 text-xs font-semibold text-primary hover:bg-white disabled:opacity-50"
                  >
                    {loadingMore === column.id
                      ? "Cargando…"
                      : `Ver más (${column.count - column.cards.length})`}
                  </button>
                )}
              </div>
              <footer className="rounded-b-2xl border-t border-line bg-white px-4 py-2 text-xs text-muted">
                Valor: <strong className="text-ink">{money(column.value_cents)}</strong>
              </footer>
            </section>
          ))}
        </main>
        <div className="hidden w-[270px] shrink-0 overflow-hidden rounded-2xl border border-line bg-white min-[80rem]:flex [&>aside]:w-full [&>aside]:border-l-0">
          <LivePanel leads={leads} onOpen={(phone) => void openPhone(phone)} opening={opening} />
        </div>
      </div>

      {chat && (
        <ConversationDialog
          key={chat.id}
          conversationId={chat.id}
          item={chat.item}
          onClose={() => setChat(null)}
          onChanged={() => void refresh().catch(() => undefined)}
        />
      )}
      {liveOpen && (
        <div className="fixed inset-0 z-40 flex flex-col bg-white min-[80rem]:hidden">
          <button
            type="button"
            onClick={() => setLiveOpen(false)}
            className="border-b border-line p-4 text-right text-primary"
          >
            Cerrar TikTok LIVE
          </button>
          <LivePanel leads={leads} onOpen={(phone) => void openPhone(phone)} opening={opening} />
        </div>
      )}
      {dialog === "new" && (
        <NewFunnelDialog
          templates={templates}
          onCreate={createFunnel}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "builder" && funnel && board && (
        <FunnelBuilder
          key={funnel.id}
          funnel={funnel}
          stages={stages}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            void loadFunnels(funnel.id);
            void refresh().catch(() => undefined);
          }}
          onArchived={() => {
            setDialog(null);
            setBoard(null);
            void loadFunnels(funnels.find((f) => f.default)?.id);
          }}
        />
      )}
      {dialog === "add" && funnel && (
        <AddChatsDialog
          funnelId={funnel.id}
          stages={stages}
          onClose={() => setDialog(null)}
          onChanged={() => void refresh().catch(() => undefined)}
        />
      )}
    </div>
  );
}
