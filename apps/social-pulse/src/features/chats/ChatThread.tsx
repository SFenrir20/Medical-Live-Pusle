import { ChatImage, ImagePreview } from "./ChatImage";
import { FormEvent, Fragment, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Archive,
  ArchiveRestore,
  ArrowLeft,
  Check,
  CheckCheck,
  Clock,
  MailOpen,
  MoreVertical,
  ImagePlus,
  MessageCircle,
  Search,
  Send,
  Smile,
  Zap,
  X,
} from "lucide-react";
import type { CrmDetail, Message, QuickReply, Stage, Thread, WaStatus } from "./api";
import { Avatar } from "./ConversationList";
import { clock, dayLabel, dayOf, fullDate, nice, RESULTS, STAGES, STATUS_LABEL } from "./format";

const EMOJIS = [
  "😊",
  "🙂",
  "😉",
  "🙏",
  "👍",
  "👋",
  "😀",
  "😅",
  "❤️",
  "💙",
  "✨",
  "📅",
  "📍",
  "🕘",
  "✅",
  "📞",
  "🩺",
  "👩‍⚕️",
  "👨‍⚕️",
  "🙌",
  "😍",
  "🤝",
  "💬",
  "⭐",
];

function Ticks({ message }: { message: Message }) {
  if (message.direction !== "out") return null;
  const s = message.status;
  if (s === "read") return <CheckCheck size={14} className="text-[#53bdeb]" aria-label="Leído" />;
  if (s === "delivered")
    return <CheckCheck size={14} className="text-slate-400" aria-label="Entregado" />;
  if (s === "sent") return <Check size={14} className="text-slate-400" aria-label="Enviado" />;
  if (s === "unknown")
    return <AlertTriangle size={13} className="text-amber-600" aria-label="Sin confirmar" />;
  if (s === "blocked") return <X size={13} className="text-red-600" aria-label="No enviado" />;
  return <Clock size={12} className="text-slate-400" aria-label="En cola" />;
}

function timesTitle(m: Message): string {
  const lines = [`Estado: ${STATUS_LABEL[m.status] ?? m.status}`];
  if (m.sent_at) lines.push(`Enviado: ${fullDate(m.sent_at)}`);
  if (m.delivered_at) lines.push(`Entregado: ${fullDate(m.delivered_at)}`);
  if (m.read_at) lines.push(`Leído: ${fullDate(m.read_at)}`);
  if (m.sent_at || m.delivered_at || m.read_at)
    lines.push("Sin hora de origen se usa la hora en que se observó.");
  return lines.join("\n");
}

function lima(value: string): string {
  return `${value}:00-05:00`; // a datetime-local value is read as Lima time
}

export function ChatThread({
  detail,
  thread,
  status,
  canSend,
  quickReplies,
  busy,
  before,
  onOlder,
  onNewest,
  onBack,
  onFicha,
  scheduleSignal,
  onClaim,
  onStage,
  onResult,
  onArchive,
  onUnread,
  onSend,
  onSchedule,
}: {
  detail: CrmDetail | null;
  thread: Thread | null;
  status: WaStatus;
  canSend: boolean;
  quickReplies: QuickReply[];
  busy: boolean;
  before: number | null;
  onOlder: (id: number) => void;
  onNewest: () => void;
  onBack: () => void;
  onFicha: () => void;
  scheduleSignal: number;
  onClaim: () => void;
  onStage: (stage: Stage) => void;
  onResult: (value: string) => void;
  onArchive: () => void;
  onUnread: () => void;
  onSend: (text: string, file?: File) => Promise<boolean>;
  onSchedule: (text: string, sendAt: string) => Promise<boolean>;
}) {
  const [actionsOpen, setActionsOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [attachment, setAttachment] = useState<File | undefined>();
  const [imageError, setImageError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const [popover, setPopover] = useState<"replies" | "emoji" | "schedule" | null>(null);
  const [searching, setSearching] = useState(false);
  const [needle, setNeedle] = useState("");
  const [when, setWhen] = useState("");
  const list = useRef<HTMLDivElement>(null);
  const follow = useRef(true);

  const conversationId = detail?.id;
  useEffect(() => {
    if (scheduleSignal > 0) setPopover("schedule");
  }, [scheduleSignal]);
  useEffect(() => {
    setDraft("");
    setPopover(null);
    setSearching(false);
    setNeedle("");
    follow.current = true;
  }, [conversationId]);
  useEffect(() => {
    if (!before && follow.current && list.current)
      list.current.scrollTop = list.current.scrollHeight;
  }, [thread?.messages.length, conversationId, before]);

  const messages = useMemo(() => {
    const all = thread?.messages ?? [];
    return needle.trim()
      ? all.filter((m) => m.body.toLowerCase().includes(needle.trim().toLowerCase()))
      : all;
  }, [thread?.messages, needle]);

  const shortcutMatches = useMemo(() => {
    if (!draft.startsWith("/") || draft.includes(" ")) return [];
    const typed = draft.slice(1).toLowerCase();
    return quickReplies.filter((r) => r.shortcut.startsWith(typed)).slice(0, 5);
  }, [draft, quickReplies]);

  if (!detail)
    return (
      <section className="grid min-h-0 place-items-center bg-[#faf9f6] p-8 text-center text-muted">
        <div>
          <MessageCircle className="mx-auto mb-3" />
          Selecciona una conversación o abre el número de un contacto.
        </div>
      </section>
    );

  const own = detail.is_mine;
  const connected = status.state === "connected" && status.sync_ok !== false;
  const canWrite = canSend && own && connected;
  const fill = (text: string) =>
    text.replace(
      /\{\{\s*nombre\s*(?:\|([^}]*))?\}\}/g,
      (_, fallback) => detail.name || (fallback ?? "").trim(),
    );

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = draft.trim();
    if ((!text && !attachment) || busy || !canWrite) return;
    if (await onSend(text, attachment)) {
      setAttachment(undefined);
      setDraft("");
      follow.current = true;
    }
  };
  const key = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };
  const insert = (text: string) => {
    setDraft(
      (current) =>
        (current.startsWith("/") && !current.includes(" ") ? "" : current ? current + " " : "") +
        text,
    );
    setPopover(null);
  };
  const plan = async () => {
    if (attachment) {
      setImageError("El envío programado admite texto; envía la imagen desde el chat.");
      return;
    }
    const text = draft.trim();
    if (!text || !when) return;
    if (await onSchedule(text, lima(when))) {
      setDraft("");
      setWhen("");
      setPopover(null);
    }
  };
  const defaultWhen = () => {
    const d = new Date(Date.now() + 3600_000);
    const local = new Date(d.getTime() - 5 * 3600_000).toISOString().slice(0, 16);
    return local;
  };

  return (
    <section className="flex min-h-0 min-w-0 flex-col bg-white">
      <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <button
          type="button"
          onClick={onBack}
          className="rounded-lg p-1 text-muted hover:bg-slate-100 md:hidden"
          aria-label="Volver a la lista"
        >
          <ArrowLeft size={18} />
        </button>
        <Avatar name={detail.name} phone={detail.phone} size="size-10" />
        <div className="min-w-0 flex-1">
          <h2 className="truncate font-bold">{detail.name || nice(detail.phone)}</h2>
          <p className="truncate text-xs text-muted">
            {nice(detail.phone)} ·{" "}
            {detail.is_mine
              ? "Es tuyo"
              : detail.advisor_name
                ? `Lo atiende ${detail.advisor_name}`
                : "Sin asignar"}
          </p>
        </div>
        <button
          type="button"
          onClick={onFicha}
          className="rounded-xl border border-line px-3 py-2 text-xs font-bold text-muted hover:bg-slate-50 min-[68.75rem]:hidden"
        >
          Ficha
        </button>
        {canSend && !detail.advisor_id && (
          <button
            type="button"
            onClick={onClaim}
            disabled={busy}
            className="rounded-xl bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            Tomar contacto
          </button>
        )}
        <span className="ml-auto hidden rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-semibold text-emerald-700 min-[87.5rem]:inline">
          {detail.archived ? "Archivada" : "Conversación abierta"}
        </span>
        <button
          type="button"
          aria-label="Opciones de conversación"
          aria-expanded={actionsOpen}
          onClick={() => setActionsOpen(!actionsOpen)}
          className="rounded-xl border border-line p-2 text-muted"
        >
          <MoreVertical size={15} />
        </button>
      </header>

      {actionsOpen && (
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
          <select
            aria-label="Etapa del contacto"
            value={detail.stage}
            disabled={!detail.can_edit || busy}
            onChange={(e) => onStage(e.target.value as Stage)}
            className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-semibold disabled:opacity-60"
          >
            {STAGES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <select
            aria-label="Resultado"
            value={detail.result ?? ""}
            disabled={!detail.can_edit || busy}
            onChange={(e) => onResult(e.target.value)}
            className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm text-muted disabled:opacity-60"
          >
            <option value="">Marcar resultado</option>
            {RESULTS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
          <span className="ml-auto flex items-center gap-1.5">
            <button
              type="button"
              title="Marcar como no leído"
              aria-label="Marcar como no leído"
              disabled={!detail.can_edit || busy}
              onClick={onUnread}
              className="grid size-9 place-items-center rounded-lg border border-line hover:bg-slate-50 disabled:opacity-40"
            >
              <MailOpen size={16} />
            </button>
            <button
              type="button"
              title={detail.archived ? "Desarchivar" : "Archivar"}
              aria-label={detail.archived ? "Desarchivar" : "Archivar"}
              disabled={!detail.can_edit || busy}
              onClick={onArchive}
              className="grid size-9 place-items-center rounded-lg border border-line hover:bg-slate-50 disabled:opacity-40"
            >
              {detail.archived ? <ArchiveRestore size={16} /> : <Archive size={16} />}
            </button>
            <button
              type="button"
              title="Buscar en la conversación"
              aria-label="Buscar en la conversación"
              onClick={() => {
                setSearching((v) => !v);
                setNeedle("");
              }}
              className={`grid size-9 place-items-center rounded-lg border border-line hover:bg-slate-50 ${searching ? "bg-primary-soft text-primary" : ""}`}
            >
              <Search size={16} />
            </button>
          </span>
          {searching && (
            <input
              autoFocus
              value={needle}
              onChange={(e) => setNeedle(e.target.value)}
              placeholder="Buscar en esta conversación"
              className="w-full rounded-lg border border-line px-3 py-1.5 text-sm outline-none focus:border-primary"
            />
          )}
        </div>
      )}

      <div
        ref={list}
        onScroll={(e) => {
          const el = e.currentTarget;
          follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto bg-[#faf9f6] px-4 py-4 sm:px-8 [background-image:radial-gradient(rgb(14_148_171/12%)_1px,transparent_1px)] [background-size:18px_18px]"
      >
        <div className="flex justify-between text-xs font-semibold text-primary">
          {thread?.has_more && thread.messages[0] && (
            <button type="button" onClick={() => onOlder(thread.messages[0].id)}>
              Mensajes anteriores
            </button>
          )}
          {before && (
            <button type="button" onClick={onNewest}>
              Volver a recientes
            </button>
          )}
        </div>
        {thread && !messages.length && (
          <p className="m-auto max-w-sm rounded-xl bg-white/80 p-4 text-center text-sm text-muted">
            {needle
              ? "Ningún mensaje coincide."
              : "Sin mensajes registrados. La sincronización comienza al vincular; no importa todo el historial anterior."}
          </p>
        )}
        {messages.map((m, i) => {
          const out = m.direction === "out";
          const newDay = i === 0 || dayOf(messages[i - 1].at) !== dayOf(m.at);
          return (
            <Fragment key={m.id}>
              {newDay && (
                <span className="my-2 self-center rounded-lg bg-white px-3 py-1 text-[11px] font-semibold text-muted shadow-sm">
                  {dayLabel(m.at)}
                </span>
              )}
              <article
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-xs leading-5 shadow-sm sm:max-w-[85%] ${out ? "self-end rounded-tr-sm bg-[#dcf8e7]" : "self-start rounded-tl-sm bg-white"}`}
              >
                {out && (
                  <p className="text-[11px] font-bold text-emerald-800">
                    {m.author_kind === "agent"
                      ? m.author_name || m.author_id
                      : "Desde teléfono u otro dispositivo"}
                  </p>
                )}
                {m.has_image && <ChatImage messageId={m.id} />}
                {(m.body !== "[Imagen]" || !m.has_image) && (
                  <p className="whitespace-pre-wrap break-words">{m.body}</p>
                )}
                <p
                  title={timesTitle(m)}
                  className="mt-0.5 flex items-center justify-end gap-1 text-[10.5px] text-[#667781]"
                >
                  {clock(m.at)} <Ticks message={m} />
                </p>
                {m.status !== "sent" &&
                  m.status !== "delivered" &&
                  m.status !== "read" &&
                  m.status !== "received" && (
                    <p className="text-[10.5px] text-[#667781]">
                      {STATUS_LABEL[m.status] ?? m.status}
                    </p>
                  )}
                {m.error && <p className="mt-1 text-xs text-amber-800">{m.error}</p>}
              </article>
            </Fragment>
          );
        })}
      </div>

      <div className="relative border-t border-line bg-white p-3">
        {!canSend && (
          <p className="px-2 pb-2 text-xs text-muted">Tu rol solo revisa las conversaciones.</p>
        )}
        {canSend && !own && (
          <p className="px-2 pb-2 text-xs text-muted">
            {detail.advisor_id
              ? `Lo atiende ${detail.advisor_name ?? "otra persona"}: un supervisor puede reasignarlo.`
              : "Toma el contacto para responder."}
          </p>
        )}
        {canSend && own && !connected && (
          <p className="px-2 pb-2 text-xs text-amber-800">
            WhatsApp no está conectado o la sincronización no está al día: no se puede enviar ahora.
          </p>
        )}

        {popover === "replies" && (
          <div className="absolute bottom-full left-3 z-10 mb-2 max-h-72 w-[min(22rem,90%)] overflow-y-auto rounded-2xl border border-line bg-white p-2 shadow-xl">
            <p className="px-2 py-1 text-[11px] font-bold uppercase tracking-wide text-muted">
              Mensajes pregrabados
            </p>
            {quickReplies.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => insert(fill(r.body))}
                className="block w-full rounded-xl p-2 text-left hover:bg-slate-50"
              >
                <span className="flex items-center gap-2 text-sm font-semibold">
                  {r.title}
                  <code className="rounded bg-slate-100 px-1.5 text-[11px] font-normal text-muted">
                    /{r.shortcut}
                  </code>
                </span>
                <span className="line-clamp-2 text-xs text-muted">{r.body}</span>
              </button>
            ))}
            {!quickReplies.length && (
              <p className="p-3 text-sm text-muted">
                Todavía no hay mensajes pregrabados. Un supervisor los crea en el CRM.
              </p>
            )}
          </div>
        )}
        {popover === "emoji" && (
          <div className="absolute bottom-full left-3 z-10 mb-2 grid w-64 grid-cols-6 gap-1 rounded-2xl border border-line bg-white p-2 shadow-xl">
            {EMOJIS.map((e) => (
              <button
                key={e}
                type="button"
                onClick={() => {
                  setDraft((d) => d + e);
                  setPopover(null);
                }}
                className="rounded-lg p-1.5 text-xl hover:bg-slate-100"
              >
                {e}
              </button>
            ))}
          </div>
        )}
        {popover === "schedule" && (
          <div className="absolute bottom-full right-3 z-10 mb-2 w-72 space-y-2 rounded-2xl border border-line bg-white p-3 shadow-xl">
            <p className="text-sm font-bold">Programar este mensaje</p>
            <p className="text-xs text-muted">
              Sale solo a la hora indicada (hora de Lima), si el contacto sigue siendo tuyo. Puedes
              cancelarlo desde la ficha.
            </p>
            <input
              type="datetime-local"
              className="w-full rounded-lg border border-line px-3 py-2 text-sm"
              min={defaultWhen().slice(0, 16)}
              value={when || defaultWhen()}
              onChange={(e) => setWhen(e.target.value)}
            />
            <button
              type="button"
              disabled={!draft.trim() || busy || !canWrite}
              onClick={() => void plan()}
              className="w-full rounded-xl bg-primary px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
            >
              Programar
            </button>
            {!draft.trim() && <p className="text-[11px] text-muted">Escribe primero el mensaje.</p>}
          </div>
        )}
        {shortcutMatches.length > 0 && (
          <div className="absolute bottom-full left-3 z-10 mb-2 w-[min(22rem,90%)] rounded-2xl border border-line bg-white p-1 shadow-xl">
            {shortcutMatches.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => insert(fill(r.body))}
                className="block w-full rounded-xl p-2 text-left hover:bg-slate-50"
              >
                <span className="text-sm font-semibold">/{r.shortcut}</span>{" "}
                <span className="text-xs text-muted">{r.title}</span>
              </button>
            ))}
          </div>
        )}

        {attachment && (
          <div className="mb-2 flex items-start gap-3">
            <ImagePreview file={attachment} />
            <button
              type="button"
              disabled={busy}
              onClick={() => setAttachment(undefined)}
              className="text-xs text-primary"
            >
              Quitar imagen
            </button>
            <span className="text-xs text-muted">{attachment.name}</span>
          </div>
        )}
        {imageError && (
          <p role="alert" className="mb-2 text-xs text-red-700">
            {imageError}
          </p>
        )}
        <input
          ref={fileInput}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            setImageError("");
            if (!file) return;
            if (
              !["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
              file.size > 8 * 1024 * 1024
            ) {
              setImageError("Selecciona una imagen JPG, PNG o WebP de hasta 8 MB.");
              return;
            }
            setAttachment(file);
            setPopover(null);
          }}
        />
        <form
          onSubmit={submit}
          className="flex items-end gap-1 rounded-2xl border border-line bg-canvas p-1.5"
        >
          <button
            type="button"
            title="Emojis"
            aria-label="Emojis"
            onClick={() => setPopover(popover === "emoji" ? null : "emoji")}
            className="grid size-10 shrink-0 place-items-center rounded-full text-[#54656f] hover:bg-slate-200"
          >
            <Smile size={20} />
          </button>
          <button
            type="button"
            title="Adjuntar imagen"
            aria-label="Adjuntar imagen"
            disabled={!canWrite || busy}
            onClick={() => fileInput.current?.click()}
            className="grid size-10 shrink-0 place-items-center rounded-full text-[#54656f] disabled:opacity-40"
          >
            <ImagePlus size={20} />
          </button>
          <textarea
            aria-label="Mensaje de WhatsApp"
            rows={1}
            value={draft}
            maxLength={4000}
            disabled={!canWrite || busy}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={key}
            placeholder={
              canWrite
                ? "Escribe un mensaje (/ para respuestas rápidas)"
                : "No puedes escribir en esta conversación"
            }
            className="max-h-32 min-h-10 min-w-0 flex-1 resize-none rounded-2xl border-0 bg-white px-4 py-2.5 text-sm outline-none disabled:opacity-60"
          />
          <button
            type="button"
            title="Mensajes pregrabados"
            aria-label="Mensajes pregrabados"
            onClick={() => setPopover(popover === "replies" ? null : "replies")}
            className="hidden size-10 shrink-0 place-items-center rounded-full text-muted 2xl:grid"
          >
            <Zap size={19} />
          </button>
          <button
            type="button"
            title="Programar envío"
            aria-label="Programar envío"
            disabled={!canWrite || !!attachment}
            onClick={() => setPopover(popover === "schedule" ? null : "schedule")}
            className="hidden size-10 shrink-0 place-items-center rounded-full text-muted disabled:opacity-40 2xl:grid"
          >
            <Clock size={19} />
          </button>
          <button
            disabled={busy || !canWrite || (!draft.trim() && !attachment)}
            title="Enviar"
            aria-label="Enviar"
            className="grid size-10 shrink-0 place-items-center rounded-full bg-primary text-white disabled:opacity-40"
          >
            <Send size={18} />
          </button>
        </form>
        <p className="px-2 pt-1.5 text-[11px] text-[#667781]">
          Texto e imágenes por WhatsApp (hasta 8 MB). Enviado, entregado y leído se registran por
          separado: «leído» no prueba que respondió.
        </p>
      </div>
    </section>
  );
}
