import { useCallback, useEffect, useState } from "react";
import {
  Bot,
  Link2,
  MessageSquareText,
  MousePointerClick,
  RefreshCw,
  Send,
  Smartphone,
  Users,
  Workflow,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { AutomationPanel } from "@/features/automation/AutomationPanel";
import { api as automationApi, Overview } from "@/features/automation/api";
import { BroadcastsTab } from "@/features/automation/BroadcastsTab";
import { chatApi, ContactRow, problem, Stage, Summary } from "@/features/chats/api";
import { Avatar } from "@/features/chats/ConversationList";
import { initials, nice, shortTime, STAGES, stageOf } from "@/features/chats/format";
import { AppNav } from "@/features/shell/AppNav";
import { QuickRepliesManager } from "./QuickRepliesManager";

type Tab = "contacts" | "campaigns" | "automations";

function Stat({
  icon,
  value,
  label,
  tone,
}: {
  icon: React.ReactNode;
  value: number | string;
  label: string;
  tone: string;
}) {
  return (
    <div className="rounded-2xl border border-line bg-white p-5">
      <span className={`grid size-10 place-items-center rounded-xl ${tone}`}>{icon}</span>
      <strong className="mt-4 block text-3xl">{value}</strong>
      <span className="text-sm text-muted">{label}</span>
    </div>
  );
}

function Contacts({ mayAssign }: { mayAssign: boolean }) {
  const [rows, setRows] = useState<ContactRow[]>([]);
  const [q, setQ] = useState("");
  const [stage, setStage] = useState<Stage | "">("");
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const page = await chatApi.contacts(q, stage, offset);
      setRows(page.items);
      setHasMore(page.has_more);
      setError("");
    } catch (e) {
      setError(problem(e));
    }
  }, [q, stage, offset]);
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 250);
    return () => window.clearTimeout(timer);
  }, [load]);

  const change = async (row: ContactRow, value: Stage) => {
    if (!row.conversation_id) return;
    setBusy(true);
    try {
      await chatApi.patch(row.conversation_id, { stage: value });
      await load();
    } catch (e) {
      setError(problem(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-2xl border border-line bg-white">
      <div className="flex flex-col justify-between gap-3 border-b border-line p-5 sm:flex-row sm:items-center">
        <div>
          <h2 className="text-lg font-bold">Base de pacientes</h2>
          <p className="text-sm text-muted">
            Actualiza la etapa, mira quién atiende y qué contactos autorizaron WhatsApp.
          </p>
        </div>
        <div className="flex gap-2">
          <select
            aria-label="Filtrar por etapa"
            value={stage}
            onChange={(e) => {
              setStage(e.target.value as Stage | "");
              setOffset(0);
            }}
            className="rounded-xl border border-line px-3 py-2 text-sm"
          >
            <option value="">Todas las etapas</option>
            {STAGES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <input
            aria-label="Buscar nombre o teléfono"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
            placeholder="Buscar nombre o teléfono"
            className="w-56 rounded-xl border border-line px-3 py-2 text-sm outline-none focus:border-primary"
          />
        </div>
      </div>
      {error && (
        <p role="alert" className="m-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] text-left text-sm">
          <thead className="text-[11px] uppercase tracking-wide text-muted">
            <tr>
              <th className="px-5 py-3">Contacto</th>
              <th className="px-2 py-3">Último mensaje</th>
              <th className="px-2 py-3">Etapa</th>
              <th className="px-2 py-3">Atiende</th>
              <th className="px-2 py-3">WhatsApp</th>
              <th className="px-2 py-3" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const editable = !!r.conversation_id && (r.is_mine || mayAssign);
              const consent = r.opted_out
                ? { text: "Pidió no recibir", style: "bg-red-50 text-red-700" }
                : r.consent === "granted"
                  ? { text: "WhatsApp autorizado", style: "bg-emerald-50 text-emerald-700" }
                  : r.consent === "revoked"
                    ? { text: "Revocado", style: "bg-red-50 text-red-700" }
                    : { text: "Sin consentimiento", style: "bg-slate-100 text-slate-600" };
              return (
                <tr key={`${r.registry_id ?? "c"}-${r.phone}`} className="border-t border-line">
                  <td className="px-5 py-3">
                    <span className="flex items-center gap-3">
                      {r.conversation_id ? (
                        <Avatar name={r.name} phone={r.phone} size="size-10" />
                      ) : (
                        <span className="grid size-10 place-items-center rounded-full bg-primary-soft text-xs font-bold text-primary">
                          {initials(r.name, r.phone)}
                        </span>
                      )}
                      <span>
                        <strong className="block">{r.name || nice(r.phone)}</strong>
                        <span className="text-xs text-muted">
                          {nice(r.phone)}
                          {r.origin === "tiktok_live" ? " · LIVE" : ""}
                        </span>
                      </span>
                    </span>
                  </td>
                  <td className="max-w-[260px] px-2 py-3 text-xs text-muted">
                    <span className="line-clamp-2">{r.message ?? "—"}</span>
                    {r.last_message_at && (
                      <span className="text-[10px]">{shortTime(r.last_message_at)}</span>
                    )}
                  </td>
                  <td className="px-2 py-3">
                    {editable ? (
                      <select
                        aria-label={`Etapa de ${r.name || r.phone}`}
                        disabled={busy}
                        value={r.stage}
                        onChange={(e) => void change(r, e.target.value as Stage)}
                        className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-semibold"
                      >
                        {STAGES.map((s) => (
                          <option key={s.value} value={s.value}>
                            {s.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span
                        className={`rounded-full px-3 py-1 text-xs font-bold ${stageOf(r.stage).chip}`}
                      >
                        {stageOf(r.stage).label}
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-3 text-xs">
                    {r.is_mine ? "Tú" : (r.advisor_name ?? "Sin asignar")}
                  </td>
                  <td className="px-2 py-3">
                    <span
                      className={`whitespace-nowrap rounded-full px-3 py-1 text-xs font-bold ${consent.style}`}
                    >
                      {consent.text}
                    </span>
                  </td>
                  <td className="px-2 py-3 text-right">
                    <a
                      href={`/whatsapp?phone=${encodeURIComponent(r.phone)}`}
                      className="rounded-xl border border-line px-3 py-1.5 text-xs font-bold text-primary hover:bg-primary-soft"
                    >
                      Abrir chat
                    </a>
                  </td>
                </tr>
              );
            })}
            {!rows.length && (
              <tr>
                <td colSpan={6} className="px-5 py-10 text-center text-sm text-muted">
                  No hay contactos con esos filtros.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {(offset > 0 || hasMore) && (
        <div className="flex justify-between border-t border-line px-5 py-3 text-sm font-semibold text-primary">
          <button
            type="button"
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 50))}
            className="disabled:opacity-30"
          >
            Anterior
          </button>
          <button
            type="button"
            disabled={!hasMore}
            onClick={() => setOffset(offset + 50)}
            className="disabled:opacity-30"
          >
            Siguiente
          </button>
        </div>
      )}
    </section>
  );
}

function Automations({ canManageReplies }: { canManageReplies: boolean }) {
  const [open, setOpen] = useState<"bot" | "replies" | null>(null);
  const cards = [
    {
      key: "bot" as const,
      icon: <Bot size={22} />,
      tone: "bg-primary-soft text-primary",
      title: "MedicalBot",
      text: "Diseña flujos y un asistente que clasifica consultas, responde con tu información y pasa a una persona cuando hace falta.",
      action: "Configurar MedicalBot",
      enabled: true,
    },
    {
      key: "replies" as const,
      icon: <MessageSquareText size={22} />,
      tone: "bg-emerald-50 text-emerald-700",
      title: "Mensajes pregrabados",
      text: "Respuestas para precios, ubicaciones, preparación, recuperación y horarios, listas con un atajo.",
      action: "Crear respuestas",
      enabled: true,
    },
    {
      key: null,
      icon: <MousePointerClick size={22} />,
      tone: "bg-sky-50 text-sky-700",
      title: "MedicalClic",
      text: "Botones, menús y llamadas a la acción dentro del mensaje. Necesita la API oficial de WhatsApp: el espejo no puede enviarlos.",
      action: "Requiere API oficial",
      enabled: false,
    },
  ];
  return (
    <>
      <section className="overflow-hidden rounded-3xl bg-deep p-7 text-white">
        <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-cyan-200">
          <Workflow size={13} /> Automatización Medical
        </span>
        <h2 className="mt-4 text-3xl font-bold tracking-tight">
          ¿Qué quieres automatizar primero?
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-slate-300">
          Empieza por un módulo y combínalos: el bot detecta una consulta, usa un mensaje pregrabado
          y pasa a una asesora para agendar.
        </p>
      </section>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        {cards.map((c) => (
          <article
            key={c.title}
            className={`flex flex-col rounded-2xl border bg-white p-5 ${open === c.key && c.key ? "border-primary" : "border-line"} ${c.enabled ? "" : "opacity-70"}`}
          >
            <span className={`grid size-11 place-items-center rounded-xl ${c.tone}`}>{c.icon}</span>
            <h3 className="mt-4 text-lg font-bold">{c.title}</h3>
            <p className="mt-2 flex-1 text-sm text-muted">{c.text}</p>
            <button
              type="button"
              disabled={!c.enabled}
              onClick={() => c.key && setOpen(open === c.key ? null : c.key)}
              className="mt-4 rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-white disabled:bg-slate-300"
            >
              {c.action} {c.enabled && "→"}
            </button>
          </article>
        ))}
      </div>
      <p className="mt-4 flex items-start gap-3 rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900">
        <Link2 size={16} className="mt-0.5 shrink-0" /> Los bots y las campañas siguen desconectados
        del WhatsApp real: se diseñan y prueban en el simulador. Sobre el espejo (que no es oficial)
        los bots y los envíos masivos pueden hacer que restrinjan el número, y solo el administrador
        puede encenderlos.
      </p>
      {open === "replies" && <QuickRepliesManager canManage={canManageReplies} />}
      {open === "bot" && (
        <div className="mt-2">
          <AutomationPanel />
        </div>
      )}
    </>
  );
}

/** CRM omnicanal: patients, campaigns and automations in one place. Agents see their own contacts;
 *  supervisors everything; campaigns and automations only roles that may look at them. */
export function CrmPage() {
  const { user } = useAuth();
  const permissions = user?.permissions ?? [];
  const mayRead =
    permissions.includes("wa:read") &&
    permissions.includes("automation:read") &&
    !!user?.screens.includes("marketing");
  const seesAutomation = permissions.includes("automation:read");
  const [tab, setTab] = useState<Tab>("automations");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);

  const load = useCallback(async () => {
    try {
      setSummary(await chatApi.summary());
      if (seesAutomation) setOverview(await automationApi.overview());
    } catch {
      /* the page keeps working without the numbers */
    }
  }, [seesAutomation]);
  useEffect(() => {
    if (!mayRead) return;
    void load();
    const timer = window.setInterval(() => void load(), 20000);
    return () => window.clearInterval(timer);
  }, [mayRead, load]);

  if (!mayRead)
    return (
      <>
        <AppNav />
        <main className="p-8">
          TOOLS está disponible en la vista de marketing y supervisión.{" "}
          <a className="text-primary" href="/">
            Volver
          </a>
        </main>
      </>
    );

  const tabs: { key: Tab; label: string }[] = [
    ...(seesAutomation
      ? [
          { key: "campaigns" as Tab, label: "Campañas" },
          { key: "automations" as Tab, label: "Automatizaciones" },
        ]
      : []),
  ];
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <AppNav />
      <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 sm:py-8">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.16em] text-primary">
              <Link2 size={13} /> TOOLS
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
              Herramientas de marketing
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
              Gestiona campañas, mensajes pregrabados y automatizaciones desde un solo lugar.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            aria-label="Actualizar"
            className="grid size-10 place-items-center rounded-xl border border-line bg-white text-muted hover:text-primary"
          >
            <RefreshCw size={16} />
          </button>
        </div>

        <div
          className="mt-6 grid gap-4"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))" }}
        >
          <Stat
            icon={<Users size={18} />}
            value={summary?.contacts ?? "—"}
            label="Contactos CRM"
            tone="bg-sky-50 text-sky-600"
          />
          <Stat
            icon={<MessageSquareText size={18} />}
            value={summary?.conversations ?? "—"}
            label="Conversaciones abiertas"
            tone="bg-primary-soft text-primary"
          />
          <Stat
            icon={<Smartphone size={18} />}
            value={summary?.ready_for_whatsapp ?? "—"}
            label="Listos para WhatsApp"
            tone="bg-emerald-50 text-emerald-600"
          />
          {summary?.campaigns != null && (
            <Stat
              icon={<Send size={18} />}
              value={summary.campaigns}
              label="Campañas"
              tone="bg-violet-50 text-violet-600"
            />
          )}
          {summary?.automations != null && (
            <Stat
              icon={<Bot size={18} />}
              value={summary.automations}
              label="Automatizaciones activas"
              tone="bg-amber-50 text-amber-600"
            />
          )}
        </div>

        <div className="mt-6 flex gap-2 rounded-2xl border border-line bg-white p-2">
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`rounded-xl px-5 py-2.5 text-sm font-semibold ${tab === t.key ? "bg-deep text-white" : "text-muted hover:bg-slate-50"}`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="mt-5">
          {tab === "contacts" && (
            <Contacts mayAssign={permissions.includes("contacts:assign_any")} />
          )}
          {tab === "campaigns" && overview && (
            <>
              <p className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                Las campañas se prueban en el simulador. Sobre el espejo de WhatsApp están apagadas
                por defecto y solo llegan a una lista de prueba; la audiencia puede limitarse a
                quienes autorizaron WhatsApp.
              </p>
              <BroadcastsTab channels={overview.channels} canManage={overview.can_manage} />
            </>
          )}
          {tab === "automations" && (
            <Automations canManageReplies={permissions.includes("crm:manage")} />
          )}
        </div>
      </main>
    </div>
  );
}

export function ContactsPage() {
  const { user } = useAuth();
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <AppNav />
      <main className="mx-auto max-w-[1400px] px-4 py-8 sm:px-6">
        <p className="text-xs font-bold uppercase tracking-widest text-primary">Seguimiento</p>
        <h1 className="mb-6 mt-2 text-3xl font-bold">Contactos</h1>
        {user?.permissions.includes("wa:read") ? (
          <Contacts mayAssign={user.permissions.includes("contacts:assign_any")} />
        ) : (
          <p>Tu rol no tiene acceso a los contactos.</p>
        )}
      </main>
    </div>
  );
}
