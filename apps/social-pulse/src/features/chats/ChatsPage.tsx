import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ChevronDown, X } from "lucide-react";
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
import { ChatsHome } from "./ChatsHome";
import { ChatThread } from "./ChatThread";
import { ContactPanel } from "./ContactPanel";
import { ConversationList } from "./ConversationList";
import { fullDate } from "./format";
import { LivePanel } from "./LivePanel";
import { pollVisible } from "./polling";

const STATES: Record<string, string> = {
  connected: "Conectado",
  connecting: "Conectando",
  qr: "Espera vinculación",
  disconnected: "Desconectado",
  unavailable: "Conector no disponible",
  relink_required: "Requiere nueva vinculación",
  wrong_number: "No se pudo identificar la cuenta o no coincide con la cuenta vinculada",
};
const NO_COUNTS: Counts = { all: 0, mine: 0, unread: 0, waiting: 0, unassigned: 0, archived: 0 };

/** Keeps the previous object when nothing changed, so rows that did not change are not redrawn. */
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
function keepUnchanged<T extends { id: number }>(old: T[], next: T[]): T[] {
  const before = new Map(old.map((x) => [x.id, x]));
  const merged = next.map((x) => {
    const prior = before.get(x.id);
    return prior && same(prior, x) ? prior : x;
  });
  return merged.length === old.length && merged.every((x, i) => x === old[i]) ? old : merged;
}

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
  const [listLoaded, setListLoaded] = useState(false);
  const [waitingList, setWaitingList] = useState<ConversationItem[]>([]);
  const [statusOpen, setStatusOpen] = useState(false);
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
  const [liveOpen, setLiveOpen] = useState(false);
  const [scheduleSignal, setScheduleSignal] = useState(0);
  const request = useRef<{ id: string; text: string; conversation: number; file?: File } | null>(
    null,
  );
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const seenFor = useRef<number | null>(null);
  const listKey = JSON.stringify([scope, search, offset]);
  const listKeyRef = useRef(listKey);
  listKeyRef.current = listKey;
  const listRequest = useRef(0);

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

  const refreshStatus = useCallback(async (signal?: AbortSignal) => {
    const connection = await chatApi.status(signal);
    if (signal?.aborted) return;
    setStatus((old) => (same(old, connection) ? old : connection));
  }, []);

  const refreshList = useCallback(
    async (signal?: AbortSignal) => {
      if (listKeyRef.current !== listKey) return;
      const requestId = ++listRequest.current;
      const list = await chatApi.conversations(scope, search, offset, signal);
      if (signal?.aborted || listKeyRef.current !== listKey || requestId !== listRequest.current)
        return;
      setItems((old) => keepUnchanged(old, list.items));
      setCounts((old) => (same(old, list.counts) ? old : list.counts));
      setHasMore(list.has_more);
      setListLoaded(true);
    },
    [scope, search, offset, listKey],
  );

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
    return pollVisible(refreshList, 4000, (e) => setError(problem(e)), 100);
  }, [mayRead, refreshList]);

  // The status probe never holds up the inbox, and resumes immediately on reconnect.
  useEffect(() => {
    if (!mayRead) return;
    return pollVisible(refreshStatus, 8000, () =>
      setStatus((old) => (old.state === "unavailable" ? old : { state: "unavailable" })),
    );
  }, [mayRead, refreshStatus]);

  // With no conversation open the middle shows who is waiting for an answer.
  useEffect(() => {
    if (!mayRead || selected) return;
    return pollVisible(
      async (signal) => {
        const waiting = await chatApi.conversations("waiting", "", 0, signal);
        if (signal.aborted) return;
        setWaitingList((old) =>
          keepUnchanged(
            old,
            [...waiting.items]
              .sort((a, b) => (a.last?.at ?? "").localeCompare(b.last?.at ?? ""))
              .slice(0, 8),
          ),
        );
      },
      10000,
      () => undefined,
    );
  }, [mayRead, selected]);

  useEffect(() => {
    if (!mayRead || !selected) return;
    return pollVisible(
      async (signal) => {
        const [crm, messages] = await Promise.all([
          chatApi.detail(selected, signal),
          chatApi.thread(selected, before, signal),
        ]);
        if (signal.aborted || selectedRef.current !== selected) return;
        setDetail((old) => (old && same(old, crm) ? old : crm));
        setThread((old) => {
          if (!old) return messages;
          const kept = keepUnchanged(old.messages, messages.messages);
          return kept === old.messages &&
            old.has_more === messages.has_more &&
            same(old.lives, messages.lives)
            ? old
            : { ...messages, messages: kept };
        });
      },
      3000,
      (e) => setError(problem(e)),
    );
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
      if (result && result.id === selectedRef.current) setDetail(result);
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

  const send = async (text: string, file?: File): Promise<boolean> => {
    if (!id) return false;
    if (
      !request.current ||
      request.current.text !== text ||
      request.current.conversation !== id ||
      request.current.file !== file
    )
      request.current = { id: crypto.randomUUID(), text, conversation: id, file };
    const requestId = request.current.id;
    setBusy(true);
    setError("");
    try {
      const message = file
        ? await chatApi.sendImage(id, requestId, text, file)
        : await chatApi.send(id, requestId, text);
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
      key={selected}
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
      onRefresh={() => {
        if (id)
          void chatApi
            .detail(id)
            .then(setDetail)
            .catch(() => undefined);
        void refreshList().catch(() => undefined);
      }}
    />
  );

  const notices: string[] = [];
  if (status.state === "disconnected" && status.retry_at)
    notices.push("Se perdió la conexión. Estamos intentando recuperarla sin borrar la sesión.");
  if (status.state === "connected" && status.sync_ok === false)
    notices.push(
      `WhatsApp está vinculado, pero la sincronización no está al día. Última sincronización: ${fullDate(status.sync_at || null)}. Contacta al administrador.`,
    );
  if (status.unresolved)
    notices.push(
      "Hay mensajes pendientes de identificar por teléfono. El conector reintentará al recibir la correspondencia de WhatsApp.",
    );
  if (status.rejected)
    notices.push(
      `Hay ${status.rejected} mensajes o confirmaciones guardados pendientes de revisión por un error de datos. Contacta al administrador.`,
    );
  if (status.pending_events && status.sync_ok === false)
    notices.push(`Hay ${status.pending_events} eventos guardados esperando sincronización.`);
  if (status.detail) notices.push(status.detail);
  const healthy = status.state === "connected" && notices.length === 0;
  const current = items.find((c) => c.id === selected) ?? null;

  return (
    <div className="flex h-dvh flex-col bg-canvas text-ink">
      <AppNav />
      <div className="space-y-2 px-4 pt-3 sm:px-6">
        <div className="relative flex flex-wrap items-center gap-3 text-sm">
          <button
            type="button"
            aria-expanded={statusOpen}
            onClick={() => setStatusOpen((v) => !v)}
            className={`flex items-center gap-2 rounded-full px-3 py-1 text-xs font-bold ${healthy ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}
          >
            <span
              className={`size-2 rounded-full ${healthy ? "bg-emerald-500" : "bg-amber-500"}`}
            />
            WhatsApp · {STATES[status.state] || status.state} {status.phone}
            {notices.length > 0 && (
              <span className="flex items-center gap-1 rounded-full bg-amber-200/70 px-1.5">
                <AlertTriangle size={11} /> {notices.length}
              </span>
            )}
            <ChevronDown size={13} className={statusOpen ? "rotate-180" : ""} />
          </button>
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
          <button
            type="button"
            onClick={() => setLiveOpen(true)}
            className="ml-auto rounded-xl border border-line bg-white px-3 py-1.5 text-xs text-primary min-[68.75rem]:hidden"
          >
            TikTok LIVE
          </button>
          {statusOpen && (
            <div
              role="status"
              className="absolute left-0 top-full z-30 mt-2 w-[min(26rem,92vw)] space-y-2 rounded-2xl border border-line bg-white p-4 text-sm shadow-xl"
            >
              <p className="font-bold">Estado de la conexión</p>
              <p className="text-xs text-muted">
                {STATES[status.state] || status.state}
                {status.phone ? ` · ${status.phone}` : ""}
                {status.sync_at ? ` · última sincronización ${fullDate(status.sync_at)}` : ""}
              </p>
              {notices.map((text) => (
                <p key={text} className="rounded-xl bg-amber-50 p-3 text-xs text-amber-800">
                  {text}
                </p>
              ))}
              {!notices.length && <p className="text-xs text-emerald-700">Todo en orden.</p>}
            </div>
          )}
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

      <main className="mx-3 my-4 grid min-h-0 flex-1 grid-cols-1 overflow-hidden rounded-[24px] border border-line bg-white shadow-sm sm:mx-6 md:grid-cols-[320px_minmax(0,1fr)] min-[68.75rem]:grid-cols-[320px_minmax(320px,1fr)_220px_230px] 2xl:grid-cols-[360px_minmax(0,1fr)_260px_270px]">
        <div
          className={`min-h-0 overflow-hidden md:flex ${selected ? "hidden" : "flex"} [&>aside]:w-full`}
        >
          <ConversationList
            items={items}
            loaded={listLoaded}
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
          className={`min-h-0 overflow-hidden md:flex ${selected ? "flex" : "hidden"} [&>section]:w-full`}
        >
          {!selected && (
            <ChatsHome
              counts={counts}
              waiting={waitingList}
              loaded={listLoaded}
              onScope={(next) => {
                setScope(next);
                setOffset(0);
              }}
              onSelect={choose}
            />
          )}
          {selected && (
            <ChatThread
              key={selected}
              item={current}
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
          )}
        </div>
        <div className="hidden min-h-0 overflow-hidden min-[68.75rem]:flex [&>aside]:w-full">
          {panel}
        </div>
        <div className="hidden min-h-0 overflow-hidden min-[68.75rem]:flex [&>aside]:w-full">
          <LivePanel leads={leads} onOpen={(phone) => void openPhone(phone)} opening={opening} />
        </div>
      </main>

      {liveOpen && (
        <div className="fixed inset-0 z-40 flex flex-col bg-white min-[68.75rem]:hidden">
          <button
            type="button"
            onClick={() => setLiveOpen(false)}
            className="border-b border-line p-4 text-right text-primary"
          >
            Cerrar TikTok LIVE
          </button>
          <LivePanel
            leads={leads}
            onOpen={(phone) => {
              setLiveOpen(false);
              void openPhone(phone);
            }}
            opening={opening}
          />
        </div>
      )}
      {ficha && (
        <div className="fixed inset-0 z-40 flex flex-col bg-white min-[68.75rem]:hidden">
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
