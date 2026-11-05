import { useEffect, useState } from "react";
import { Check, Copy, MessageCircle, MousePointerClick, Save } from "lucide-react";
import { api, problemText } from "./api";
import type { WidgetConfig } from "./studio.types";
import { contactLinks, widgetEmbed } from "./widget";
import { Banner, buttonClass, Field, inputClass, Toggle } from "./ui";

const COLORS = ["#0f92ac", "#102b36", "#16a34a", "#7c3aed", "#e11d48", "#f59e0b"];
export function MedicalClic({ canManage }: { canManage: boolean }) {
  const [config, setConfig] = useState<WidgetConfig | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");
  useEffect(() => {
    let active = true;
    api
      .widget()
      .then((c) => {
        if (active) setConfig(c);
      })
      .catch((e) => {
        if (active) setError(problemText(e));
      });
    return () => {
      active = false;
    };
  }, []);
  if (!config)
    return (
      <div className="mt-5">
        {error ? <Banner tone="error">{error}</Banner> : "Cargando MedicalClic…"}
      </div>
    );
  const patch = (next: Partial<WidgetConfig>) => {
    setConfig({ ...config, ...next });
    setCode("");
    setNotice("");
  };
  const save = async (copy: boolean) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = await api.saveWidget(config);
      setConfig(saved);
      const embed = widgetEmbed(saved);
      setCode(embed);
      if (copy) {
        try {
          await navigator.clipboard.writeText(embed);
          setNotice("Configuración guardada y código copiado. Pégalo antes de </body> en tu web.");
        } catch {
          setNotice("Configuración guardada. Copia el código del campo inferior.");
        }
      } else setNotice("Configuración guardada.");
    } catch (e) {
      setError(problemText(e));
    } finally {
      setBusy(false);
    }
  };
  const links = contactLinks(config);
  return (
    <section className="mt-5 overflow-hidden rounded-3xl border border-line bg-white">
      <header className="flex flex-wrap items-center gap-3 p-6">
        <span className="rounded-2xl bg-primary-soft p-3 text-primary">
          <MousePointerClick />
        </span>
        <div>
          <h2 className="text-xl font-bold">MedicalClic</h2>
          <p className="text-sm text-muted">
            Crea un componente de contacto para la web de la clínica.
          </p>
        </div>
        <span className="ml-auto rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">
          Widget web · sin API oficial
        </span>
      </header>
      <div className="px-6 pb-6">
        <p className="mb-3 text-xs font-bold uppercase tracking-widest text-primary">
          Paso 1 · Elige las integraciones
        </p>
        <fieldset
          disabled={!canManage || busy}
          className="overflow-hidden rounded-2xl border border-line disabled:opacity-70"
        >
          {(
            [
              ["whatsapp", "WhatsApp", "Número con país: +51987654321"],
              ["instagram", "Instagram", "Usuario sin @"],
              ["messenger", "Messenger", "Nombre de tu página"],
            ] as const
          ).map(([key, label, placeholder]) => (
            <div
              key={key}
              className="grid items-center gap-3 border-b border-line p-4 last:border-0 sm:grid-cols-[160px_1fr_auto]"
            >
              <strong className="flex items-center gap-2 text-sm">
                <MessageCircle size={18} className="text-primary" />
                {label}
              </strong>
              <input
                aria-label={`Cuenta de ${label}`}
                className={inputClass}
                placeholder={placeholder}
                maxLength={60}
                value={config[key]}
                onChange={(e) => patch({ [key]: e.target.value.trim() })}
              />
              <Toggle
                label={`Mostrar ${label}`}
                checked={config[`${key}_enabled`]}
                onChange={(v) => patch({ [`${key}_enabled`]: v })}
              />
            </div>
          ))}
        </fieldset>
      </div>
      <div className="grid gap-6 border-t border-line bg-slate-50/60 p-6 lg:grid-cols-[1.2fr_1fr]">
        <fieldset disabled={!canManage || busy} className="space-y-5 disabled:opacity-70">
          <p className="text-xs font-bold uppercase tracking-widest text-primary">
            Paso 2 · Configura el estilo
          </p>
          <Field label="Mensaje de acción">
            <input
              className={inputClass}
              maxLength={80}
              value={config.title}
              onChange={(e) => patch({ title: e.target.value })}
            />
          </Field>
          <Field label="Mensaje secundario">
            <input
              className={inputClass}
              maxLength={160}
              value={config.subtitle}
              onChange={(e) => patch({ subtitle: e.target.value })}
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            {(
              [
                ["color", "Color del botón"],
                ["text_color", "Color del texto"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label}>
                <div className="flex flex-wrap gap-2">
                  {(key === "color" ? COLORS : ["#ffffff", "#102b36", "#172554"]).map((color) => (
                    <button
                      key={color}
                      type="button"
                      title={color}
                      aria-label={`${label} ${color}`}
                      aria-pressed={config[key] === color}
                      onClick={() => patch({ [key]: color })}
                      className={`size-8 rounded-full border-4 border-white shadow-sm ${config[key] === color ? "ring-2 ring-primary" : ""}`}
                      style={{ background: color }}
                    />
                  ))}
                </div>
                <input
                  type="color"
                  aria-label={`${label} personalizado`}
                  value={config[key]}
                  onChange={(e) => patch({ [key]: e.target.value })}
                  className="mt-3 h-9 w-full rounded-lg"
                />
              </Field>
            ))}
          </div>
          <Field label="Posición del componente">
            <div className="grid grid-cols-2 gap-2">
              {(["left", "right"] as const).map((position) => (
                <button
                  type="button"
                  key={position}
                  aria-pressed={config.position === position}
                  onClick={() => patch({ position })}
                  className={`rounded-xl p-3 text-sm ${config.position === position ? "bg-primary text-white" : "bg-white text-muted"}`}
                >
                  {position === "left" ? "Izquierda" : "Derecha"}
                </button>
              ))}
            </div>
          </Field>
        </fieldset>
        <div className="space-y-3">
          <p className="text-xs font-bold uppercase tracking-widest text-primary">Vista previa</p>
          <div
            className={`flex min-h-72 items-end rounded-2xl border border-line bg-slate-100 p-5 ${config.position === "right" ? "justify-end" : "justify-start"}`}
          >
            <div
              className="max-w-full rounded-2xl p-4 shadow-lg"
              style={{ background: config.color, color: config.text_color }}
            >
              <strong>{config.title}</strong>
              <p className="mt-1 text-xs">{config.subtitle}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {links.map((link) => (
                  <a
                    key={link.label}
                    href={link.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded-full border border-current px-3 py-1 text-xs"
                  >
                    {link.label}
                  </a>
                ))}
              </div>
            </div>
          </div>
          {!links.length && (
            <p className="text-xs text-muted">
              Completa y habilita al menos una cuenta para mostrar sus enlaces.
            </p>
          )}
          <p className="rounded-2xl bg-deep p-4 text-xs text-cyan-100">
            Abre el canal elegido. No envía mensajes ni recoge datos del paciente. El código incluye
            el diseño guardado; vuelve a copiarlo si lo cambias.
          </p>
          {canManage && (
            <div className="flex gap-2">
              <button
                disabled={busy || !config.title.trim() || !links.length}
                onClick={() => void save(true)}
                className={`${buttonClass} flex-1`}
              >
                <Copy size={15} className="mr-2 inline" />
                Copiar y guardar
              </button>
              <button
                aria-label="Guardar configuración"
                disabled={busy}
                onClick={() => void save(false)}
                className={buttonClass}
              >
                <Save size={16} />
              </button>
            </div>
          )}
        </div>
      </div>
      <div className="space-y-3 px-6 pb-6">
        {error && <Banner tone="error">{error}</Banner>}
        {notice && (
          <Banner tone="ok">
            <Check size={14} className="mr-1 inline" />
            {notice}
          </Banner>
        )}
        {code && (
          <Field label="Código para insertar en tu web">
            <textarea
              readOnly
              value={code}
              onFocus={(e) => e.target.select()}
              className={`${inputClass} h-32 font-mono text-xs`}
            />
          </Field>
        )}
      </div>
    </section>
  );
}
