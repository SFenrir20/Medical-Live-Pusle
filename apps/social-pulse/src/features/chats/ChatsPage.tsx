import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { AppNav } from "@/features/shell/AppNav";
import {
  chatApi,
  ConversationItem,
  Counts,
  CrmDetail,
  LiveLead,
  problem,
  QuickReply,
  Scope,
  Stage,
  TeamMember,
  Thread,
  WaStatus,
} from "./api";
import { ChatThread } from "./ChatThread";
import { ContactPanel } from "./ContactPanel";
import { ConversationList } from "./ConversationList";
import { fullDate } from "./format";
import { LivePanel } from "./LivePanel";

const STATES: Record<string, string> = {
  connected: "Conectado",
  connecting: "Conectando",
  qr: "Espera vinculación",
  disconnected: "Desconectado",
  unavailable: "Conector no disponible",
  relink_required: "Requiere nueva vinculación",
  wrong_number: "No se pudo identificar la cuenta o no coincide con la cuenta vinculada",
};
const NO_COUNTS: Counts = { all: 0, mine: 0, unread: 0, archived: 0 };

/** Omnichannel inbox: conversations, chat, contact file (CRM) and the TikTok LIVE side. */
export function ChatsPage() {
  const { user } = useAuth();
  const permissions = user?.permissions ?? [];
  const mayRead = permissions.includes("wa:read");
  const maySend = permissions.includes("wa:send");
  const mayManage = permissions.includes("wa:manage");
  const mayAssign = permissions.includes("contacts:assign_any");

  const [status, setStatus] = useState<WaStatus>({ state: "connecting" });
  const [items, setItems] = useState<ConversationItem[]>([]);
  const [counts, setCounts] = useState<Counts>(NO_COUNTS);
  const [hasMore, setHasMore] = useState(false);
  const [scope, setScope] = useState<Scope>("all");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<CrmDetail | null>(null);
  const [thread, setThread] = useState<Thread | null>(null);
  const [before, setBefore] = useState<number | null>(null);
  const [replies, setReplies] = useState<QuickReply[]>([]);
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [leads, setLeads] = useState<LiveLead[]>([]);
  const [busy, setBusy] = useState(false);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState("");
  const [ficha, setFicha] = useState(false);
  const [scheduleSignal, setScheduleSignal] = useState(0);
  const request = useRef<{ id: string; text: string; conversation: number } | null>(null);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const seenFor = useRef<number | null>(null);

  const choose = useCallback((id: number) => {
    setSelected(id);
    setDetail(null);
    setThread(null);
    setBefore(null);
    setFicha(false);
    setError("");
    request.current = null;
    seenFor.current = null;
  }, []);

  const refreshList = useCallback(async () => {
    const [list, connection] = await Promise.all([
      chatApi.conversations(scope, search, offset),
      chatApi.status(),
    ]);
    setItems(list.items);
    setCounts(list.counts);
    setHasMore(list.has_more);
    setStatus(connection);
  }, [scope, search, offset]);

  const openPhone = useCallback(
    async (phone: string) => {
      setOpening(true);
      setError("");
      try {
        const { id } = await chatApi.openPhone(phone);
        choose(id);
        void refreshList().catch(() => undefined);
      } catch (e) {
        setError(problem(e));
      } finally {
        setOpening(false);
      }
    },
    [choose, refreshList],
  );

  // A phone in the address (?phone=+51…) opens its conversation: the link from the LIVE contacts.
  const started = useRef(false);
  useEffect(() => {
    if (!mayRead || started.current) return;
    started.current = true;
    const phone = new URLSearchParams(window.location.search).get("phone");
    if (phone) void openPhone(phone.trim());
  }, [mayRead, openPhone]);

  useEffect(() => {
    if (!mayRead) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        await refreshList();
      } catch (e) {
        if (!stopped) {
          setError(problem(e));
          setStatus({ state: "unavailable" });
        }
      }
      if (!stopped) timer = setTimeout(poll, 4000);
    };
    timer = setTimeout(poll, 100);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [mayRead, refreshList]);

  useEffect(() => {
    if (!mayRead || !selected) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const [crm, messages] = await Promise.all([
          chatApi.detail(selected),
          chatApi.thread(selected, before),
        ]);
        if (!stopped) {
          setDetail(crm);
          setThread(messages);
        }
      } catch (e) {
        if (!stopped) {
          setDetail(null);
          setThread(null);
          setError(problem(e));
        }
      }
      if (!stopped) timer = setTimeout(poll, 3000);
    };
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [mayRead, selected, before]);

  // Opening one of your own unread conversations marks it reviewed here (no WhatsApp read receipt).
  useEffect(() => {
    if (
      detail &&
      detail.is_mine &&
      detail.unread > 0 &&
      maySend &&
      seenFor.current !== detail.id + detail.unread
    ) {
      seenFor.current = detail.id + detail.unread;
      void chatApi.seen(detail.id).catch(() => undefined);
    }
  }, [detail, maySend]);

  useEffect(() => {
    if (!mayRead) return;
    void chatApi
      .quickReplies()
      .then(setReplies)
      .catch(() => undefined);
    if (mayAssign)
      void chatApi
        .team()
        .then(setTeam)
        .catch(() => undefined);
  }, [mayRead, mayAssign]);

  useEffect(() => {
    if (!mayRead) return;
    let stopped = false;
    const load = () =>
      void chatApi
        .liveLeads()
        .then((l) => !stopped && setLeads(l))
        .catch(() => undefined);
    load();
    const timer = window.setInterval(load, 15000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [mayRead]);

  const act = async (work: () => Promise<CrmDetail | void>): Promise<boolean> => {
    setBusy(true);
    setError("");
    try {
      const result = await work();
      if (result) setDetail(result);
      void refreshList().catch(() => undefined);
      return true;
    } catch (e) {
      setError(problem(e));
      return false;
    } finally {
      setBusy(false);
    }
  };
  const id = selected;

  const send = async (text: string): Promise<boolean> => {
    if (!id) return false;
    if (!request.current || request.current.text !== text || request.current.conversation !== id)
      request.current = { id: crypto.randomUUID(), text, conversation: id };
    const requestId = request.current.id;
    setBusy(true);
    setError("");
    try {
      const message = await chatApi.send(id, requestId, text);
      if (selectedRef.current === id) {
        setThread((old) =>
          old
            ? { ...old, messages: [...old.messages.filter((m) => m.id !== message.id), message] }
            : old,
        );
        setBefore(null);
        request.current = null;
      }
      void refreshList().catch(() => undefined);
      return true;
    } catch (e) {
      setError(problem(e));
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (!mayRead)
    return (
      <>
        <AppNav />
        <main className="p-8">
          Tu rol no tiene acceso a las conversaciones.{" "}
          <a className="text-primary" href="/">
            Volver
          </a>
        </main>
      </>
    );

  const panel = (
    <ContactPanel
      detail={detail}
      thread={thread}
      canSend={maySend}
      mayAssign={mayAssign}
      team={team}
      busy={busy}
      onStage={(stage: Stage) => id && void act(() => chatApi.patch(id, { stage }))}
      onTags={(tags) => id && void act(() => chatApi.patch(id, { tags }))}
      onAssign={(advisor) => id && void act(() => chatApi.assign(id, advisor))}
      onClaim={() =>
        id &&
        void act(async () => {
          await chatApi.claim(id);
          return chatApi.detail(id);
        })
      }
      onAddNote={(text) => (id ? act(() => chatApi.addNote(id, text)) : Promise.resolve(false))}
      onDeleteNote={(note) => void act(() => chatApi.deleteNote(note))}
      onCancelScheduled={(item) => void act(() => chatApi.cancelScheduled(item))}
      onConsent={(state, note) => id && void act(() => chatApi.setConsent(id, state, note))}
      onSchedule={() => {
        setFicha(false);
        setScheduleSignal((n) => n + 1);
      }}
    />
  );

  return (
    <div className="flex h-screen flex-col bg-canvas text-ink">
      <AppNav />
      <div className="space-y-2 px-4 pt-3 sm:px-6">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span
            className={`rounded-full px-3 py-1 text-xs font-bold ${status.state === "connected" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}
          >
            WhatsApp · {STATES[status.state] || status.state} {status.phone}
          </span>
          {mayManage && status.state !== "connected" && (
            <button
              type="button"
              className="rounded-xl bg-primary px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  setStatus(await chatApi.connect());
                })
              }
            >
              Vincular / reconectar
            </button>
          )}
          <span className="text-xs text-muted">
            Horas de Lima. No es una integración oficial de Meta: una actualización de WhatsApp
            puede interrumpirla.
          </span>
        </div>
        {error && (
          <p
            role="alert"
            className="flex items-start justify-between gap-3 rounded-xl bg-red-50 p-3 text-sm text-red-800"
          >
            {error}
            <button type="button" onClick={() => setError("")} aria-label="Cerrar aviso">
              <X size={14} />
            </button>
          </p>
        )}
        {status.detail && <p className="text-xs text-muted">{status.detail}</p>}
        {status.state === "connected" && status.sync_ok === false && (
          <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
            WhatsApp está vinculado, pero la sincronización no está al día. Última sincronización:{" "}
            {fullDate(status.sync_at || null)}. Contacta al administrador.
          </p>
        )}
        {!!status.unresolved && (
          <p className="text-xs text-amber-800">
            Hay mensajes pendientes de identificar por teléfono. El conector reintentará al recibir
            la correspondencia de WhatsApp.
          </p>
        )}
        {!!status.rejected && (
          <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
            Hay {status.rejected} mensajes o confirmaciones guardados pendientes de revisión por un
            error de datos. Contacta al administrador.
          </p>
        )}
        {mayManage && status.qr && (
          <section className="flex flex-wrap items-center gap-5 rounded-2xl border border-line bg-white p-5">
            <img src={status.qr} width={200} height={200} alt="QR de vinculación de WhatsApp" />
            <div>
              <h2 className="font-bold">
                {status.phone
                  ? `Vincula el número ${status.phone}`
                  : "Vincula tu cuenta de WhatsApp"}
              </h2>
              <p className="text-sm">
                En tu teléfono: WhatsApp → Dispositivos vinculados → Vincular dispositivo.
              </p>
              <p className="mt-2 text-xs text-muted">
                El QR se renueva. Solo supervisores y administradores pueden verlo.
              </p>
            </div>
          </section>
        )}
      </div>

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-0 p-3 sm:p-4 lg:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[320px_minmax(0,1fr)_310px] 2xl:grid-cols-[320px_minmax(0,1fr)_310px_280px]">
        <div
          className={`min-h-0 overflow-hidden rounded-l-2xl border border-line lg:flex ${selected ? "hidden" : "flex"} [&>aside]:w-full`}
        >
          <ConversationList
            items={items}
            counts={counts}
            scope={scope}
            onScope={(s) => {
              setScope(s);
              setOffset(0);
            }}
            search={search}
            onSearch={(v) => {
              setSearch(v);
              setOffset(0);
            }}
            selected={selected}
            onSelect={choose}
            hasMore={hasMore}
            offset={offset}
            onOffset={setOffset}
            onOpenPhone={(phone) => void openPhone(phone)}
            opening={opening}
          />
        </div>
        <div
          className={`min-h-0 overflow-hidden border border-line lg:flex ${selected ? "flex" : "hidden"} [&>section]:w-full`}
        >
          <ChatThread
            detail={detail}
            thread={thread}
            status={status}
            canSend={maySend}
            quickReplies={replies}
            busy={busy}
            before={before}
            onOlder={setBefore}
            onNewest={() => setBefore(null)}
            onBack={() => {
              setSelected(null);
              setDetail(null);
              setThread(null);
            }}
            onFicha={() => setFicha(true)}
            scheduleSignal={scheduleSignal}
            onClaim={() =>
              id &&
              void act(async () => {
                await chatApi.claim(id);
                return chatApi.detail(id);
              })
            }
            onStage={(stage) => id && void act(() => chatApi.patch(id, { stage }))}
            onResult={(result) => id && void act(() => chatApi.patch(id, { result }))}
            onArchive={() =>
              id && detail && void act(() => chatApi.patch(id, { archived: !detail.archived }))
            }
            onUnread={() => id && void act(() => chatApi.markUnread(id))}
            onSend={send}
            onSchedule={(text, at) =>
              id ? act(() => chatApi.schedule(id, text, at)) : Promise.resolve(false)
            }
          />
        </div>
        <div className="hidden min-h-0 overflow-hidden border border-l-0 border-line xl:flex [&>aside]:w-full">
          {panel}
        </div>
        <div className="hidden min-h-0 overflow-hidden rounded-r-2xl border border-l-0 border-line 2xl:flex [&>aside]:w-full">
          <LivePanel leads={leads} onOpen={(phone) => void openPhone(phone)} opening={opening} />
        </div>
      </main>

      {ficha && (
        <div className="fixed inset-0 z-40 flex flex-col bg-white xl:hidden">
          <div className="flex items-center justify-between border-b border-line p-3">
            <strong>Ficha del contacto</strong>
            <button type="button" onClick={() => setFicha(false)} aria-label="Cerrar ficha">
              <X size={18} />
            </button>
          </div>
          <div className="flex min-h-0 flex-1 [&>aside]:w-full">{panel}</div>
        </div>
      )}
    </div>
  );
}
