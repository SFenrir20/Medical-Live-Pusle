import { FormEvent, useRef, useState } from "react";
import { Bot, CalendarClock, Copy, Phone, StickyNote, Tag, Trash2, X } from "lucide-react";
import type { CrmDetail, Stage, TeamMember, Thread } from "./api";
import { Avatar } from "./ConversationList";
import { fullDate, nice, STAGES, TAG_SUGGESTIONS } from "./format";

const label = "text-[10px] font-bold uppercase tracking-[0.14em] text-muted";

export function ContactPanel({
  detail,
  thread,
  canSend,
  mayAssign,
  team,
  busy,
  onStage,
  onTags,
  onAssign,
  onClaim,
  onAddNote,
  onDeleteNote,
  onCancelScheduled,
  onConsent,
  onSchedule,
}: {
  detail: CrmDetail | null;
  thread: Thread | null;
  canSend: boolean;
  mayAssign: boolean;
  team: TeamMember[];
  busy: boolean;
  onStage: (stage: Stage) => void;
  onTags: (tags: string[]) => void;
  onAssign: (advisorId: string | null) => void;
  onClaim: () => void;
  onAddNote: (text: string) => Promise<boolean>;
  onDeleteNote: (id: number) => void;
  onCancelScheduled: (id: number) => void;
  onConsent: (status: "granted" | "revoked", note: string) => void;
  onSchedule: () => void;
}) {
  const [tag, setTag] = useState("");
  const [note, setNote] = useState("");
  const [consentNote, setConsentNote] = useState("");
  const [copied, setCopied] = useState(false);
  const noteBox = useRef<HTMLTextAreaElement>(null);

  if (!detail)
    return (
      <aside className="hidden border-l border-line bg-white p-6 text-sm text-muted xl:block">
        La ficha del contacto aparece al abrir una conversación.
      </aside>
    );

  const can = detail.can_edit && !busy;
  const copy = async () => {
    await navigator.clipboard.writeText(detail.phone);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  const addTag = (event?: FormEvent, value = tag) => {
    event?.preventDefault();
    const clean = value.trim().slice(0, 30);
    if (!clean || detail.tags.some((t) => t.toLowerCase() === clean.toLowerCase()))
      return setTag("");
    onTags([...detail.tags, clean]);
    setTag("");
  };
  const saveNote = async (event: FormEvent) => {
    event.preventDefault();
    if (note.trim() && (await onAddNote(note.trim()))) setNote("");
  };
  const consent = detail.opted_out
    ? { text: "Pidió no recibir mensajes", style: "bg-red-50 text-red-700" }
    : detail.consent === "granted"
      ? { text: "WhatsApp autorizado", style: "bg-emerald-50 text-emerald-700" }
      : detail.consent === "revoked"
        ? { text: "Autorización revocada", style: "bg-red-50 text-red-700" }
        : { text: "Sin consentimiento", style: "bg-slate-100 text-slate-600" };

  return (
    <aside className="flex min-h-0 flex-col overflow-y-auto border-l border-line bg-white">
      <div className="space-y-3 p-5 text-center">
        <div className="flex justify-center">
          <Avatar name={detail.name} phone={detail.phone} size="size-16" />
        </div>
        <div>
          <h3 className="font-bold">{detail.name || nice(detail.phone)}</h3>
          <p className="text-xs text-muted">
            {detail.origin === "tiktok_live"
              ? `Contacto de TikTok LIVE · ${detail.lives} aparición(es)`
              : "Escribió por WhatsApp"}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void copy()}
          className="mx-auto flex items-center gap-2 rounded-full bg-primary-soft px-4 py-1.5 text-sm font-semibold text-primary"
        >
          <Copy size={13} /> {copied ? "Copiado" : nice(detail.phone)}
        </button>
      </div>

      <div className="space-y-5 border-t border-line p-5">
        <section>
          <p className={label}>Etapa CRM</p>
          <select
            aria-label="Etapa CRM"
            disabled={!can}
            value={detail.stage}
            onChange={(e) => onStage(e.target.value as Stage)}
            className="mt-2 w-full rounded-xl border border-line bg-white px-3 py-2 text-sm font-semibold disabled:opacity-60"
          >
            {STAGES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </section>

        <section>
          <p className={label}>Responsable</p>
          {mayAssign ? (
            <select
              aria-label="Responsable"
              disabled={busy}
              value={detail.advisor_id ?? ""}
              onChange={(e) => onAssign(e.target.value || null)}
              className="mt-2 w-full rounded-xl border border-line bg-white px-3 py-2 text-sm disabled:opacity-60"
            >
              <option value="">Sin asignar</option>
              {team.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          ) : (
            <div className="mt-2 flex items-center justify-between gap-2 rounded-xl bg-slate-50 p-3 text-sm">
              <span>{detail.is_mine ? "Tú" : (detail.advisor_name ?? "Sin asignar")}</span>
              {canSend && !detail.advisor_id && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={onClaim}
                  className="font-bold text-primary disabled:opacity-50"
                >
                  Tomar
                </button>
              )}
            </div>
          )}
        </section>

        <section>
          <p className={`${label} flex items-center gap-1`}>
            <Tag size={11} /> Etiquetas
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {detail.tags.map((t) => (
              <span
                key={t}
                className="flex items-center gap-1 rounded-full bg-violet-50 px-2.5 py-1 text-[11px] font-semibold text-violet-700"
              >
                {t}
                {can && (
                  <button
                    type="button"
                    aria-label={`Quitar ${t}`}
                    onClick={() => onTags(detail.tags.filter((x) => x !== t))}
                  >
                    <X size={11} />
                  </button>
                )}
              </span>
            ))}
            {!detail.tags.length && <span className="text-xs text-muted">Sin etiquetas</span>}
          </div>
          {can && (
            <>
              <form onSubmit={addTag} className="mt-2 flex gap-2">
                <input
                  aria-label="Nueva etiqueta"
                  maxLength={30}
                  value={tag}
                  onChange={(e) => setTag(e.target.value)}
                  placeholder="Agregar etiqueta"
                  className="min-w-0 flex-1 rounded-lg border border-line px-3 py-1.5 text-xs outline-none focus:border-primary"
                />
                <button className="rounded-lg bg-slate-100 px-3 text-xs font-bold">Añadir</button>
              </form>
              <div className="mt-2 flex flex-wrap gap-1">
                {TAG_SUGGESTIONS.filter(
                  (s) => !detail.tags.some((t) => t.toLowerCase() === s.toLowerCase()),
                ).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => addTag(undefined, s)}
                    className="rounded-full border border-dashed border-line px-2 py-0.5 text-[10px] text-muted hover:border-primary hover:text-primary"
                  >
                    + {s}
                  </button>
                ))}
              </div>
            </>
          )}
        </section>

        <section>
          <p className={label}>Consentimiento WhatsApp</p>
          <span
            className={`mt-2 inline-block rounded-full px-3 py-1 text-xs font-bold ${consent.style}`}
          >
            {consent.text}
          </span>
          {detail.consent_note && (
            <p className="mt-1 text-[11px] text-muted">
              {detail.consent_note} · {fullDate(detail.consent_at)}
            </p>
          )}
          {can && !detail.opted_out && (
            <div className="mt-2 space-y-2">
              <input
                aria-label="Nota del consentimiento"
                value={consentNote}
                onChange={(e) => setConsentNote(e.target.value)}
                maxLength={200}
                placeholder="Cómo lo aceptó (opcional)"
                className="w-full rounded-lg border border-line px-3 py-1.5 text-xs outline-none focus:border-primary"
              />
              <div className="flex gap-2">
                {detail.consent !== "granted" && (
                  <button
                    type="button"
                    onClick={() => onConsent("granted", consentNote)}
                    className="flex-1 rounded-lg bg-emerald-600 px-2 py-1.5 text-xs font-bold text-white"
                  >
                    Marcar autorizado
                  </button>
                )}
                {detail.consent !== "revoked" && (
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm("¿Revocar? No se le escribirá más con bots ni campañas."))
                        onConsent("revoked", consentNote);
                    }}
                    className="flex-1 rounded-lg border border-red-200 px-2 py-1.5 text-xs font-bold text-red-600"
                  >
                    Revocar
                  </button>
                )}
              </div>
            </div>
          )}
          <p className="mt-2 text-[11px] text-muted">
            Hace falta para campañas y bots. Responder a quien te escribe no lo necesita.
          </p>
        </section>

        <section className="space-y-1 border-t border-line pt-4 text-sm">
          <a
            href={`tel:${detail.phone}`}
            className="flex items-center gap-3 rounded-xl p-2.5 font-medium hover:bg-slate-50"
          >
            <Phone size={16} className="text-muted" /> Llamar al contacto
          </a>
          <button
            type="button"
            disabled={!can}
            onClick={() => noteBox.current?.focus()}
            className="flex w-full items-center gap-3 rounded-xl p-2.5 text-left font-medium hover:bg-slate-50 disabled:opacity-40"
          >
            <StickyNote size={16} className="text-muted" /> Agregar nota
          </button>
          <button
            type="button"
            disabled={!canSend || !detail.is_mine}
            onClick={onSchedule}
            className="flex w-full items-center gap-3 rounded-xl p-2.5 text-left font-medium hover:bg-slate-50 disabled:opacity-40"
          >
            <CalendarClock size={16} className="text-muted" /> Programar mensaje
          </button>
          <button
            type="button"
            disabled
            title="Los bots no están conectados al WhatsApp real: se prueban en el simulador de Automatización."
            className="flex w-full items-center gap-3 rounded-xl p-2.5 text-left font-medium opacity-40"
          >
            <Bot size={16} /> Activar automatización
          </button>
        </section>

        <section>
          <p className={label}>Notas internas</p>
          <p className="mt-1 text-[11px] text-muted">La persona no las ve.</p>
          {can && (
            <form onSubmit={saveNote} className="mt-2">
              <textarea
                ref={noteBox}
                aria-label="Nueva nota"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={2000}
                rows={2}
                placeholder="Ej.: prefiere hablar por la tarde"
                className="w-full resize-none rounded-lg border border-line p-2 text-xs outline-none focus:border-primary"
              />
              <button
                disabled={!note.trim()}
                className="mt-1 rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-bold disabled:opacity-40"
              >
                Guardar nota
              </button>
            </form>
          )}
          <ul className="mt-2 space-y-2">
            {detail.notes.map((n) => (
              <li key={n.id} className="rounded-xl bg-amber-50 p-3 text-xs">
                <p className="whitespace-pre-wrap">{n.body}</p>
                <p className="mt-1 flex items-center justify-between text-[10px] text-muted">
                  <span>
                    {n.author_name} · {fullDate(n.at)}
                  </span>
                  {can && (
                    <button
                      type="button"
                      aria-label="Borrar nota"
                      onClick={() => onDeleteNote(n.id)}
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </p>
              </li>
            ))}
          </ul>
        </section>

        {detail.scheduled.length > 0 && (
          <section>
            <p className={label}>Mensajes programados</p>
            <ul className="mt-2 space-y-2">
              {detail.scheduled.map((s) => (
                <li key={s.id} className="rounded-xl border border-line p-3 text-xs">
                  <p className="font-semibold">{fullDate(s.send_at)}</p>
                  <p className="mt-1 line-clamp-2 text-muted">{s.body}</p>
                  <p className="mt-1 flex items-center justify-between text-[10px]">
                    <span
                      className={s.status === "pending" ? "text-amber-700" : "text-emerald-700"}
                    >
                      {s.status === "pending" ? "Pendiente" : "Enviado a la cola"}
                    </span>
                    {s.status === "pending" && can && (
                      <button
                        type="button"
                        onClick={() => onCancelScheduled(s.id)}
                        className="font-bold text-red-600"
                      >
                        Cancelar
                      </button>
                    )}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        )}

        {thread && thread.lives.length > 0 && (
          <section>
            <p className={label}>Capturas en LIVE</p>
            <p className="mt-1 text-[11px] text-muted">
              El primer envío posterior a cada captura, sin atribuir mensajes de otros LIVE.
            </p>
            <div className="mt-2 space-y-2">
              {thread.lives.map((live) => (
                <article
                  key={`${live.live_id}-${live.captured_at}`}
                  className="rounded-xl border border-line p-3 text-xs"
                >
                  <h4 className="font-bold">{live.title || live.live_id}</h4>
                  <p className="text-muted">
                    {live.account_id} · {live.tiktoker_id || "Sin responsable"}
                  </p>
                  <p className="mt-1 text-muted">Captura: {fullDate(live.captured_at)}</p>
                  <p className="mt-1">
                    {live.seconds_to_send === null
                      ? "Sin envío posterior registrado"
                      : `Primer envío posterior: ${Math.round(live.seconds_to_send / 60)} min`}
                  </p>
                  {live.sent_at && (
                    <div className="mt-1 text-[11px] text-muted">
                      <p>
                        {fullDate(live.sent_at)} ·{" "}
                        {live.source === "social_pulse" ? "Social Pulse" : "Otro dispositivo"}
                      </p>
                      <p>Entregado: {fullDate(live.delivered_at)}</p>
                      <p>Leído: {fullDate(live.read_at)}</p>
                      <p>Mensaje recibido después: {fullDate(live.next_inbound_at)}</p>
                    </div>
                  )}
                </article>
              ))}
            </div>
          </section>
        )}
      </div>
    </aside>
  );
}
