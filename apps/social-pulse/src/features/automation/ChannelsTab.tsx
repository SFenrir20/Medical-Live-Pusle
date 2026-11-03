import { useState } from "react";
import { api, Channel, ChannelPolicy, problemText } from "./api";
import { Banner, buttonClass, Field, ghostButtonClass, inputClass, Section, Toggle } from "./ui";

const KIND_LABEL: Record<Channel["kind"], string> = {
  simulator: "Simulador",
  whatsapp_mirror: "Espejo de WhatsApp (no oficial)",
  whatsapp_cloud: "WhatsApp API oficial",
};

function ChannelCard({
  channel,
  canManage,
  onChanged,
}: {
  channel: Channel;
  canManage: boolean;
  onChanged: () => void;
}) {
  const [draft, setDraft] = useState<ChannelPolicy>(channel.policy);
  const [numbers, setNumbers] = useState(channel.policy.test_numbers.join("\n"));
  const [accepted, setAccepted] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const turningOnRisk =
    channel.risky_automation &&
    ((draft.bots_enabled && !channel.policy.bots_enabled) ||
      (draft.broadcasts_enabled && !channel.policy.broadcasts_enabled));

  const save = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await api.patchChannel(channel.id, {
        policy: {
          ...draft,
          test_numbers: numbers
            .split(/[\n,]/)
            .map((n) => n.trim())
            .filter(Boolean),
        },
        acknowledge_risk: accepted,
      });
      setAccepted(false);
      setMessage({ tone: "ok", text: "Política guardada." });
      onChanged();
    } catch (error) {
      setMessage({ tone: "error", text: problemText(error) });
    } finally {
      setBusy(false);
    }
  };

  const toggleStatus = async () => {
    setBusy(true);
    try {
      await api.patchChannel(channel.id, {
        status: channel.status === "active" ? "disabled" : "active",
      });
      onChanged();
    } catch (error) {
      setMessage({ tone: "error", text: problemText(error) });
    } finally {
      setBusy(false);
    }
  };

  const set = <K extends keyof ChannelPolicy>(key: K, value: ChannelPolicy[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  return (
    <article className="rounded-2xl border border-line bg-white p-5">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="font-bold">{channel.name}</h3>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-600">
          {KIND_LABEL[channel.kind]}
        </span>
        <span className="font-mono text-[11px] text-muted">{channel.id}</span>
        <span className="ml-auto flex items-center gap-2 text-xs font-semibold text-muted">
          {channel.status === "active" ? "Activo" : "Deshabilitado"}
          <Toggle
            checked={channel.status === "active"}
            onChange={() => void toggleStatus()}
            disabled={!canManage || busy}
            label="Canal activo"
          />
        </span>
      </div>

      {channel.risky_automation && (
        <div className="mt-4">
          <Banner tone="warn">
            Este canal no es el oficial de WhatsApp. Los bots y los mensajes masivos pueden hacer
            que restrinjan o bloqueen el número. Por eso están apagados y, al encenderlos, solo
            llegan a la lista de números de prueba.
          </Banner>
        </div>
      )}
      {channel.kind === "whatsapp_mirror" && (
        <p className="mt-3 text-xs text-muted">
          El espejo todavía no está vinculado a un teléfono: aunque lo configures, no se enviará
          nada hasta que se conecte.
        </p>
      )}

      <div className="mt-5 grid gap-5 md:grid-cols-2">
        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
            <div>
              <strong className="text-sm">Bots (flujos y agente de IA)</strong>
              <p className="text-[11px] text-muted">Respuestas automáticas a quien escribe.</p>
            </div>
            <Toggle
              checked={draft.bots_enabled}
              onChange={(v) => set("bots_enabled", v)}
              disabled={!canManage}
              label="Bots"
            />
          </div>
          <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
            <div>
              <strong className="text-sm">Difusiones (mensajes masivos)</strong>
              <p className="text-[11px] text-muted">Envíos a una lista de contactos.</p>
            </div>
            <Toggle
              checked={draft.broadcasts_enabled}
              onChange={(v) => set("broadcasts_enabled", v)}
              disabled={!canManage}
              label="Difusiones"
            />
          </div>
          <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
            <div>
              <strong className="text-sm">Solo números de prueba</strong>
              <p className="text-[11px] text-muted">
                Lo automático solo llega a la lista de la derecha.
              </p>
            </div>
            <Toggle
              checked={draft.test_only}
              onChange={(v) => set("test_only", v)}
              disabled={!canManage}
              label="Solo pruebas"
            />
          </div>
        </div>
        <div className="space-y-4">
          <Field label="Números de prueba" hint="uno por línea, con +51">
            <textarea
              className={`${inputClass} h-24 font-mono`}
              value={numbers}
              onChange={(e) => setNumbers(e.target.value)}
              disabled={!canManage}
              placeholder="+51987654321"
            />
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Bot por hora">
              <input
                type="number"
                min={0}
                className={inputClass}
                value={draft.bot_max_per_hour}
                onChange={(e) => set("bot_max_per_hour", Number(e.target.value))}
                disabled={!canManage}
              />
            </Field>
            <Field label="Difusión por día">
              <input
                type="number"
                min={0}
                className={inputClass}
                value={draft.broadcast_max_per_day}
                onChange={(e) => set("broadcast_max_per_day", Number(e.target.value))}
                disabled={!canManage}
              />
            </Field>
            <Field label="Pausa (s)">
              <input
                type="number"
                min={0}
                className={inputClass}
                value={draft.min_delay_s}
                onChange={(e) => set("min_delay_s", Number(e.target.value))}
                disabled={!canManage}
              />
            </Field>
          </div>
        </div>
      </div>

      {turningOnRisk && canManage && (
        <label className="mt-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <input
            type="checkbox"
            className="mt-1"
            checked={accepted}
            onChange={(e) => setAccepted(e.target.checked)}
          />
          <span>
            Entiendo que encender esto en un canal no oficial puede hacer que restrinjan o bloqueen
            el número de WhatsApp, y quiero hacerlo igualmente.
          </span>
        </label>
      )}
      {message && (
        <div className="mt-4">
          <Banner tone={message.tone}>{message.text}</Banner>
        </div>
      )}
      {canManage && (
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            className={buttonClass}
            disabled={busy || (turningOnRisk && !accepted)}
            onClick={() => void save()}
          >
            Guardar política
          </button>
          <button
            type="button"
            className={ghostButtonClass}
            onClick={() => {
              setDraft(channel.defaults);
              setNumbers(channel.defaults.test_numbers.join("\n"));
            }}
          >
            Volver a lo seguro
          </button>
        </div>
      )}
    </article>
  );
}

export function ChannelsTab({
  channels,
  canManage,
  onChanged,
}: {
  channels: Channel[];
  canManage: boolean;
  onChanged: () => void;
}) {
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    id: "",
    name: "",
    kind: "whatsapp_mirror" as Channel["kind"],
  });
  const [error, setError] = useState("");

  const create = async () => {
    setError("");
    try {
      await api.createChannel(form);
      setCreating(false);
      setForm({ id: "", name: "", kind: "whatsapp_mirror" });
      onChanged();
    } catch (e) {
      setError(problemText(e));
    }
  };

  return (
    <Section
      title="Canales y seguridad"
      help="Cada canal define qué se puede automatizar y con qué límites. Los flujos, el agente de IA y las difusiones solo envían a través de un canal, así que al cambiar de espejo a la API oficial se ajusta el canal y nada más."
      action={
        canManage && (
          <button type="button" className={ghostButtonClass} onClick={() => setCreating((v) => !v)}>
            Agregar canal
          </button>
        )
      }
    >
      {creating && (
        <div className="mb-4 grid gap-3 rounded-2xl border border-line bg-white p-5 md:grid-cols-4">
          <Field label="Id" hint="minúsculas, sin espacios">
            <input
              className={inputClass}
              value={form.id}
              onChange={(e) => setForm({ ...form, id: e.target.value })}
              placeholder="espejo-1"
            />
          </Field>
          <Field label="Nombre">
            <input
              className={inputClass}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="WhatsApp Business"
            />
          </Field>
          <Field label="Tipo">
            <select
              className={inputClass}
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value as Channel["kind"] })}
            >
              <option value="whatsapp_mirror">Espejo de WhatsApp</option>
              <option value="whatsapp_cloud">API oficial de WhatsApp</option>
            </select>
          </Field>
          <div className="flex items-end">
            <button type="button" className={buttonClass} onClick={() => void create()}>
              Crear
            </button>
          </div>
          {error && (
            <div className="md:col-span-4">
              <Banner tone="error">{error}</Banner>
            </div>
          )}
        </div>
      )}
      <div className="space-y-4">
        {channels.map((channel) => (
          <ChannelCard
            key={channel.id + JSON.stringify(channel.policy) + channel.status}
            channel={channel}
            canManage={canManage}
            onChanged={onChanged}
          />
        ))}
      </div>
    </Section>
  );
}
