import { useCallback, useEffect, useRef, useState } from "react";
import { api, ChatMessage, Conversation, problemText } from "./api";
import { Banner, buttonClass, Field, ghostButtonClass, inputClass, Section, when } from "./ui";

const AUTHOR: Record<ChatMessage["author_kind"], { label: string; style: string }> = {
  contact: { label: "Paciente", style: "mr-auto bg-white" },
  bot: { label: "Bot", style: "ml-auto bg-emerald-100" },
  agent: { label: "Persona", style: "ml-auto bg-sky-100" },
  system: { label: "Sistema", style: "mx-auto bg-amber-50" },
};

/** A pretend patient writes on the simulator channel; whatever is enabled there reacts exactly as
 *  it would on a real channel. The place to see flows and the AI agent working end to end. */
export function SimulatorTab({ canManage }: { canManage: boolean }) {
  const [phone, setPhone] = useState("+51987654321");
  const [name, setName] = useState("Camila");
  const [text, setText] = useState("");
  const [asPerson, setAsPerson] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await api.conversations("simulador");
      setConversations(list);
      if (current) {
        const data = await api.messages(current.id);
        setCurrent(data.conversation);
        setMessages(data.messages);
      }
    } catch (e) {
      setError(problemText(e));
    }
  }, [current]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [messages.length]);

  const open = async (conversation: Conversation) => {
    setCurrent(conversation);
    setPhone(conversation.phone);
    setName(conversation.name ?? "");
    setMessages((await api.messages(conversation.id)).messages);
  };

  const send = async () => {
    const value = text.trim();
    if (!value) return;
    setText("");
    setError("");
    try {
      if (asPerson && current) {
        await api.writeAsPerson(current.id, value);
        setMessages((await api.messages(current.id)).messages);
      } else {
        const result = await api.simulate(phone, value, name || undefined);
        setCurrent(result.conversation);
        setMessages(result.messages);
      }
      setConversations(await api.conversations("simulador"));
    } catch (e) {
      setError(problemText(e));
    }
  };

  if (!canManage)
    return (
      <Section
        title="Simulador"
        help="Solo un administrador puede usar el simulador (muestra conversaciones de prueba)."
      >
        <Banner tone="info">
          Tu rol puede ver los flujos y sus resultados, pero no las conversaciones.
        </Banner>
      </Section>
    );

  return (
    <Section
      title="Simulador"
      help="Escribe como una paciente en un canal de pruebas: no sale nada a ningún WhatsApp real. Los flujos activos de ese canal y el agente de IA responden igual que lo harían en uno real."
    >
      {error && (
        <div className="mb-4">
          <Banner tone="error">{error}</Banner>
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="rounded-2xl border border-line bg-white p-3">
          <button
            type="button"
            className={`${ghostButtonClass} w-full`}
            onClick={() => {
              setCurrent(null);
              setMessages([]);
              setAsPerson(false);
            }}
          >
            + Nueva conversación
          </button>
          <div className="mt-3 space-y-1">
            {conversations.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => void open(c)}
                className={`w-full rounded-xl p-2.5 text-left text-sm ${current?.id === c.id ? "bg-primary-soft" : "hover:bg-slate-50"}`}
              >
                <strong>{c.name || c.phone}</strong>
                <span className="block truncate text-xs text-muted">{c.last?.body ?? "—"}</span>
                {!c.bot_active && (
                  <span className="text-[10px] font-bold text-amber-700">bot en pausa</span>
                )}
              </button>
            ))}
            {!conversations.length && (
              <p className="p-2 text-xs text-muted">Sin conversaciones todavía.</p>
            )}
          </div>
        </aside>
        <div className="rounded-2xl border border-line bg-white p-4">
          {!current && (
            <div className="mb-3 grid grid-cols-2 gap-3">
              <Field label="Teléfono de la paciente">
                <input
                  className={inputClass}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
              </Field>
              <Field label="Nombre">
                <input
                  className={inputClass}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </Field>
            </div>
          )}
          {current && (
            <div className="mb-3 flex flex-wrap items-center gap-3 border-b border-line pb-3">
              <strong>{current.name || current.phone}</strong>
              <span className="text-xs text-muted">{current.phone}</span>
              {current.tags.map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-primary-soft px-2 py-0.5 text-[10px] font-bold text-primary"
                >
                  {t}
                </span>
              ))}
              <button
                type="button"
                className={`${ghostButtonClass} ml-auto`}
                onClick={async () =>
                  setCurrent(
                    await api.patchConversation(current.id, { bot_active: !current.bot_active }),
                  )
                }
              >
                {current.bot_active ? "Pausar al bot aquí" : "Devolver al bot"}
              </button>
            </div>
          )}
          <div className="h-80 space-y-2 overflow-y-auto rounded-xl bg-[#efeae2] p-3">
            {messages.map((m) => (
              <p
                key={m.id}
                className={`max-w-[75%] rounded-xl px-3 py-2 text-sm shadow-sm ${AUTHOR[m.author_kind].style} ${m.status === "blocked" ? "opacity-60" : ""}`}
              >
                <span className="block text-[10px] font-bold text-slate-500">
                  {AUTHOR[m.author_kind].label} · {when(m.at)}
                  {m.status === "blocked" ? ` · bloqueado (${m.error})` : ""}
                </span>
                {m.body}
              </p>
            ))}
            {!messages.length && (
              <p className="text-center text-xs text-slate-500">Escribe un mensaje para empezar.</p>
            )}
            <div ref={end} />
          </div>
          <div className="mt-3 flex items-center gap-2">
            <input
              className={inputClass}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void send();
              }}
              placeholder={
                asPerson ? "Responder como persona del equipo" : "Escribe como la paciente"
              }
            />
            <button
              type="button"
              className={buttonClass}
              onClick={() => void send()}
              disabled={!text.trim()}
            >
              Enviar
            </button>
          </div>
          {current && (
            <label className="mt-2 flex items-center gap-2 text-xs text-muted">
              <input
                type="checkbox"
                checked={asPerson}
                onChange={(e) => setAsPerson(e.target.checked)}
              />
              Escribir como persona del equipo (el bot se calla en esta conversación)
            </label>
          )}
        </div>
      </div>
    </Section>
  );
}
