import { useCallback, useEffect, useState } from "react";
import { FileSpreadsheet, ShieldAlert } from "lucide-react";
import { errorMessage } from "@/features/workspace/api";
import {
  AlertStatus,
  Complaint,
  ContactAlert,
  downloadContacts,
  fetchAlerts,
  fetchComplaints,
  reviewAlert,
  reviewComplaint,
} from "./api";

const limaTime = (iso: string) =>
  new Date(iso).toLocaleString("es-PE", {
    timeZone: "America/Lima",
    day: "2-digit",
    month: "2-digit",
    hour: "numeric",
    minute: "2-digit",
  });

const KIND_STYLE: Record<string, string> = {
  same_live: "bg-red-50 text-red-700",
  other_live: "bg-amber-50 text-amber-700",
  other_account: "bg-violet-50 text-violet-700",
};
const STATUS_TEXT: Record<string, string> = {
  new: "Nuevo",
  contacted: "Contactado",
  qualified: "Calificado",
  discarded: "Descartado",
};

function describe(alert: ContactAlert) {
  const who = alert.advisor ?? "un asesor";
  const where =
    alert.kind === "same_live"
      ? "en el mismo LIVE"
      : alert.kind === "other_live"
        ? `en otro LIVE de ${alert.account}`
        : `en otra cuenta (${alert.account})`;
  return `${who} lo marcó como contactado a las ${limaTime(alert.contacted_at)}; volvió a escribir su número ${where} ${alert.minutes_after_contact} min después.`;
}

/** Supervisors, marketing heads and managers: who needs a second look, and a way to say what
 *  was found. Agents never reach this screen (the API refuses them too). */
export function AlertsPanel() {
  const [tab, setTab] = useState<"alerts" | "complaints">("alerts");
  const [status, setStatus] = useState<AlertStatus>("open");
  const [alerts, setAlerts] = useState<ContactAlert[]>([]);
  const [alertTotal, setAlertTotal] = useState(0);
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [complaintTotal, setComplaintTotal] = useState(0);
  const [showReviewed, setShowReviewed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async () => {
    try {
      const [a, c] = await Promise.all([
        fetchAlerts(status),
        fetchComplaints(showReviewed ? "all" : "open"),
      ]);
      setAlerts(a.items);
      setAlertTotal(a.total);
      setComplaints(c.items);
      setComplaintTotal(c.total);
      setError("");
    } catch (err) {
      setError(errorMessage(err, "No se pudieron cargar las alertas."));
    } finally {
      setLoading(false);
    }
  }, [status, showReviewed]);

  useEffect(() => {
    setLoading(true);
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 15000);
    return () => window.clearInterval(timer);
  }, [load]);

  const review = async (alert: ContactAlert, next: AlertStatus) => {
    setBusy(alert.id);
    try {
      await reviewAlert(alert.id, next, notes[alert.id]);
      await load();
    } catch (err) {
      setError(errorMessage(err, "No se pudo guardar la revisión."));
    } finally {
      setBusy(null);
    }
  };

  const markComplaint = async (complaint: Complaint) => {
    setBusy(-complaint.id);
    try {
      await reviewComplaint(complaint.id, !complaint.reviewed_at);
      await load();
    } catch (err) {
      setError(errorMessage(err, "No se pudo guardar la revisión."));
    } finally {
      setBusy(null);
    }
  };

  const download = async () => {
    setDownloading(true);
    try {
      await downloadContacts();
      setError("");
    } catch (err) {
      setError(errorMessage(err, "No se pudo descargar la lista de contactos."));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <section className="mt-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <h2 className="text-xl font-bold">Alertas de validación</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Contactos que figuran como contactados pero volvieron a escribir su número, y comentarios
            de personas que dicen que no las atendieron. Son motivos para revisar, no prueba:
            confirma con el chat o el registro de la central.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void download()}
          disabled={downloading}
          className="inline-flex w-fit items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-emerald-700 disabled:opacity-60"
        >
          <FileSpreadsheet size={16} />
          {downloading ? "Preparando…" : "Descargar contactos"}
        </button>
      </div>

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </p>
      )}

      <div className="mt-5 flex gap-2">
        {(
          [
            ["alerts", `Números que reaparecen (${alertTotal})`],
            ["complaints", `“No me contactan” (${complaintTotal})`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`rounded-xl px-4 py-2.5 text-sm font-semibold ${
              tab === key ? "bg-primary-soft text-primary" : "text-muted hover:bg-slate-50"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "alerts" && (
        <div className="mt-4">
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as AlertStatus)}
            className="rounded-xl border border-line bg-white px-3 py-2 text-sm"
            aria-label="Estado de la alerta"
          >
            <option value="open">Por revisar</option>
            <option value="reviewed">Revisadas</option>
            <option value="dismissed">Descartadas</option>
          </select>
          {loading && <p className="mt-4 text-sm text-muted">Cargando…</p>}
          {!loading && !alerts.length && (
            <p className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-muted">
              No hay alertas {status === "open" ? "por revisar" : "en este estado"}.
            </p>
          )}
          <div className="mt-4 space-y-3">
            {alerts.map((alert) => (
              <article key={alert.id} className="rounded-2xl border border-line bg-white p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <ShieldAlert size={18} className="text-red-500" />
                  <strong className="font-mono text-sm">{alert.phone}</strong>
                  {alert.tiktok_username && (
                    <span className="text-xs text-muted">@{alert.tiktok_username.replace(/^@/, "")}</span>
                  )}
                  <span
                    className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${KIND_STYLE[alert.kind]}`}
                  >
                    {alert.kind_label}
                  </span>
                  {alert.repeats > 1 && (
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-600">
                      {alert.repeats} veces
                    </span>
                  )}
                </div>
                <p className="mt-3 text-sm leading-6">{describe(alert)}</p>
                <p className="mt-1 text-xs text-muted">
                  Primera captura {limaTime(alert.first_captured_at)}
                  {alert.first_account ? ` · ${alert.first_account}` : ""} · Estado actual:{" "}
                  {STATUS_TEXT[alert.contact_status] ?? alert.contact_status}
                  {alert.live_title ? ` · LIVE “${alert.live_title}”` : ""}
                </p>
                {alert.status === "open" ? (
                  <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                    <input
                      value={notes[alert.id] ?? ""}
                      onChange={(event) =>
                        setNotes((current) => ({ ...current, [alert.id]: event.target.value }))
                      }
                      placeholder="Nota (opcional): qué se encontró"
                      maxLength={500}
                      className="flex-1 rounded-xl border border-line px-3 py-2 text-sm"
                    />
                    <button
                      type="button"
                      disabled={busy === alert.id}
                      onClick={() => void review(alert, "reviewed")}
                      className="rounded-xl bg-primary px-4 py-2 text-xs font-bold text-white disabled:opacity-60"
                    >
                      Marcar revisada
                    </button>
                    <button
                      type="button"
                      disabled={busy === alert.id}
                      onClick={() => void review(alert, "dismissed")}
                      className="rounded-xl border border-line px-4 py-2 text-xs font-bold text-slate-600 disabled:opacity-60"
                    >
                      Falsa alarma
                    </button>
                  </div>
                ) : (
                  <p className="mt-3 text-xs text-muted">
                    {alert.status === "reviewed" ? "Revisada" : "Descartada"} por{" "}
                    {alert.reviewed_by ?? "—"}
                    {alert.reviewed_at ? ` · ${limaTime(alert.reviewed_at)}` : ""}
                    {alert.note ? ` · ${alert.note}` : ""}
                  </p>
                )}
              </article>
            ))}
          </div>
        </div>
      )}

      {tab === "complaints" && (
        <div className="mt-4">
          <label className="flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              checked={showReviewed}
              onChange={(event) => setShowReviewed(event.target.checked)}
            />
            Incluir los ya revisados
          </label>
          {loading && <p className="mt-4 text-sm text-muted">Cargando…</p>}
          {!loading && !complaints.length && (
            <p className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-muted">
              No hay comentarios de este tipo en los últimos días.
            </p>
          )}
          <div className="mt-4 space-y-3">
            {complaints.map((item) => (
              <article key={item.id} className="rounded-2xl border border-line bg-white p-5">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                  <strong className="text-sm text-ink">@{item.username.replace(/^@/, "")}</strong>
                  <span>
                    {item.account} · {limaTime(item.created_at)}
                    {item.live_title ? ` · “${item.live_title}”` : ""}
                  </span>
                </div>
                <p className="mt-2 rounded-xl bg-slate-50 p-3 text-sm">“{item.comment}”</p>
                {item.contacts.length ? (
                  <ul className="mt-3 space-y-1 text-xs">
                    {item.contacts.map((contact) => (
                      <li key={contact.phone}>
                        <span className="font-mono font-semibold">{contact.phone}</span> ·{" "}
                        {STATUS_TEXT[contact.status] ?? contact.status}
                        {contact.advisor ? ` · asesor: ${contact.advisor}` : " · sin asesor"}
                        {contact.contacted_at ? ` · contactado ${limaTime(contact.contacted_at)}` : ""}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 text-xs text-muted">
                    Este usuario no dejó ningún número registrado.
                  </p>
                )}
                <button
                  type="button"
                  disabled={busy === -item.id}
                  onClick={() => void markComplaint(item)}
                  className="mt-4 rounded-xl border border-line px-4 py-2 text-xs font-bold text-slate-600 disabled:opacity-60"
                >
                  {item.reviewed_at ? `Revisado por ${item.reviewed_by ?? "—"} · reabrir` : "Marcar como revisado"}
                </button>
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
