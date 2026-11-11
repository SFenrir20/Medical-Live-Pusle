import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import {
  chatApi,
  type ConversationItem,
  type CrmDetail,
  problem,
  type QuickReply,
  type Stage,
  type TeamMember,
  type Thread,
  type WaStatus,
} from "./api";
import { ChatThread } from "./ChatThread";
import { ContactPanel } from "./ContactPanel";
import { pollVisible } from "./polling";

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** A conversation in a window over the page you are on (the funnel board): the same chat and
 *  contact file as the inbox, without leaving. `onChanged` tells the page to refresh itself. */
export function ConversationDialog({
  conversationId,
  item,
  onClose,
  onChanged,
}: {
  conversationId: number;
  item: ConversationItem | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { user } = useAuth();
  const permissions = user?.permissions ?? [];
  const maySend = permissions.includes("wa:send");
  const mayAssign = permissions.includes("contacts:assign_any");

  const [detail, setDetail] = useState<CrmDetail | null>(null);
  const [thread, setThread] = useState<Thread | null>(null);
  const [before, setBefore] = useState<number | null>(null);
  const [status, setStatus] = useState<WaStatus>({ state: "connecting" });
  const [replies, setReplies] = useState<QuickReply[]>([]);
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ficha, setFicha] = useState(false);
  const [scheduleSignal, setScheduleSignal] = useState(0);
  const request = useRef<{ id: string; text: string; file?: File } | null>(null);
  const seenFor = useRef<number | null>(null);

  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);

  useEffect(
    () =>
      pollVisible(
        async (signal) => {
          const [crm, messages] = await Promise.all([
            chatApi.detail(conversationId, signal),
            chatApi.thread(conversationId, before, signal),
          ]);
          if (signal.aborted) return;
          setDetail((old) => (old && same(old, crm) ? old : crm));
          setThread((old) => (old && same(old, messages) ? old : messages));
        },
        3000,
        (e) => setError(problem(e)),
      ),
    [conversationId, before],
  );
  useEffect(
    () =>
      pollVisible(
        async (signal) => {
          const next = await chatApi.status(signal);
          if (!signal.aborted) setStatus((old) => (same(old, next) ? old : next));
        },
        15000,
        () => setStatus({ state: "unavailable" }),
      ),
    [],
  );
  useEffect(() => {
    void chatApi
      .quickReplies()
      .then(setReplies)
      .catch(() => undefined);
    if (mayAssign)
      void chatApi
        .team()
        .then(setTeam)
        .catch(() => undefined);
  }, [mayAssign]);

  // Opening one of your own unread conversations marks it reviewed (no WhatsApp read receipt).
  useEffect(() => {
    if (
      detail?.is_mine &&
      detail.unread > 0 &&
      maySend &&
      seenFor.current !== detail.id + detail.unread
    ) {
      seenFor.current = detail.id + detail.unread;
      void chatApi
        .seen(detail.id)
        .then(onChanged)
        .catch(() => undefined);
    }
  }, [detail, maySend, onChanged]);

  const act = async (work: () => Promise<CrmDetail | void>): Promise<boolean> => {
    setBusy(true);
    setError("");
    try {
      const result = await work();
      if (result) setDetail(result);
      onChanged();
      return true;
    } catch (e) {
      setError(problem(e));
      return false;
    } finally {
      setBusy(false);
    }
  };
  const id = conversationId;
  const claim = () =>
    void act(async () => {
      await chatApi.claim(id);
      return chatApi.detail(id);
    });

  const send = async (text: string, file?: File): Promise<boolean> => {
    if (!request.current || request.current.text !== text || request.current.file !== file)
      request.current = { id: crypto.randomUUID(), text, file };
    const requestId = request.current.id;
    setBusy(true);
    setError("");
    try {
      const message = file
        ? await chatApi.sendImage(id, requestId, text, file)
        : await chatApi.send(id, requestId, text);
      setThread((old) =>
        old
          ? { ...old, messages: [...old.messages.filter((m) => m.id !== message.id), message] }
          : old,
      );
      setBefore(null);
      request.current = null;
      onChanged();
      return true;
    } catch (e) {
      setError(problem(e));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const panel = (
    <ContactPanel
      detail={detail}
      thread={thread}
      canSend={maySend}
      mayAssign={mayAssign}
      team={team}
      busy={busy}
      onStage={(stage: Stage) => void act(() => chatApi.patch(id, { stage }))}
      onTags={(tags) => void act(() => chatApi.patch(id, { tags }))}
      onAssign={(advisor) => void act(() => chatApi.assign(id, advisor))}
      onClaim={claim}
      onAddNote={(text) => act(() => chatApi.addNote(id, text))}
      onDeleteNote={(note) => void act(() => chatApi.deleteNote(note))}
      onCancelScheduled={(scheduled) => void act(() => chatApi.cancelScheduled(scheduled))}
      onConsent={(state, note) => void act(() => chatApi.setConsent(id, state, note))}
      onSchedule={() => {
        setFicha(false);
        setScheduleSignal((n) => n + 1);
      }}
      onRefresh={() => {
        void chatApi
          .detail(id)
          .then(setDetail)
          .catch(() => undefined);
        onChanged();
      }}
    />
  );

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-3 sm:p-6"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Conversación"
        className="relative flex h-[min(92dvh,52rem)] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
      >
        <div className="flex items-center justify-end border-b border-line bg-white px-4 py-2">
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar conversación"
            className="rounded-lg p-1.5 text-muted hover:bg-slate-100"
          >
            <X size={18} />
          </button>
        </div>
        {error && (
          <p
            role="alert"
            className="flex items-start justify-between gap-3 bg-red-50 px-4 py-2 text-sm text-red-800"
          >
            {error}
            <button type="button" onClick={() => setError("")} aria-label="Cerrar aviso">
              <X size={14} />
            </button>
          </p>
        )}
        <div className="grid min-h-0 flex-1 grid-cols-1 min-[56rem]:grid-cols-[minmax(0,1fr)_300px] [&>section]:min-h-0">
          <ChatThread
            key={conversationId}
            item={item}
            detail={detail}
            thread={thread}
            status={status}
            canSend={maySend}
            quickReplies={replies}
            busy={busy}
            before={before}
            onOlder={setBefore}
            onNewest={() => setBefore(null)}
            onBack={onClose}
            onFicha={() => setFicha(true)}
            scheduleSignal={scheduleSignal}
            onClaim={claim}
            onStage={(stage) => void act(() => chatApi.patch(id, { stage }))}
            onResult={(result) => void act(() => chatApi.patch(id, { result }))}
            onArchive={() =>
              detail && void act(() => chatApi.patch(id, { archived: !detail.archived }))
            }
            onUnread={() => void act(() => chatApi.markUnread(id))}
            onSend={send}
            onSchedule={(text, at) => act(() => chatApi.schedule(id, text, at))}
          />
          <div className="hidden min-h-0 overflow-hidden border-l border-line min-[56rem]:flex [&>aside]:w-full">
            {panel}
          </div>
        </div>
        {ficha && (
          <div className="absolute inset-0 z-10 flex flex-col bg-white min-[56rem]:hidden">
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
    </div>
  );
}
