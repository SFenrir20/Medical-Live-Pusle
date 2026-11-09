import { useEffect, useState } from "react";
import { Clock3, MessageCircle, Play, Save } from "lucide-react";
import { api, problemText, TestResult } from "./api";
import type { MessagePreset } from "./studio.types";
import { Banner, buttonClass, Field, inputClass, Toggle } from "./ui";

const TITLES = [
  "Mensaje de bienvenida",
  "Mensaje para leads pregrabados",
  "Recordatorio de cita",
  "Seguimiento posterior",
];
const DEFAULTS: MessagePreset[] = [
  {
    key: "welcome",
    text: "¡Hola! Gracias por contactar a Medical. Tu mensaje es muy importante para nosotros. Te atenderemos en unos segundos.",
    enabled: true,
    delay_minutes: 0,
  },
  {
    key: "lead",
    text: "Hola {{nombre|}}, gracias por tu interés. ¿En qué servicio podemos orientarte?",
    enabled: true,
    delay_minutes: 0,
  },
  {
    key: "appointment",
    text: "Hola {{nombre|}}, te escribimos para recordar tu cita. Confirma el día y la hora con tu asesora.",
    enabled: true,
    delay_minutes: 0,
  },
  {
    key: "followup",
    text: "Hola {{nombre|}}, ¿pudiste revisar la información? Estamos aquí para ayudarte.",
    enabled: true,
    delay_minutes: 60,
  },
];

export function PresetMessages({ canManage }: { canManage: boolean }) {
  const [items, setItems] = useState(DEFAULTS);
  const [selected, setSelected] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [result, setResult] = useState<TestResult | null>(null);
  useEffect(() => {
    let current = true;
    api
      .presets()
      .then((value) => {
        if (current) {
          if (value.items.length)
            setItems(DEFAULTS.map((d) => value.items.find((i) => i.key === d.key) ?? d));
          setLoaded(true);
        }
      })
      .catch((e) => {
        if (current) setError(problemText(e));
      });
    return () => {
      current = false;
    };
  }, []);
  const item = items[selected];
  const patch = (value: Partial<MessagePreset>) => {
    setItems((old) => old.map((p, i) => (i === selected ? { ...p, ...value } : p)));
    setNotice("");
    setResult(null);
  };
  const save = async (test: boolean) => {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const saved = await api.savePresets(items);
      setItems(saved.items);
      if (test) {
        const flow = saved.items.find((p) => p.key === item.key);
        if (flow?.flow_id) setResult(await api.testFlow(flow.flow_id, "Hola, quiero información"));
      }
      setNotice(
        test
          ? "Prueba terminada en el simulador; no se enviaron mensajes reales."
          : "Mensajes guardados como borradores de flujo en el simulador.",
      );
    } catch (e) {
      setError(problemText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="mt-5 overflow-hidden rounded-3xl border border-line bg-white">
      <header className="flex flex-wrap items-center justify-between gap-4 p-6">
        <div>
          <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-primary">
            <Clock3 size={15} />
            Mensajes por etapa
          </p>
          <h2 className="mt-2 text-xl font-bold">Respuestas pregrabadas</h2>
          <p className="mt-1 text-sm text-muted">
            Define, guarda y prueba el mensaje de cada momento del recorrido.
          </p>
        </div>
        {canManage && (
          <button
            disabled={busy || !loaded || items.some((i) => !i.text.trim())}
            onClick={() => void save(false)}
            className={buttonClass}
          >
            <Save size={15} className="mr-2 inline" />
            Guardar mensajes
          </button>
        )}
      </header>
      <div
        className="grid gap-2 px-6 pb-6 sm:grid-cols-2 xl:grid-cols-4"
        role="tablist"
        aria-label="Etapas del mensaje"
      >
        {TITLES.map((title, index) => (
          <button
            role="tab"
            aria-selected={selected === index}
            disabled={busy}
            key={title}
            onClick={() => {
              setSelected(index);
              setResult(null);
            }}
            className={`rounded-xl border p-5 text-left text-xs font-semibold ${selected === index ? "border-primary bg-primary-soft text-primary" : "border-line text-ink"}`}
          >
            {String(index + 1).padStart(2, "0")} · {title}
          </button>
        ))}
      </div>
      <div className="grid gap-5 border-t border-line bg-slate-50/60 p-6 lg:grid-cols-[1.2fr_1fr]">
        <fieldset
          disabled={!canManage || busy || !loaded}
          className="space-y-5 rounded-2xl border border-line bg-white p-5 disabled:opacity-70"
        >
          <div className="flex justify-between gap-3">
            <div>
              <h3 className="font-bold">{TITLES[selected]}</h3>
              <p className="mt-1 text-xs text-muted">
                Incluye este mensaje en su borrador de flujo.
              </p>
            </div>
            <Toggle
              label="Incluir mensaje"
              checked={item.enabled}
              onChange={(enabled) => patch({ enabled })}
            />
          </div>
          <Field label="Redacta el mensaje">
            <textarea
              className={`${inputClass} h-44 resize-y`}
              maxLength={500}
              value={item.text}
              onChange={(e) => patch({ text: e.target.value })}
            />
            <p className="mt-1 text-right text-xs text-muted">{item.text.length}/500 caracteres</p>
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Esperar después del disparador">
              <select
                className={inputClass}
                value={item.delay_minutes}
                onChange={(e) => patch({ delay_minutes: Number(e.target.value) })}
              >
                {[
                  [0, "Inmediatamente"],
                  [5, "5 minutos"],
                  [30, "30 minutos"],
                  [60, "1 hora"],
                  [1440, "24 horas"],
                ].map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Canal de prueba">
              <input readOnly className={inputClass} value="Simulador" />
            </Field>
          </div>
          <p className="text-xs leading-5 text-muted">
            {item.key === "welcome"
              ? "El borrador empieza con un mensaje entrante."
              : "Este borrador usa un disparador manual. No está conectado a citas ni cambios de etapa."}{" "}
            Guardar no activa envíos. Puedes editar y activar el flujo desde MedicalBot.
          </p>
          {canManage && (
            <button
              type="button"
              className={buttonClass}
              disabled={busy || !item.text.trim()}
              onClick={() => void save(true)}
            >
              <Play size={14} className="mr-2 inline" />
              Guardar y probar
            </button>
          )}
        </fieldset>
        <div className="overflow-hidden rounded-2xl border border-line bg-[#f3f0e9]">
          <p className="flex items-center gap-2 border-b border-line bg-white px-5 py-3 text-sm font-bold">
            <MessageCircle size={16} className="text-emerald-600" />
            Vista previa · ejemplo
          </p>
          <div
            className="min-h-80 space-y-5 p-5"
            style={{
              backgroundImage: "radial-gradient(#0f92ac22 1px, transparent 1px)",
              backgroundSize: "20px 20px",
            }}
          >
            <p className="mr-10 rounded-2xl rounded-tl-none bg-white p-4 text-sm shadow-sm">
              Hola, vi su anuncio y quisiera información.
            </p>
            <p className="ml-10 whitespace-pre-wrap rounded-2xl rounded-tr-none bg-[#d9fdd3] p-4 text-sm shadow-sm">
              {item.enabled ? item.text : "Este mensaje no está incluido en el borrador."}
            </p>
            {result && (
              <div className="rounded-xl bg-white/90 p-4 text-xs">
                <strong>Resultado de la prueba: {result.status}</strong>
                {result.messages.map((m, i) => (
                  <p key={i} className="mt-2 whitespace-pre-wrap">
                    {m.body}
                  </p>
                ))}
                {result.reason && <p>{result.reason}</p>}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="space-y-2 px-6 pb-5">
        {error && <Banner tone="error">{error}</Banner>}
        {notice && <Banner tone="ok">{notice}</Banner>}
      </div>
    </section>
  );
}
