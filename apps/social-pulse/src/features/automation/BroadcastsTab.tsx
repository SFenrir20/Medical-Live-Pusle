import { useCallback, useEffect, useState } from "react";
import { api, Broadcast, Channel, problemText } from "./api";
import { Banner, buttonClass, Field, ghostButtonClass, inputClass, Section, when } from "./ui";

const STATUS: Record<Broadcast["status"], { label: string; style: string }> = {
  draft: { label: "Borrador", style: "bg-slate-100 text-slate-600" },
  scheduled: { label: "Programada", style: "bg-sky-50 text-sky-700" },
  sending: { label: "Enviando", style: "bg-emerald-50 text-emerald-700" },
  paused: { label: "En pausa", style: "bg-amber-50 text-amber-700" },
  done: { label: "Terminada", style: "bg-emerald-50 text-emerald-700" },
  cancelled: { label: "Cancelada", style: "bg-red-50 text-red-700" },
};
const AUDIENCE_STATUSES = [
  ["new", "Nuevos"],
  ["contacted", "Contactados"],
  ["qualified", "Calificados"],
];

function Detail({ id, canManage, onBack }: { id: number; canManage: boolean; onBack: () => void }) {
  const [b, setB] = useState<Broadcast | null>(null);
  const [notice, setNotice] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [testPhone, setTestPhone] = useState("");
  const [confirm, setConfirm] = useState("");

  const load = useCallback(async () => {
    try {
      setB(await api.broadcast(id));
    } catch (e) {
      setNotice({ tone: "error", text: problemText(e) });
    }
  }, [id]);
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [load]);

  if (!b) return <p className="mt-6 text-sm text-muted">Cargando…</p>;
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setNotice(null);
    try {
      await fn();
      setNotice({ tone: "ok", text: ok });
      await load();
    } catch (e) {
      setNotice({ tone: "error", text: problemText(e) });
    }
  };
  const percent = b.total ? Math.round(((b.sent + b.skipped + b.failed) / b.total) * 100) : 0;
  return (
    <Section
      title={b.name}
      help={`Canal ${b.channel_id} · creada ${when(b.created_at)}`}
      action={
        <button type="button" className={ghostButtonClass} onClick={onBack}>
          ← Difusiones
        </button>
      }
    >
      <div className="space-y-4">
        <div className="rounded-2xl border border-line bg-white p-5">
          <div className="flex items-center gap-3">
            <span className={`rounded-full px-3 py-1 text-xs font-bold ${STATUS[b.status].style}`}>
              {STATUS[b.status].label}
            </span>
            <span className="text-sm text-muted">
              {b.sent} enviados · {b.skipped} omitidos · {b.failed} fallidos · {b.total} en total
            </span>
          </div>
          <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-primary" style={{ width: `${percent}%` }} />
          </div>
          {b.pause_reason && (
            <div className="mt-3">
              <Banner tone="warn">{b.pause_reason}</Banner>
            </div>
          )}
          <p className="mt-4 whitespace-pre-line rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900">
            {b.body}
          </p>
        </div>
        {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
        {canManage && (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-line bg-white p-5">
              <h4 className="text-sm font-bold">Enviar una prueba</h4>
              <p className="mt-1 text-xs text-muted">
                Un solo mensaje, tal como lo recibiría una persona. En el espejo, el número debe
                estar en la lista de prueba del canal.
              </p>
              <div className="mt-3 flex gap-2">
                <input
                  className={inputClass}
                  placeholder="+51987654321"
                  value={testPhone}
                  onChange={(e) => setTestPhone(e.target.value)}
                />
                <button
                  type="button"
                  className={ghostButtonClass}
                  disabled={!testPhone.trim()}
                  onClick={() =>
                    void act(() => api.testBroadcast(b.id, testPhone), "Prueba enviada.")
                  }
                >
                  Enviar
                </button>
              </div>
            </div>
            <div className="rounded-2xl border border-line bg-white p-5">
              <h4 className="text-sm font-bold">Control del envío</h4>
              {(b.status === "draft" || b.status === "paused") && (
                <div className="mt-3">
                  <Field
                    label={`Para iniciar, escribe el número exacto de destinatarios (${b.recipients_by_status?.pending ?? 0})`}
                  >
                    <input
                      className={inputClass}
                      inputMode="numeric"
                      value={confirm}
                      onChange={(e) => setConfirm(e.target.value)}
                    />
                  </Field>
                  <button
                    type="button"
                    className={`${buttonClass} mt-2`}
                    disabled={!confirm}
                    onClick={() =>
                      void act(() => api.startBroadcast(b.id, Number(confirm)), "Envío iniciado.")
                    }
                  >
                    {b.status === "paused" ? "Reanudar con confirmación" : "Iniciar envío"}
                  </button>
                </div>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                {(b.status === "sending" || b.status === "scheduled") && (
                  <button
                    type="button"
                    className={ghostButtonClass}
                    onClick={() => void act(() => api.broadcastAction(b.id, "pause"), "En pausa.")}
                  >
                    Pausar
                  </button>
                )}
                {b.status === "paused" && (
                  <button
                    type="button"
                    className={ghostButtonClass}
                    onClick={() =>
                      void act(() => api.broadcastAction(b.id, "resume"), "Reanudada.")
                    }
                  >
                    Reanudar
                  </button>
                )}
                {["draft", "scheduled", "sending", "paused"].includes(b.status) && (
                  <button
                    type="button"
                    className={`${ghostButtonClass} text-red-600`}
                    onClick={() => {
                      if (window.confirm("¿Cancelar la difusión?"))
                        void act(() => api.broadcastAction(b.id, "cancel"), "Cancelada.");
                    }}
                  >
                    Cancelar
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
        {b.recipients && (
          <div className="overflow-x-auto rounded-2xl border border-line bg-white">
            <table className="w-full text-left text-sm">
              <thead className="text-[11px] uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-3">Teléfono</th>
                  <th className="px-2 py-3">Nombre</th>
                  <th className="px-2 py-3">Estado</th>
                </tr>
              </thead>
              <tbody>
                {b.recipients.map((r) => (
                  <tr key={r.phone} className="border-t border-line">
                    <td className="px-4 py-2 font-mono text-xs">{r.phone}</td>
                    <td className="px-2 py-2">{r.name ?? "—"}</td>
                    <td className="px-2 py-2 text-xs">
                      {r.status}
                      {r.error ? ` (${r.error})` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Section>
  );
}

export function BroadcastsTab({
  channels,
  canManage,
}: {
  channels: Channel[];
  canManage: boolean;
}) {
  const [items, setItems] = useState<Broadcast[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    name: "",
    body: "",
    channel_id: channels[0]?.id ?? "simulador",
  });
  const [statuses, setStatuses] = useState<string[]>(["new"]);
  const [excludeDays, setExcludeDays] = useState(0);
  const [requireConsent, setRequireConsent] = useState(true);
  const [preview, setPreview] = useState<{
    count: number;
    sample: { phone: string; name: string | null }[];
  } | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setItems(await api.broadcasts());
    } catch (e) {
      setError(problemText(e));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const audience = {
    statuses,
    exclude_contacted_days: excludeDays,
    require_consent: requireConsent,
  };
  const channel = channels.find((c) => c.id === form.channel_id);
  const channelOff = channel && !channel.policy.broadcasts_enabled;

  const runPreview = async () => {
    setError("");
    try {
      setPreview(await api.previewAudience(audience));
    } catch (e) {
      setError(problemText(e));
    }
  };

  const create = async () => {
    setError("");
    try {
      const created = await api.createBroadcast({ ...form, audience });
      setCreating(false);
      setPreview(null);
      setForm({ ...form, name: "", body: "" });
      await load();
      setOpen(created.id);
    } catch (e) {
      setError(problemText(e));
    }
  };

  if (open !== null)
    return (
      <Detail
        id={open}
        canManage={canManage}
        onBack={() => {
          setOpen(null);
          void load();
        }}
      />
    );

  return (
    <Section
      title="Difusiones (mensajes masivos)"
      help="Pensadas como muestra de lo que se puede hacer, no para uso frecuente: en el espejo de WhatsApp están apagadas por defecto y, si se encienden, solo llegan a la lista de prueba. En el canal oficial son la herramienta normal."
      action={
        canManage && (
          <button type="button" className={buttonClass} onClick={() => setCreating((v) => !v)}>
            Nueva difusión
          </button>
        )
      }
    >
      {error && (
        <div className="mb-4">
          <Banner tone="error">{error}</Banner>
        </div>
      )}
      {creating && (
        <div className="mb-5 space-y-4 rounded-2xl border border-line bg-white p-5">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="1 · Nombre">
              <input
                className={inputClass}
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Recordatorio de valoración"
              />
            </Field>
            <Field label="Canal">
              <select
                className={inputClass}
                value={form.channel_id}
                onChange={(e) => setForm({ ...form, channel_id: e.target.value })}
              >
                {channels.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          {channelOff && (
            <Banner tone="warn">
              Las difusiones están apagadas en este canal: la difusión se creará, pero se pausará al
              iniciar hasta que se enciendan en «Canales y seguridad».
            </Banner>
          )}
          <Field label="2 · Mensaje" hint="{{nombre}} · {{nombre|paciente}} con valor por defecto">
            <textarea
              className={`${inputClass} h-24`}
              maxLength={1000}
              value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
            />
          </Field>
          <div>
            <span className="text-xs font-bold">3 · Audiencia</span>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {AUDIENCE_STATUSES.map(([value, label]) => {
                const on = statuses.includes(value);
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() =>
                      setStatuses(on ? statuses.filter((s) => s !== value) : [...statuses, value])
                    }
                    className={`rounded-full border px-3 py-1 text-xs font-semibold ${on ? "border-primary bg-primary-soft text-primary" : "border-line text-muted"}`}
                  >
                    {label}
                  </button>
                );
              })}
              <label className="ml-2 flex items-center gap-2 text-xs text-muted">
                Excluir contactados en los últimos
                <input
                  type="number"
                  min={0}
                  max={365}
                  className="w-16 rounded-lg border border-line px-2 py-1"
                  value={excludeDays}
                  onChange={(e) => setExcludeDays(Number(e.target.value))}
                />{" "}
                días
              </label>
              <button type="button" className={ghostButtonClass} onClick={() => void runPreview()}>
                Ver a cuántas personas llega
              </button>
            </div>
            <label className="mt-3 flex items-center gap-2 text-xs text-ink">
              <input type="checkbox" checked={requireConsent} onChange={(e) => setRequireConsent(e.target.checked)} />
              Solo contactos que autorizaron WhatsApp (se marca en la ficha del contacto)
            </label>
            <p className="mt-2 text-[11px] text-muted">
              Siempre se excluye a quien pidió no recibir mensajes.
            </p>
            {preview && (
              <p className="mt-2 rounded-xl bg-slate-50 p-3 text-sm">
                Llegaría a <strong>{preview.count}</strong> personas
                {preview.sample.length
                  ? ` (por ejemplo ${preview.sample.map((s) => s.name || s.phone).join(", ")})`
                  : ""}
                .
              </p>
            )}
          </div>
          <button
            type="button"
            className={buttonClass}
            disabled={!form.name.trim() || !form.body.trim() || !statuses.length}
            onClick={() => void create()}
          >
            4 · Crear borrador
          </button>
          <p className="text-[11px] text-muted">
            Crear el borrador no envía nada. Para enviar tendrás que confirmar el número exacto de
            destinatarios.
          </p>
        </div>
      )}
      <div className="overflow-x-auto rounded-2xl border border-line bg-white">
        <table className="w-full min-w-[620px] text-left text-sm">
          <thead className="text-[11px] uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-3">Difusión</th>
              <th className="px-2 py-3">Canal</th>
              <th className="px-2 py-3">Estado</th>
              <th className="px-2 py-3">Enviados</th>
              <th className="px-2 py-3">Creada</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((b) => (
              <tr key={b.id} className="border-t border-line">
                <td className="px-4 py-3 font-semibold">{b.name}</td>
                <td className="px-2 py-3 text-xs text-muted">
                  {channels.find((c) => c.id === b.channel_id)?.name ?? b.channel_id}
                </td>
                <td className="px-2 py-3">
                  <span
                    className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${STATUS[b.status].style}`}
                  >
                    {STATUS[b.status].label}
                  </span>
                </td>
                <td className="px-2 py-3 text-xs">
                  {b.sent} / {b.total}
                </td>
                <td className="px-2 py-3 text-xs text-muted">{when(b.created_at)}</td>
                <td className="px-2 py-3 text-right">
                  <button type="button" className={ghostButtonClass} onClick={() => setOpen(b.id)}>
                    Abrir
                  </button>
                </td>
              </tr>
            ))}
            {!items.length && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-muted">
                  Todavía no hay difusiones.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Section>
  );
}
