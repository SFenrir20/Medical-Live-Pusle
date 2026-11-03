import { useCallback, useEffect, useState } from "react";
import { AiConfig, AiAnswer, api, KnowledgeDoc, Overview, problemText } from "./api";
import { Banner, buttonClass, Field, ghostButtonClass, inputClass, Section, Toggle } from "./ui";

const PROVIDERS: Record<string, { name: string; text: string }> = {
  echo: {
    name: "Sin proveedor (simulación)",
    text: "No llama a ninguna IA: sirve para probar flujos, traspasos y límites sin gastar ni enviar datos a nadie.",
  },
  anthropic: {
    name: "Anthropic (Claude)",
    text: "Pagas por uso con tu propia cuenta de Anthropic. Modelos pequeños son rápidos y baratos para chat.",
  },
  openai: {
    name: "OpenAI",
    text: "Pagas por uso con tu propia cuenta de OpenAI. Indica el nombre exacto del modelo.",
  },
  openai_compatible: {
    name: "Otro servidor compatible con OpenAI",
    text: "Para Gemini (su modo compatible), Groq, o un modelo propio en tu servidor (Ollama, vLLM). Indica la dirección del servidor, y si es tuyo, tus datos no salen de tu infraestructura.",
  },
};

const emptyDoc = { title: "", body: "" };

export function AiTab({ overview, canManage }: { overview: Overview; canManage: boolean }) {
  const [config, setConfig] = useState<AiConfig | null>(null);
  const [draft, setDraft] = useState<AiConfig | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [keywords, setKeywords] = useState("");
  const [notice, setNotice] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [newDoc, setNewDoc] = useState(emptyDoc);
  const [chat, setChat] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [input, setInput] = useState("");
  const [answer, setAnswer] = useState<AiAnswer | null>(null);
  const [usage, setUsage] = useState<
    { day: string; messages: number; input_tokens: number; output_tokens: number }[]
  >([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, d, u] = await Promise.all([api.ai(), api.knowledge(), api.usage()]);
      setConfig(c);
      setDraft(c);
      setKeywords(c.handoff_keywords.join(", "));
      setDocs(d);
      setUsage(u);
    } catch (e) {
      setNotice({ tone: "error", text: problemText(e) });
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  if (!config || !draft) return <p className="mt-6 text-sm text-muted">Cargando…</p>;
  const set = <K extends keyof AiConfig>(key: K, value: AiConfig[K]) =>
    setDraft({ ...draft, [key]: value });

  const save = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const saved = await api.saveAi({
        enabled: draft.enabled,
        provider: draft.provider,
        model: draft.model,
        base_url: draft.base_url,
        name: draft.name,
        clinic_name: draft.clinic_name,
        instructions: draft.instructions,
        knowledge_only: draft.knowledge_only,
        handoff_message: draft.handoff_message,
        max_replies: draft.max_replies,
        daily_message_cap: draft.daily_message_cap,
        handoff_keywords: keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean),
        api_key: apiKey,
        clear_key: clearKey,
      });
      setConfig(saved);
      setDraft(saved);
      setApiKey("");
      setClearKey(false);
      setNotice({ tone: "ok", text: "Configuración guardada." });
    } catch (e) {
      setNotice({ tone: "error", text: problemText(e) });
    } finally {
      setBusy(false);
    }
  };

  const addDoc = async () => {
    try {
      await api.addKnowledge(newDoc);
      setNewDoc(emptyDoc);
      setDocs(await api.knowledge());
    } catch (e) {
      setNotice({ tone: "error", text: problemText(e) });
    }
  };

  const toggleDoc = async (doc: KnowledgeDoc) => {
    await api.editKnowledge(doc.id, { title: doc.title, body: doc.body, active: !doc.active });
    setDocs(await api.knowledge());
  };

  const removeDoc = async (doc: KnowledgeDoc) => {
    if (!window.confirm(`¿Borrar «${doc.title}»?`)) return;
    await api.deleteKnowledge(doc.id);
    setDocs(await api.knowledge());
  };

  const ask = async () => {
    const next = [...chat, { role: "user" as const, content: input.trim() }];
    setChat(next);
    setInput("");
    setBusy(true);
    try {
      const result = await api.playground(next);
      setAnswer(result);
      setChat([...next, { role: "assistant", content: result.text ?? "(sin respuesta)" }]);
    } catch (e) {
      setNotice({ tone: "error", text: problemText(e) });
    } finally {
      setBusy(false);
    }
  };

  const provider = PROVIDERS[draft.provider];
  return (
    <>
      <Section
        title="Agente de IA"
        help="Contesta con la información que tú cargas y pasa a una persona cuando hace falta. No se usa en ningún chat hasta que lo actives aquí y pongas un paso «Responde la IA» en un flujo activo."
      >
        <div className="grid gap-4 md:grid-cols-2">
          <Banner tone="info">
            <strong>Reglas fijas, que ni el paciente ni tus instrucciones pueden quitar:</strong>
            <ul className="mt-1 list-disc pl-5">
              <li>Es un asistente virtual: no diagnostica ni recomienda tratamientos.</li>
              <li>Ante síntomas, dolor, urgencias o quejas, pasa a una persona.</li>
              <li>Solo afirma lo que está en la información cargada; si no, pasa a una persona.</li>
              <li>Tope de respuestas seguidas y tope diario.</li>
            </ul>
          </Banner>
          <Banner tone="warn">
            La clave del proveedor la pones tú, se guarda <strong>cifrada en tu servidor</strong> y
            no vuelve a mostrarse. Con un proveedor real, cada respuesta envía esa conversación y la
            información cargada a ese proveedor: revisa sus condiciones sobre datos de salud antes
            de usarlo con pacientes.
          </Banner>
        </div>

        <div className="mt-5 rounded-2xl border border-line bg-white p-5">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                <strong className="text-sm">Agente activo</strong>
                <Toggle
                  checked={draft.enabled}
                  onChange={(v) => set("enabled", v)}
                  disabled={!canManage}
                  label="Agente activo"
                />
              </div>
              <Field label="Proveedor de IA">
                <select
                  className={inputClass}
                  value={draft.provider}
                  onChange={(e) => set("provider", e.target.value)}
                  disabled={!canManage}
                >
                  {overview.providers.map((p) => (
                    <option key={p} value={p}>
                      {PROVIDERS[p]?.name ?? p}
                    </option>
                  ))}
                </select>
              </Field>
              <p className="rounded-xl bg-slate-50 p-3 text-xs text-muted">{provider?.text}</p>
              {draft.provider !== "echo" && (
                <>
                  <Field
                    label="Modelo"
                    hint={
                      overview.suggested_models[draft.provider]
                        ? `sugerido: ${overview.suggested_models[draft.provider]}`
                        : "nombre exacto del modelo"
                    }
                  >
                    <input
                      className={inputClass}
                      value={draft.model}
                      onChange={(e) => set("model", e.target.value)}
                      disabled={!canManage}
                    />
                  </Field>
                  {draft.provider === "openai_compatible" && (
                    <Field label="Dirección del servidor" hint="p. ej. https://mi-servidor/v1">
                      <input
                        className={inputClass}
                        value={draft.base_url}
                        onChange={(e) => set("base_url", e.target.value)}
                        disabled={!canManage}
                      />
                    </Field>
                  )}
                  <Field
                    label="Clave de API"
                    hint={
                      draft.has_key
                        ? `guardada ${draft.key_hint ?? ""}`
                        : "todavía no hay una guardada"
                    }
                  >
                    <input
                      type="password"
                      autoComplete="off"
                      className={inputClass}
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder={
                        draft.has_key ? "Déjalo vacío para conservarla" : "pega aquí la clave"
                      }
                      disabled={!canManage}
                    />
                  </Field>
                  {draft.has_key && canManage && (
                    <label className="flex items-center gap-2 text-xs text-muted">
                      <input
                        type="checkbox"
                        checked={clearKey}
                        onChange={(e) => setClearKey(e.target.checked)}
                      />{" "}
                      Borrar la clave guardada
                    </label>
                  )}
                </>
              )}
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Nombre del asistente">
                  <input
                    className={inputClass}
                    value={draft.name}
                    onChange={(e) => set("name", e.target.value)}
                    disabled={!canManage}
                  />
                </Field>
                <Field label="Nombre de la clínica">
                  <input
                    className={inputClass}
                    value={draft.clinic_name}
                    onChange={(e) => set("clinic_name", e.target.value)}
                    disabled={!canManage}
                  />
                </Field>
              </div>
              <Field label="Instrucciones y tono" hint="opcional">
                <textarea
                  className={`${inputClass} h-24`}
                  value={draft.instructions}
                  onChange={(e) => set("instructions", e.target.value)}
                  disabled={!canManage}
                  placeholder="Habla de tú, sé cálida y breve…"
                />
              </Field>
              <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                <div>
                  <strong className="text-sm">Responder solo con lo cargado</strong>
                  <p className="text-[11px] text-muted">
                    Sin información relevante, pasa a una persona en vez de inventar.
                  </p>
                </div>
                <Toggle
                  checked={draft.knowledge_only}
                  onChange={(v) => set("knowledge_only", v)}
                  disabled={!canManage}
                  label="Solo conocimiento"
                />
              </div>
              <Field label="Palabras que pasan a una persona" hint="separadas por coma">
                <textarea
                  className={`${inputClass} h-16`}
                  value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                  disabled={!canManage}
                />
              </Field>
              <Field label="Mensaje al pasar a una persona">
                <input
                  className={inputClass}
                  value={draft.handoff_message}
                  onChange={(e) => set("handoff_message", e.target.value)}
                  disabled={!canManage}
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Respuestas seguidas (máx.)">
                  <input
                    type="number"
                    min={1}
                    max={50}
                    className={inputClass}
                    value={draft.max_replies}
                    onChange={(e) => set("max_replies", Number(e.target.value))}
                    disabled={!canManage}
                  />
                </Field>
                <Field label="Respuestas por día (máx.)">
                  <input
                    type="number"
                    min={1}
                    className={inputClass}
                    value={draft.daily_message_cap}
                    onChange={(e) => set("daily_message_cap", Number(e.target.value))}
                    disabled={!canManage}
                  />
                </Field>
              </div>
            </div>
          </div>
          {notice && (
            <div className="mt-4">
              <Banner tone={notice.tone}>{notice.text}</Banner>
            </div>
          )}
          {canManage && (
            <button
              type="button"
              className={`${buttonClass} mt-4`}
              disabled={busy}
              onClick={() => void save()}
            >
              Guardar configuración
            </button>
          )}
        </div>
      </Section>

      <Section
        title="Información de la clínica"
        help="Lo único que el agente puede afirmar: horarios, sedes, precios autorizados, preguntas frecuentes. Separa los temas con una línea en blanco."
      >
        <div className="space-y-3">
          {docs.map((doc) => (
            <article key={doc.id} className="rounded-2xl border border-line bg-white p-4">
              <div className="flex items-center gap-3">
                <strong className="text-sm">{doc.title}</strong>
                <span className="ml-auto flex items-center gap-2 text-xs text-muted">
                  {doc.active ? "Activo" : "Oculto"}
                  <Toggle
                    checked={doc.active}
                    onChange={() => void toggleDoc(doc)}
                    disabled={!canManage}
                    label={`Usar ${doc.title}`}
                  />
                </span>
                {canManage && (
                  <button
                    type="button"
                    className="text-xs font-semibold text-red-600"
                    onClick={() => void removeDoc(doc)}
                  >
                    Borrar
                  </button>
                )}
              </div>
              <p className="mt-2 whitespace-pre-line text-xs text-muted">
                {doc.body.slice(0, 400)}
                {doc.body.length > 400 ? "…" : ""}
              </p>
            </article>
          ))}
          {!docs.length && (
            <p className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-sm text-muted">
              Todavía no hay información. Sin ella, con «Responder solo con lo cargado», el agente
              siempre pasa a una persona.
            </p>
          )}
          {canManage && (
            <div className="rounded-2xl border border-line bg-white p-4">
              <div className="grid gap-3 md:grid-cols-[220px_1fr]">
                <Field label="Título">
                  <input
                    className={inputClass}
                    value={newDoc.title}
                    onChange={(e) => setNewDoc({ ...newDoc, title: e.target.value })}
                    placeholder="Horarios y sedes"
                  />
                </Field>
                <Field label="Contenido">
                  <textarea
                    className={`${inputClass} h-24`}
                    value={newDoc.body}
                    onChange={(e) => setNewDoc({ ...newDoc, body: e.target.value })}
                  />
                </Field>
              </div>
              <button
                type="button"
                className={`${ghostButtonClass} mt-3`}
                disabled={!newDoc.title.trim() || !newDoc.body.trim()}
                onClick={() => void addDoc()}
              >
                Agregar información
              </button>
            </div>
          )}
        </div>
      </Section>

      {canManage && (
        <Section
          title="Probar al agente"
          help="Escribe como si fueras la paciente. No se envía nada a nadie y no cuenta para el tope diario; si hay un proveedor real, sí consume tokens."
        >
          <div className="rounded-2xl border border-line bg-white p-4">
            <div className="max-h-72 space-y-2 overflow-y-auto">
              {chat.map((m, i) => (
                <p
                  key={i}
                  className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${m.role === "user" ? "ml-auto bg-primary-soft" : "bg-emerald-50 text-emerald-900"}`}
                >
                  {m.content}
                </p>
              ))}
              {!chat.length && (
                <p className="text-sm text-muted">
                  Prueba con «¿a qué hora atienden?» o «tengo mucho dolor».
                </p>
              )}
            </div>
            {answer?.handoff && (
              <p className="mt-3 text-xs font-semibold text-amber-700">
                Pasaría a una persona ({answer.reason}).
              </p>
            )}
            <div className="mt-3 flex gap-2">
              <input
                className={inputClass}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && input.trim() && !busy) void ask();
                }}
                placeholder="Escribe como la paciente"
              />
              <button
                type="button"
                className={buttonClass}
                disabled={busy || !input.trim()}
                onClick={() => void ask()}
              >
                Enviar
              </button>
              <button
                type="button"
                className={ghostButtonClass}
                onClick={() => {
                  setChat([]);
                  setAnswer(null);
                }}
              >
                Limpiar
              </button>
            </div>
          </div>
        </Section>
      )}

      <Section title="Uso" help="Respuestas reales de la IA por día (la prueba no cuenta).">
        <div className="overflow-x-auto rounded-2xl border border-line bg-white">
          <table className="w-full text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-3">Día</th>
                <th className="px-2 py-3">Respuestas</th>
                <th className="px-2 py-3">Tokens de entrada</th>
                <th className="px-2 py-3">Tokens de salida</th>
              </tr>
            </thead>
            <tbody>
              {usage.map((u) => (
                <tr key={u.day} className="border-t border-line">
                  <td className="px-4 py-2">{u.day}</td>
                  <td className="px-2 py-2">{u.messages}</td>
                  <td className="px-2 py-2">{u.input_tokens.toLocaleString("es-PE")}</td>
                  <td className="px-2 py-2">{u.output_tokens.toLocaleString("es-PE")}</td>
                </tr>
              ))}
              {!usage.length && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-sm text-muted">
                    Sin uso todavía.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>
    </>
  );
}
