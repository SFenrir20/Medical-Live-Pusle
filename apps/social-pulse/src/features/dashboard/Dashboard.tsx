import { useEffect, useState } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Bell,
  BellRing,
  ClipboardCheck,
  ChevronRight,
  CircleUserRound,
  Copy,
  Eye,
  FileSpreadsheet,
  Gauge,
  Gift,
  Heart,
  LogOut,
  MessageCircle,
  MessagesSquare,
  Music2,
  Phone,
  Search,
  Settings,
  Share2,
  SlidersHorizontal,
  Sparkles,
  TrendingUp,
  UserPlus,
  Users,
  X,
  Zap,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { downloadLiveComments, LiveApi } from "@/features/workspace/api";
import { AlertsPanel } from "@/features/notifications/AlertsPanel";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import { useBoard } from "@/features/workspace/useBoard";
import { MessageStatus, SocialMessage, useWorkspace } from "@/features/workspace/useWorkspace";

type View = "Pulso" | "Bandeja" | "Contactos" | "Ajustes";
type MarketingView = "Resumen" | "Equipo" | "Transmisiones" | "Alertas";

const ROLE_LABEL: Record<string, string> = {
  agente_ventas: "Agente call center",
  gerente: "Gerente",
  jefe_marketing: "Jefe de Marketing",
  supervisor: "Supervisor",
  admin: "Administrador",
};
type LiveSession = {
  id: string;
  account: string;
  host: string;
  /** Why there is no host (title without a code, etc.); empty when there is one. */
  hostNote: string;
  title: string;
  startedAt: string;
  endedAt: string;
  duration: string;
  metrics: {
    loosePhones: number;
    /** null = private messages are not captured by any connected source. */
    directMessages: number | null;
    likes: number;
    views: number;
    interestedViewers: number;
    newFollowers: number;
    donors: number;
    shares: number;
    peak: number;
    average: number | null;
    uniqueViewers: number | null;
  };
};

const lima = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleTimeString("es-PE", {
        hour: "numeric",
        minute: "2-digit",
        timeZone: "America/Lima",
      })
    : "—";

function clock(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min`;
}

const HOST_NOTES = {
  sin_titulo: "el LIVE no tiene título",
  titulo_sin_codigo: "el título no tiene código",
  titulo_con_varios_codigos: "el título tiene varios códigos",
} as const;

/** "Ash" or, when unknown, "Sin asignar (el título no tiene código)". */
const hostLabel = (session: LiveSession) =>
  session.hostNote ? `${session.host} (${session.hostNote})` : session.host;

function toLiveSession(live: LiveApi): LiveSession {
  return {
    id: live.id,
    account: live.account ?? "—",
    host: live.tiktoker ?? "Sin asignar",
    hostNote: live.responsible_note ? HOST_NOTES[live.responsible_note] : "",
    title: live.title ?? "",
    startedAt: lima(live.started_at),
    endedAt: lima(live.ended_at),
    duration: clock(live.duration_seconds ?? 0),
    metrics: {
      loosePhones: live.metrics.phones_captured,
      directMessages: live.metrics.direct_messages_capture
        ? live.metrics.direct_messages_reported
        : null,
      likes: live.metrics.likes_count,
      views: live.metrics.views,
      interestedViewers: live.metrics.interested_viewers,
      newFollowers: live.metrics.new_followers,
      donors: live.metrics.donations_count,
      shares: live.metrics.shares_count,
      peak: live.metrics.peak_viewers,
      average: live.metrics.average_viewers,
      uniqueViewers: live.metrics.unique_viewers,
    },
  };
}

/** Elapsed time of a broadcast that is still on air. */
function elapsed(startedAt: string, now: number) {
  const seconds = Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 1000));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor((seconds % 3600) / 60))}:${pad(seconds % 60)}`;
}

function useNow(everyMs = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), everyMs);
    return () => window.clearInterval(timer);
  }, [everyMs]);
  return now;
}

function Logo() {
  return (
    <div className="flex items-center gap-3">
      <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-primary text-white shadow-lg shadow-primary/20">
        <Activity size={21} strokeWidth={2.5} />
      </span>
      <span className="hidden sm:block">
        <span className="block text-sm font-bold tracking-tight text-ink">
          Medical Social Pulse
        </span>
        <span className="block text-[11px] text-muted">Centro de monitoreo</span>
      </span>
    </div>
  );
}

function TypeBadge({ type }: { type: SocialMessage["type"] }) {
  const styles = {
    Comentario: "bg-slate-100 text-slate-600",
    Interesado: "bg-red-50 text-red-600",
    "Paciente potencial": "bg-violet-50 text-violet-600",
  };
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold ${styles[type]}`}
    >
      {type}
    </span>
  );
}

function StatusBadge({ status }: { status: MessageStatus }) {
  const styles = {
    Nuevo: "bg-amber-50 text-amber-700",
    Contactado: "bg-emerald-50 text-emerald-700",
  };
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold ${styles[status]}`}
    >
      {status}
    </span>
  );
}

/** Results of every broadcast. Only the supervisor/marketing/manager views render it. */
function LiveHistory({
  sessions,
  canExport,
  onExport,
  error,
}: {
  sessions: LiveSession[];
  canExport: boolean;
  onExport: (session: LiveSession) => void;
  error: string;
}) {
  return (
    <section className="mt-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">
          Historial de transmisiones
        </p>
        <h2 className="mt-2 text-xl font-bold tracking-tight">Resultados de cada LIVE</h2>
        <p className="mt-1 text-sm text-muted">
          Al finalizar una transmisión, sus comentarios se archivan y el resumen queda disponible.
        </p>
      </div>

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </p>
      )}

      {!sessions.length ? (
        <div className="mt-5 flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-12 text-center">
          <span className="grid size-11 place-items-center rounded-2xl bg-slate-100 text-slate-400">
            <Activity size={20} />
          </span>
          <strong className="mt-4 text-sm">Todavía no hay transmisiones finalizadas</strong>
          <p className="mt-1 max-w-md text-xs leading-5 text-muted">
            Cuando la plataforma detecte que un LIVE terminó, su reporte aparecerá aquí
            automáticamente.
          </p>
        </div>
      ) : (
        <div className="mt-5 space-y-5">
          {sessions.map((session) => {
            const metrics = [
              [
                Phone,
                session.metrics.loosePhones,
                "Teléfonos sueltos",
                "text-amber-600 bg-amber-50",
              ],
              [
                MessageCircle,
                session.metrics.directMessages ?? "No disponible",
                "Mensajes directos",
                "text-primary bg-primary-soft",
              ],
              [
                Heart,
                session.metrics.likes.toLocaleString("es-PE"),
                "Me gusta (tap tap)",
                "text-red-500 bg-red-50",
              ],
              [
                Eye,
                session.metrics.views.toLocaleString("es-PE"),
                "Visualizaciones",
                "text-sky-600 bg-sky-50",
              ],
              [
                Sparkles,
                session.metrics.interestedViewers,
                "Espectadores interesados",
                "text-violet-600 bg-violet-50",
              ],
              [
                UserPlus,
                session.metrics.newFollowers,
                "Seguidores nuevos",
                "text-emerald-600 bg-emerald-50",
              ],
              [Gift, session.metrics.donors, "Donadores", "text-pink-600 bg-pink-50"],
              [Share2, session.metrics.shares, "Compartidos", "text-cyan-600 bg-cyan-50"],
              [TrendingUp, session.metrics.peak, "Pico simultáneo", "text-orange-600 bg-orange-50"],
              [
                Gauge,
                session.metrics.average ?? "No disponible",
                "Promedio simultáneo",
                "text-slate-600 bg-slate-100",
              ],
              [
                Eye,
                session.metrics.uniqueViewers ?? "No disponible",
                "Espectadores únicos",
                "text-sky-600 bg-sky-50",
              ],
            ] as const;
            return (
              <article
                key={session.id}
                className="overflow-hidden rounded-2xl border border-line bg-white shadow-sm"
              >
                <div className="flex flex-col gap-4 border-b border-line p-5 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-3">
                    <span className="grid size-11 place-items-center rounded-xl bg-slate-100 text-slate-600">
                      <Music2 size={20} />
                    </span>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <strong className="text-sm">{session.account}</strong>
                        <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold uppercase text-slate-500">
                          Finalizado
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted">
                        {hostLabel(session)} · {session.startedAt}–{session.endedAt} ·{" "}
                        {session.duration}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={!canExport}
                    title={canExport ? undefined : "Tu rol no permite descargar comentarios"}
                    onClick={() => void onExport(session)}
                    className="inline-flex w-fit items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-bold text-white hover:bg-emerald-700"
                  >
                    <FileSpreadsheet size={16} /> Descargar reporte
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-3 lg:grid-cols-5">
                  {metrics.map(([Icon, value, label, color]) => {
                    const MetricIcon = Icon as typeof Phone;
                    return (
                      <div key={label} className="bg-white p-4">
                        <span className={`grid size-8 place-items-center rounded-lg ${color}`}>
                          <MetricIcon size={16} />
                        </span>
                        <strong className="mt-3 block text-xl">{value}</strong>
                        <span className="mt-1 block text-[11px] leading-4 text-muted">{label}</span>
                      </div>
                    );
                  })}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function MarketingDashboard({ initialView = "Resumen" }: { initialView?: MarketingView }) {
  const { user, logout } = useAuth();
  const [view, setView] = useState<MarketingView>(initialView);
  const { summary, lives, error: boardError } = useBoard(true);
  const now = useNow();
  const unassigned = { length: summary?.unassigned ?? 0 };
  const teamAgents = (summary?.agents ?? []).map((agent) => agent.name);
  const statsOf = (name: string) => summary?.agents.find((agent) => agent.name === name);
  const activeLives = lives.filter((live) => live.status === "live");
  const finishedSessions = lives.filter((live) => live.status === "finished").map(toLiveSession);
  const canExport = (user?.permissions ?? []).includes("export");
  const [exportError, setExportError] = useState("");
  const exportLive = async (session: LiveSession) => {
    setExportError("");
    try {
      await downloadLiveComments(session.id);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "No se pudo descargar el archivo.");
    }
  };

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-[68px] max-w-[1400px] items-center justify-between px-4 sm:px-6">
          <Logo />
          <nav className="hidden items-center gap-1 lg:flex">
            {(["Resumen", "Equipo", "Transmisiones", "Alertas"] as MarketingView[]).map((item) => (
              <button
                type="button"
                key={item}
                onClick={() => setView(item)}
                className={`rounded-xl px-4 py-2.5 text-sm font-semibold transition ${
                  view === item ? "bg-primary-soft text-primary" : "text-muted hover:bg-slate-50"
                }`}
              >
                {item}
              </button>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <NotificationBell onOpenAlerts={() => setView("Alertas")} />
            <span className="hidden rounded-full bg-violet-50 px-3 py-1.5 text-[11px] font-bold text-violet-700 sm:inline-flex">
              {ROLE_LABEL[user?.role ?? ""] ?? "Marketing"}
            </span>
            <button
              type="button"
              onClick={logout}
              className="flex items-center gap-3 rounded-xl p-1.5 pr-3 hover:bg-slate-100"
            >
              <span className="grid size-9 place-items-center rounded-xl bg-primary-soft text-xs font-bold text-primary">
                {user?.name.slice(0, 2).toUpperCase()}
              </span>
              <span className="hidden text-left sm:block">
                <span className="block text-sm font-semibold">{user?.name}</span>
                <span className="block text-[11px] text-muted">
                  {ROLE_LABEL[user?.role ?? ""] ?? "Marketing"}
                </span>
              </span>
              <LogOut size={16} className="text-muted" />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 sm:py-8">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-primary">
              Supervisión operativa
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
              Bienvenid@, {user?.name}
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
              Revisa la atención del equipo y las transmisiones. Las métricas de marketing,
              conversión y campañas permanecen centralizadas en Medical 360.
            </p>
          </div>
          <span className="inline-flex w-fit items-center gap-2 rounded-full bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700">
            <span className="size-2 rounded-full bg-emerald-500" /> Datos en tiempo real
          </span>
        </div>

        {boardError && (
          <p
            role="alert"
            className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {boardError}
          </p>
        )}

        <div className="mt-6 flex gap-2 overflow-x-auto lg:hidden">
          {(["Resumen", "Equipo", "Transmisiones", "Alertas"] as MarketingView[]).map((item) => (
            <button
              type="button"
              key={item}
              onClick={() => setView(item)}
              className={`whitespace-nowrap rounded-xl px-4 py-2.5 text-sm font-semibold ${
                view === item ? "bg-primary text-white" : "border border-line bg-white text-muted"
              }`}
            >
              {item}
            </button>
          ))}
        </div>

        <div className="mt-6 flex items-start gap-3 rounded-2xl border border-violet-200 bg-violet-50 p-5">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white text-violet-600">
            <Sparkles size={19} />
          </span>
          <div>
            <strong className="text-sm text-violet-900">Analítica disponible en Medical 360</strong>
            <p className="mt-1 text-xs leading-5 text-violet-700">
              Esta vista evita duplicar KPIs de campañas. Aquí solo se muestra el estado necesario
              para supervisar la operación del call center.
            </p>
          </div>
        </div>

        {view === "Resumen" && (
          <>
            <div className="mt-6 grid gap-4 lg:grid-cols-[1.2fr_.8fr]">
              <section className="rounded-[24px] bg-deep p-6 text-white">
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-2 text-xs font-bold tracking-wider text-cyan-300">
                    <span
                      className={`size-2 rounded-full bg-cyan-300 ${activeLives.length ? "animate-pulse" : "opacity-40"}`}
                    />
                    {activeLives.length ? "LIVE ACTIVO" : "SIN LIVE ACTIVO"}
                  </span>
                  <span className="font-mono text-sm text-cyan-100">
                    {activeLives[0] ? elapsed(activeLives[0].started_at, now) : "--:--:--"}
                  </span>
                </div>
                <div className="mt-7 flex items-center">
                  <span className="grid size-12 place-items-center rounded-2xl bg-white text-ink">
                    <Music2 size={21} />
                  </span>
                  <span className="ml-4 flex-1">
                    <strong className="block text-lg">
                      {activeLives[0]?.account ?? "Sin transmisión"}
                    </strong>
                    <span className="mt-1 block text-xs text-slate-400">
                      {activeLives[0]
                        ? `${activeLives[0].tiktoker ?? "Sin asignar"} · monitoreo activo`
                        : "Esperando que una cuenta salga en vivo"}
                    </span>
                  </span>
                  <span className="rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold">
                    TikTok
                  </span>
                </div>
              </section>
              <section className="rounded-[24px] border border-amber-200 bg-amber-50 p-6">
                <span className="grid size-11 place-items-center rounded-xl bg-white text-amber-600">
                  <BellRing size={20} />
                </span>
                <strong className="mt-5 block text-lg">{unassigned.length} sin asignar</strong>
                <p className="mt-1 text-sm leading-6 text-muted">
                  Pacientes con teléfono que todavía no pertenecen a ningún agente.
                </p>
              </section>
            </div>

            <section className="mt-6 overflow-hidden rounded-2xl border border-line bg-white">
              <div className="flex items-center justify-between border-b border-line p-5">
                <div>
                  <h2 className="text-base font-bold">Estado del equipo</h2>
                  <p className="mt-1 text-xs text-muted">Carga actual, no métricas de marketing.</p>
                </div>
                <span className="rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-bold text-emerald-700">
                  {teamAgents.length} agentes
                </span>
              </div>
              <div className="divide-y divide-line">
                {teamAgents.map((agent) => {
                  const assigned = { length: statsOf(agent)?.assigned ?? 0 };
                  const contacted = { length: statsOf(agent)?.contacted ?? 0 };
                  return (
                    <div
                      key={agent}
                      className="grid gap-3 px-5 py-4 sm:grid-cols-[1fr_auto_auto_auto] sm:items-center"
                    >
                      <div className="flex items-center gap-3">
                        <span className="grid size-9 place-items-center rounded-xl bg-primary-soft text-xs font-bold text-primary">
                          {agent.slice(0, 2).toUpperCase()}
                        </span>
                        <span>
                          <strong className="block text-sm">{agent}</strong>
                          <span className="text-[11px] text-muted">Agente</span>
                        </span>
                      </div>
                      <span className="text-xs text-muted">{assigned.length} asignados</span>
                      <span className="text-xs text-muted">{contacted.length} contactados</span>
                      <span className="text-xs font-semibold text-primary">Actividad reciente</span>
                    </div>
                  );
                })}
              </div>
            </section>
          </>
        )}

        {view === "Equipo" && (
          <section className="mt-6">
            <div>
              <h2 className="text-xl font-bold">Disponibilidad del equipo</h2>
              <p className="mt-1 text-sm text-muted">
                Consulta quién tiene cada seguimiento sin intervenir en la gestión del agente.
              </p>
            </div>
            <div className="mt-5 grid gap-4 md:grid-cols-3">
              {teamAgents.map((agent) => {
                const assigned = { length: statsOf(agent)?.assigned ?? 0 };
                const pending = { length: statsOf(agent)?.pending ?? 0 };
                return (
                  <article key={agent} className="rounded-2xl border border-line bg-white p-5">
                    <div className="flex items-center justify-between">
                      <span className="grid size-11 place-items-center rounded-xl bg-primary-soft font-bold text-primary">
                        {agent.slice(0, 2).toUpperCase()}
                      </span>
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-600">
                        Agente
                      </span>
                    </div>
                    <h3 className="mt-4 font-bold">{agent}</h3>
                    <p className="mt-1 text-xs text-muted">Agente call center</p>
                    <div className="mt-5 grid grid-cols-2 gap-2">
                      <div className="rounded-xl bg-slate-50 p-3">
                        <strong className="block text-lg">{assigned.length}</strong>
                        <span className="text-[11px] text-muted">Asignados</span>
                      </div>
                      <div className="rounded-xl bg-amber-50 p-3">
                        <strong className="block text-lg text-amber-700">{pending.length}</strong>
                        <span className="text-[11px] text-muted">Pendientes</span>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        )}

        {view === "Alertas" && <AlertsPanel />}

        {view === "Transmisiones" && (
          <section className="mt-6">
            <div>
              <h2 className="text-xl font-bold">Transmisiones monitoreadas</h2>
              <p className="mt-1 text-sm text-muted">
                Estado y disponibilidad de reportes. La analítica detallada vive en Medical 360.
              </p>
            </div>
            <div className="mt-5 space-y-3">
              {activeLives.map((live) => (
                <article
                  key={live.id}
                  className="flex flex-col gap-4 rounded-2xl border border-emerald-200 bg-white p-5 sm:flex-row sm:items-center"
                >
                  <span className="grid size-11 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
                    <Activity size={20} />
                  </span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <strong className="text-sm">{live.account}</strong>
                      <span className="rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-bold text-emerald-700">
                        En vivo
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      {live.tiktoker ?? "Sin asignar"}
                      {live.responsible_note ? ` (${HOST_NOTES[live.responsible_note]})` : ""} ·
                      iniciado {lima(live.started_at)}
                    </p>
                  </div>
                  <span className="text-xs font-semibold text-muted">
                    Reporte pendiente de cierre
                  </span>
                </article>
              ))}
              {!lives.length && (
                <p className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-muted">
                  Todavía no hay transmisiones registradas.
                </p>
              )}
            </div>
            <LiveHistory
              sessions={finishedSessions}
              canExport={canExport}
              onExport={(session) => void exportLive(session)}
              error={exportError}
            />
          </section>
        )}
      </main>

      <nav className="sticky bottom-0 z-30 border-t border-line bg-white px-3 py-2 lg:hidden">
        <div className="mx-auto flex max-w-sm justify-around">
          {(["Resumen", "Equipo", "Transmisiones", "Alertas"] as MarketingView[]).map((item, index) => {
            const Icon = index === 0 ? Activity : index === 1 ? Users : index === 2 ? Music2 : Bell;
            return (
              <button
                type="button"
                key={item}
                onClick={() => setView(item)}
                className={`flex flex-col items-center gap-1 rounded-xl px-3 py-1.5 text-[11px] font-semibold ${
                  view === item ? "text-primary" : "text-muted"
                }`}
              >
                <Icon size={20} />
                {item}
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

function AgentDashboard({ onOpenMarketing }: { onOpenMarketing?: () => void }) {
  const { user, logout } = useAuth();
  const [view, setView] = useState<View>("Pulso");
  const [phoneOnly, setPhoneOnly] = useState(true);
  const workspace = useWorkspace(true, phoneOnly);
  const { messages, loading: inboxLoading, error: inboxError } = workspace;
  const [copiedPhoneId, setCopiedPhoneId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const permissions = user?.permissions ?? [];
  const canHistory = permissions.includes("read");
  const board = useBoard(canHistory);
  const now = useNow();
  const activeLive = board.lives.find((live) => live.status === "live");
  const [settings, setSettings] = useState({
    tiktok: true,
    instagram: true,
    smartDetection: true,
    notifications: true,
  });

  const selectedMessage = messages.find((message) => message.id === selectedId) ?? null;
  const visibleMessages = phoneOnly ? messages.filter((message) => message.phone) : messages;
  const pageSize = 8;
  const totalPages = Math.max(1, Math.ceil(workspace.total / pageSize));
  useEffect(() => {
    if (!inboxLoading) setPage((current) => Math.min(current, totalPages));
  }, [inboxLoading, totalPages]);
  const pageMessages = visibleMessages.slice((page - 1) * pageSize, page * pageSize);
  const leads = messages.filter((message) => message.type !== "Comentario");
  const currentAgent = user?.name ?? "Agente";
  const myPatients = messages.filter((message) => message.isMine);
  const myContacted = myPatients.filter((message) => message.status === "Contactado");
  const teamAgents = Array.from(
    new Set([currentAgent, ...(board.summary?.agents ?? []).map((agent) => agent.name)]),
  );
  const statsOf = (name: string) => board.summary?.agents.find((agent) => agent.name === name);

  const goToView = (nextView: View) => {
    setView(nextView);
    setPage(1);
    setSelectedId(null);
  };

  const showPriority = () => {
    setView("Bandeja");
    setPage(1);
  };

  const claimFollowUp = (id: number) => {
    void workspace.claim(id);
  };

  const updateContactStatus = (id: number, status: MessageStatus) => {
    const current = messages.find((message) => message.id === id)?.status ?? "Nuevo";
    void workspace.setStatus(id, status, current);
  };

  const copyPhone = async (id: number, phone: string) => {
    await navigator.clipboard.writeText(phone.replaceAll(" ", ""));
    setCopiedPhoneId(id);
    window.setTimeout(() => setCopiedPhoneId(null), 1800);
  };

  const kanban = (
    <section className="mt-8">
      <div>
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold tracking-tight">Pipeline de leads</h2>
            <span className="rounded-full bg-primary-soft px-2.5 py-1 text-[11px] font-bold text-primary">
              {leads.length} leads
            </span>
          </div>
          <p className="mt-1 text-sm text-muted">
            Se actualiza automáticamente cuando cambia el estado de una conversación.
          </p>
        </div>
      </div>

      <div className="mt-5 grid items-start gap-4 lg:grid-cols-3">
        {(
          [
            {
              key: "new",
              label: "Nuevos detectados",
              description: "Sin agente asignado",
              dot: "bg-slate-400",
              surface: "bg-slate-100/70",
            },
            {
              key: "assigned",
              label: "En seguimiento",
              description: "Asignados al equipo",
              dot: "bg-amber-500",
              surface: "bg-amber-50/70",
            },
            {
              key: "contacted",
              label: "Contactados",
              description: "Contacto confirmado",
              dot: "bg-emerald-500",
              surface: "bg-emerald-50/70",
            },
          ] as const
        ).map((column) => {
          const columnLeads = leads.filter((lead) => {
            if (column.key === "new") return lead.status === "Nuevo" && !lead.owner;
            if (column.key === "assigned") return lead.status === "Nuevo" && Boolean(lead.owner);
            return lead.status === "Contactado";
          });
          return (
            <div
              key={column.key}
              className={`min-h-64 rounded-2xl border border-line p-3 ${column.surface}`}
            >
              <div className="flex items-center justify-between px-2 py-2">
                <div className="flex items-center gap-2.5">
                  <span className={`size-2.5 rounded-full ${column.dot}`} />
                  <div>
                    <h3 className="text-sm font-bold">{column.label}</h3>
                    <p className="mt-0.5 text-[11px] text-muted">{column.description}</p>
                  </div>
                </div>
                <span className="grid size-7 place-items-center rounded-full bg-white text-xs font-bold text-slate-600 shadow-sm">
                  {columnLeads.length}
                </span>
              </div>

              <div className="mt-2 space-y-3">
                {columnLeads.map((lead) => (
                  <article
                    key={lead.id}
                    className="rounded-2xl border border-line bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md"
                  >
                    <button
                      type="button"
                      onClick={() => setSelectedId(lead.id)}
                      className="w-full text-left"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex min-w-0 items-center gap-2.5">
                          <span
                            className={`grid size-9 shrink-0 place-items-center rounded-xl ${
                              lead.platform === "TikTok"
                                ? "bg-slate-100 text-slate-700"
                                : "bg-violet-50 text-violet-600"
                            }`}
                          >
                            {lead.platform === "TikTok" ? (
                              <Music2 size={16} />
                            ) : (
                              <MessageCircle size={16} />
                            )}
                          </span>
                          <span className="min-w-0">
                            <strong className="block truncate text-sm">{lead.user}</strong>
                            <span className="mt-0.5 block text-[11px] text-muted">
                              {lead.platform} · {lead.enteredAt}
                            </span>
                          </span>
                        </div>
                        {lead.phone && <Phone size={15} className="shrink-0 text-amber-600" />}
                      </div>
                      <p className="mt-3 line-clamp-2 text-xs leading-5 text-slate-600">
                        {lead.message}
                      </p>
                      <div className="mt-3 flex items-center justify-between gap-2">
                        <TypeBadge type={lead.type} />
                        {lead.owner && (
                          <span className="truncate text-[11px] font-semibold text-primary">
                            {lead.owner}
                          </span>
                        )}
                      </div>
                    </button>
                  </article>
                ))}
                {!columnLeads.length && (
                  <div className="grid min-h-32 place-items-center rounded-xl border border-dashed border-slate-300 bg-white/50 p-5 text-center">
                    <div>
                      <UserPlus size={19} className="mx-auto text-slate-300" />
                      <p className="mt-2 text-xs text-muted">No hay leads en esta etapa</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );

  const table = (
    <section className="mt-7 overflow-hidden rounded-2xl border border-line bg-white shadow-sm">
      <div className="flex flex-col gap-4 border-b border-line p-5 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-primary">
              Bandeja social en vivo
            </p>
            <span className="size-2 animate-pulse rounded-full bg-emerald-500" />
          </div>
          <p className="mt-1 text-sm text-muted">
            Comentarios y mensajes directos de todas las cuentas conectadas
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setPhoneOnly(true);
              setPage(1);
            }}
            className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${
              phoneOnly
                ? "bg-primary text-white"
                : "border border-amber-200 bg-amber-50 text-amber-700"
            }`}
          >
            Con teléfono
          </button>
          <button
            type="button"
            onClick={() => {
              setPhoneOnly(false);
              setPage(1);
            }}
            className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${
              !phoneOnly ? "bg-primary text-white" : "bg-sky-50 text-sky-700"
            }`}
          >
            Ver todos
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1440px] border-collapse text-left">
          <thead>
            <tr className="border-b border-line bg-slate-50 text-[10px] font-bold uppercase tracking-[0.05em] text-slate-500">
              <th className="px-5 py-4">Cuenta</th>
              <th className="px-4 py-4">Origen</th>
              <th className="px-4 py-4">Usuario</th>
              <th className="px-4 py-4">Responsable del Live</th>
              <th className="w-[30%] px-4 py-4">Mensaje / comentario</th>
              <th className="px-4 py-4">Teléfono detectado</th>
              <th className="px-4 py-4">Tipo</th>
              <th className="px-4 py-4">Agente</th>
              <th className="px-4 py-4">Estado de contacto</th>
              <th className="px-4 py-4">Hora de ingreso</th>
            </tr>
          </thead>
          <tbody>
            {pageMessages.map((item) => (
              <tr
                key={item.id}
                onClick={() => setSelectedId(item.id)}
                className={`cursor-pointer border-b border-slate-100 text-xs transition last:border-0 hover:bg-sky-50/70 ${
                  selectedId === item.id ? "bg-sky-50" : ""
                }`}
              >
                <td className="whitespace-nowrap px-5 py-4 font-bold text-primary">
                  {item.account}
                </td>
                <td className="px-4 py-4">
                  <span
                    className={`inline-flex whitespace-nowrap rounded-full px-3 py-1.5 font-bold ${
                      item.source === "Mensaje directo"
                        ? "bg-violet-50 text-violet-700"
                        : "bg-teal-100 text-teal-700"
                    }`}
                  >
                    {item.source === "Mensaje directo" ? `DM ${item.platform}` : "Comentario LIVE"}
                  </span>
                </td>
                <td className="whitespace-nowrap px-4 py-4 font-bold text-primary">{item.user}</td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-600">{item.liveHost}</td>
                <td className="px-4 py-4 text-[13px] leading-5 text-slate-700">{item.message}</td>
                <td className="whitespace-nowrap px-4 py-4">
                  {item.phone ? (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void copyPhone(item.id, item.phone!);
                      }}
                      className="inline-flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-2.5 py-1.5 font-bold text-amber-700 transition hover:bg-amber-100"
                    >
                      {copiedPhoneId === item.id ? (
                        <ClipboardCheck size={13} />
                      ) : (
                        <Copy size={13} />
                      )}
                      {copiedPhoneId === item.id ? "Copiado" : item.phone}
                    </button>
                  ) : (
                    <span className="text-slate-400">No detectado</span>
                  )}
                </td>
                <td className="px-4 py-4">
                  <TypeBadge type={item.type} />
                </td>
                <td className="px-4 py-4">
                  {item.owner ? (
                    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-primary-soft px-2.5 py-1 font-bold text-primary">
                      <CircleUserRound size={13} /> {item.owner}
                    </span>
                  ) : (
                    <span className="text-slate-400">Disponible</span>
                  )}
                </td>
                <td className="px-4 py-4">
                  <select
                    value={item.status}
                    disabled={Boolean(item.owner && !item.isMine)}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => {
                      event.stopPropagation();
                      updateContactStatus(item.id, event.target.value as MessageStatus);
                    }}
                    className={`rounded-xl border px-3 py-2 text-xs font-bold outline-none disabled:cursor-not-allowed disabled:opacity-50 ${
                      item.status === "Contactado"
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                        : "border-amber-200 bg-amber-50 text-amber-700"
                    }`}
                  >
                    <option>Nuevo</option>
                    <option>Contactado</option>
                  </select>
                </td>
                <td className="px-4 py-4">
                  <div>
                    <span className="whitespace-nowrap font-mono text-slate-500">
                      {item.enteredAt}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!pageMessages.length && (
          <div className="grid place-items-center px-5 py-16 text-center text-muted">
            <Search size={28} className="mb-3 text-slate-300" />
            <p className="text-sm">
              {inboxLoading
                ? "Cargando conversaciones…"
                : inboxError
                  ? "No se pudo cargar la bandeja. Se reintentará automáticamente."
                  : messages.length === 0
                    ? "Todavía no hay conversaciones capturadas."
                    : "No encontramos conversaciones con estos filtros."}
            </p>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-3 border-t border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted">
          Mostrando {pageMessages.length} de {workspace.total} conversaciones
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page === 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            className="grid size-9 place-items-center rounded-lg border border-line text-muted hover:text-primary disabled:opacity-30"
          >
            <ArrowLeft size={16} />
          </button>
          <span className="px-2 text-xs font-semibold text-muted">
            Página {page} de {totalPages}
          </span>
          <button
            type="button"
            disabled={page === totalPages || inboxLoading}
            onClick={async () => {
              if (page * pageSize >= visibleMessages.length && workspace.hasMore) {
                if (!(await workspace.loadMore())) return;
              }
              setPage((current) => Math.min(totalPages, current + 1));
            }}
            className="grid size-9 place-items-center rounded-lg border border-line text-muted hover:text-primary disabled:opacity-30"
          >
            <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </section>
  );

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-[68px] max-w-[1500px] items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-2">
            <Logo />
          </div>
          <nav className="hidden items-center gap-1 lg:flex">
            {(["Pulso", "Bandeja", "Contactos", "Ajustes"] as View[]).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => goToView(item)}
                className={`rounded-xl px-4 py-2.5 text-sm font-semibold transition ${
                  view === item ? "bg-primary-soft text-primary" : "text-muted hover:bg-slate-50"
                }`}
              >
                {item}
              </button>
            ))}
          </nav>
          <div className="relative flex items-center gap-2">
            <NotificationBell onOpenInbox={showPriority} onOpenAlerts={onOpenMarketing} />
            <button
              type="button"
              onClick={logout}
              className="ml-1 flex items-center gap-3 rounded-xl p-1.5 pr-3 hover:bg-slate-100"
              title="Cerrar sesión"
            >
              <span className="grid size-9 place-items-center rounded-xl bg-primary-soft text-xs font-bold text-primary">
                {user?.name.slice(0, 2).toUpperCase()}
              </span>
              <span className="hidden text-left sm:block">
                <span className="block text-sm font-semibold">{user?.name}</span>
                <span className="block text-[11px] text-muted">
                  {ROLE_LABEL[user?.role ?? ""] ?? "Agente call center"}
                </span>
              </span>
              <LogOut size={16} className="text-muted" />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1500px] px-4 py-6 sm:px-6 sm:py-8">
        {(view === "Pulso" || view === "Bandeja") && (
          <>
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-primary">
                  {view === "Pulso" ? "Inicio agente" : "Operaciones"}
                </p>
                <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
                  {view === "Pulso" ? `Bienvenid@, ${currentAgent}` : "Bandeja social"}
                </h1>
                <p className="mt-2 text-sm text-muted">
                  {view === "Pulso"
                    ? `Tienes ${myPatients.filter((item) => item.status === "Nuevo").length} seguimientos pendientes. Aquí puedes revisar tu trabajo del día.`
                    : "Copia teléfonos, toma seguimientos y registra contactos realizados."}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700">
                  <span className="size-2 rounded-full bg-emerald-500" /> Datos en tiempo real
                </span>
              </div>
            </div>

            {inboxError && (
              <p
                role="alert"
                className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
              >
                {inboxError}
              </p>
            )}
            {inboxLoading && <p className="mt-4 text-sm text-muted">Cargando tu bandeja…</p>}

            {view === "Pulso" && (
              <>
                <div className="mt-7 grid gap-4 lg:grid-cols-[1.45fr_1fr]">
                  <button
                    type="button"
                    onClick={() => setView("Bandeja")}
                    className="rounded-[24px] bg-deep p-6 text-left text-white shadow-xl shadow-slate-300/30"
                  >
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center gap-2 text-xs font-bold tracking-wider text-cyan-300">
                        <span className="size-2 animate-pulse rounded-full bg-cyan-300" />
                        {activeLive ? "EN VIVO" : "SIN LIVE ACTIVO"}
                      </span>
                      <span className="font-mono text-sm text-cyan-100">
                        {activeLive ? elapsed(activeLive.started_at, now) : "--:--:--"}
                      </span>
                    </div>
                    <div className="mt-7 flex items-center">
                      <span className="grid size-12 place-items-center rounded-2xl bg-white text-ink">
                        <Music2 size={21} />
                      </span>
                      <span className="ml-4 min-w-0 flex-1">
                        <strong className="block truncate text-lg">
                          {activeLive?.account ?? "Sin transmisión"}
                        </strong>
                        <span className="mt-1 block text-xs text-slate-400">
                          {activeLive
                            ? `Transmitiendo con ${activeLive.tiktoker ?? "nadie asignado"}${
                                activeLive.responsible_note
                                  ? ` (${HOST_NOTES[activeLive.responsible_note]})`
                                  : ""
                              }`
                            : "Esperando que una cuenta salga en vivo"}
                        </span>
                      </span>
                      <ChevronRight className="text-slate-500" />
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={showPriority}
                    className="flex items-center rounded-[24px] border border-amber-200 bg-amber-50 p-6 text-left transition hover:border-amber-300"
                  >
                    <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-white text-amber-600 shadow-sm">
                      <Zap size={21} />
                    </span>
                    <span className="ml-4 flex-1">
                      <strong className="block text-sm">
                        {
                          messages.filter(
                            (item) => item.phone && item.status === "Nuevo" && !item.owner,
                          ).length
                        }{" "}
                        pacientes disponibles
                      </strong>
                      <span className="mt-1 block text-xs leading-5 text-muted">
                        Con teléfono y sin agente asignado
                      </span>
                    </span>
                    <ArrowRight size={19} className="text-amber-600" />
                  </button>
                </div>
                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  {[
                    [
                      Phone,
                      messages.filter((item) => item.phone).length,
                      "Teléfonos detectados",
                      "bg-primary-soft text-primary",
                    ],
                    [
                      UserPlus,
                      myPatients.length,
                      "Mis seguimientos",
                      "bg-violet-50 text-violet-600",
                    ],
                    [
                      ClipboardCheck,
                      myContacted.length,
                      "Contactados por mí",
                      "bg-emerald-50 text-emerald-600",
                    ],
                    [
                      Users,
                      messages.filter((item) => item.status === "Nuevo" && item.owner).length,
                      "Pendientes del equipo",
                      "bg-amber-50 text-amber-600",
                    ],
                  ].map(([Icon, value, label, color]) => {
                    const MetricIcon = Icon as typeof MessageCircle;
                    return (
                      <article
                        key={label as string}
                        className="rounded-2xl border border-line bg-white p-5"
                      >
                        <span className={`grid size-10 place-items-center rounded-xl ${color}`}>
                          <MetricIcon size={19} />
                        </span>
                        <strong className="mt-5 block text-2xl">{value as number}</strong>
                        <span className="mt-1 block text-xs text-muted">{label as string}</span>
                      </article>
                    );
                  })}
                </div>
                <section className="mt-4 rounded-2xl border border-line bg-white p-5">
                  <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
                    <div>
                      <h2 className="text-sm font-bold">Actividad del equipo</h2>
                      <p className="mt-1 text-xs text-muted">
                        Cada seguimiento pertenece a un solo agente.
                      </p>
                    </div>
                    <span className="w-fit rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold text-slate-600">
                      {(board.summary?.agents ?? []).reduce((n, agent) => n + agent.assigned, 0)}{" "}
                      asignados
                    </span>
                  </div>
                  <div className="mt-5 grid gap-3 sm:grid-cols-3">
                    {teamAgents.map((agent) => {
                      const assigned = { length: statsOf(agent)?.assigned ?? 0 };
                      const contacted = { length: statsOf(agent)?.contacted ?? 0 };
                      const rate = assigned.length
                        ? Math.round((contacted.length / assigned.length) * 100)
                        : 0;
                      return (
                        <div
                          key={agent}
                          className={`rounded-xl border p-4 ${
                            agent === currentAgent
                              ? "border-primary/30 bg-primary-soft/40"
                              : "border-line bg-slate-50"
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <strong className="text-sm">
                              {agent}
                              {agent === currentAgent && (
                                <span className="ml-1 text-[10px] text-primary">(Tú)</span>
                              )}
                            </strong>
                            <span className="text-xs font-bold text-primary">{rate}%</span>
                          </div>
                          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-200">
                            <div
                              className="h-full rounded-full bg-primary"
                              style={{ width: `${rate}%` }}
                            />
                          </div>
                          <p className="mt-3 text-[11px] text-muted">
                            {contacted.length} contactados · {assigned.length} asignados
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </section>
                {kanban}
              </>
            )}
            {view === "Bandeja" && table}
          </>
        )}

        {view === "Contactos" && (
          <section>
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-primary">
                  Seguimiento
                </p>
                <h1 className="mt-2 text-3xl font-bold tracking-tight">Contactos detectados</h1>
                <p className="mt-2 text-sm text-muted">
                  Personas con intención identificada, sin convertir esto en un CRM complejo.
                </p>
              </div>
            </div>
            <div className="mt-7 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {leads.map((lead) => (
                <button
                  type="button"
                  key={lead.id}
                  onClick={() => {
                    setSelectedId(lead.id);
                    setView("Bandeja");
                  }}
                  className="rounded-2xl border border-line bg-white p-5 text-left transition hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-lg"
                >
                  <div className="flex items-start justify-between">
                    <span className="grid size-11 place-items-center rounded-xl bg-primary-soft text-primary">
                      <CircleUserRound size={21} />
                    </span>
                    {lead.owner ? (
                      <span className="rounded-full bg-primary-soft px-2.5 py-1 text-[11px] font-bold text-primary">
                        {lead.owner}
                      </span>
                    ) : (
                      <TypeBadge type={lead.type} />
                    )}
                  </div>
                  <strong className="mt-4 block text-sm">{lead.user}</strong>
                  <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted">{lead.message}</p>
                  <div className="mt-4 flex items-center justify-between">
                    <span className="text-[11px] text-muted">{lead.platform}</span>
                    <span className="text-xs font-semibold text-primary">
                      {lead.phone ?? "Sin teléfono"}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}

        {view === "Ajustes" && (
          <section className="mx-auto max-w-3xl">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-primary">
              Configuración
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight">Fuentes y automatización</h1>
            <p className="mt-2 text-sm text-muted">
              Controla qué canales alimentan el monitor y cómo se detectan oportunidades.
            </p>
            <div className="mt-7 overflow-hidden rounded-2xl border border-line bg-white">
              {[
                ["tiktok", Music2, "TikTok LIVE", "Comentarios y actividad de transmisiones"],
                ["instagram", MessageCircle, "Instagram", "Mensajes directos de la cuenta"],
                [
                  "smartDetection",
                  Sparkles,
                  "Detección inteligente",
                  "Intención, teléfonos y prioridad",
                ],
                ["notifications", Bell, "Alertas operativas", "Avisos de contactos por gestionar"],
              ].map(([key, Icon, title, description]) => {
                const SettingIcon = Icon as typeof Music2;
                const enabled = settings[key as keyof typeof settings];
                return (
                  <div
                    key={key as string}
                    className="flex items-center gap-4 border-b border-line p-5 last:border-0"
                  >
                    <span className="grid size-10 place-items-center rounded-xl bg-primary-soft text-primary">
                      <SettingIcon size={19} />
                    </span>
                    <span className="flex-1">
                      <strong className="block text-sm">{title as string}</strong>
                      <span className="mt-1 block text-xs text-muted">{description as string}</span>
                    </span>
                    <button
                      type="button"
                      aria-label={`${enabled ? "Desactivar" : "Activar"} ${title}`}
                      onClick={() =>
                        setSettings((current) => ({ ...current, [key as string]: !enabled }))
                      }
                      className={`relative h-7 w-12 rounded-full transition ${
                        enabled ? "bg-primary" : "bg-slate-300"
                      }`}
                    >
                      <span
                        className={`absolute top-1 size-5 rounded-full bg-white shadow-sm transition ${
                          enabled ? "left-6" : "left-1"
                        }`}
                      />
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="mt-5 rounded-2xl border border-sky-200 bg-sky-50 p-5">
              <div className="flex gap-3">
                <SlidersHorizontal size={20} className="mt-0.5 text-primary" />
                <div>
                  <strong className="text-sm">Preparado para FastAPI</strong>
                  <p className="mt-1 text-xs leading-5 text-muted">
                    Los controles son locales por ahora. Al conectar el backend podrán persistirse
                    por cuenta y usuario.
                  </p>
                </div>
              </div>
            </div>
          </section>
        )}
        {workspace.hasMore && view !== "Bandeja" && view !== "Ajustes" && (
          <button
            type="button"
            className="primary-button mt-5"
            onClick={() => void workspace.loadMore()}
          >
            Cargar más conversaciones
          </button>
        )}
      </main>

      {selectedMessage && (
        <>
          <button
            type="button"
            aria-label="Cerrar detalle"
            onClick={() => setSelectedId(null)}
            className="fixed inset-0 z-40 cursor-default bg-slate-950/20 backdrop-blur-[1px]"
          />
          <aside className="fixed bottom-0 right-0 top-0 z-50 w-full max-w-md overflow-y-auto border-l border-line bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-primary">
                  Conversación
                </p>
                <h2 className="mt-1 text-xl font-bold">{selectedMessage.user}</h2>
              </div>
              <button
                type="button"
                onClick={() => setSelectedId(null)}
                className="grid size-9 place-items-center rounded-xl bg-slate-100 text-muted"
              >
                <X size={18} />
              </button>
            </div>
            <div className="mt-6 rounded-2xl bg-slate-50 p-5">
              <div className="flex items-center justify-between">
                <TypeBadge type={selectedMessage.type} />
                <span className="text-xs text-muted">{selectedMessage.enteredAt}</span>
              </div>
              <p className="mt-4 text-sm leading-6 text-slate-700">{selectedMessage.message}</p>
            </div>
            <dl className="mt-6 grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-xs text-muted">Cuenta</dt>
                <dd className="mt-1 font-semibold text-primary">{selectedMessage.account}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Origen</dt>
                <dd className="mt-1 font-semibold">
                  {selectedMessage.source === "Mensaje directo"
                    ? `DM ${selectedMessage.platform}`
                    : "Comentario LIVE"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Responsable</dt>
                <dd className="mt-1 font-semibold">{selectedMessage.liveHost}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Teléfono</dt>
                <dd className="mt-1">
                  {selectedMessage.phone ? (
                    <button
                      type="button"
                      onClick={() => void copyPhone(selectedMessage.id, selectedMessage.phone!)}
                      className="inline-flex items-center gap-2 font-semibold text-primary"
                    >
                      {copiedPhoneId === selectedMessage.id ? (
                        <ClipboardCheck size={15} />
                      ) : (
                        <Copy size={15} />
                      )}
                      {copiedPhoneId === selectedMessage.id
                        ? "Número copiado"
                        : selectedMessage.phone}
                    </button>
                  ) : (
                    <span className="font-semibold">No detectado</span>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Primer contacto</dt>
                <dd className="mt-1 font-semibold">
                  {selectedMessage.contactedAt
                    ? `${selectedMessage.contactedAt}${
                        selectedMessage.contactSeconds !== undefined
                          ? ` · ${Math.max(1, Math.round(selectedMessage.contactSeconds / 60))} min después de la captura`
                          : ""
                      }`
                    : "Pendiente"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Agente asignado</dt>
                <dd className="mt-1 font-semibold">
                  {selectedMessage.owner ?? "Disponible para seguimiento"}
                </dd>
              </div>
            </dl>
            <div className="mt-7 rounded-2xl border border-line bg-slate-50 p-4">
              <label className="flex items-center justify-between gap-4">
                <span>
                  <span className="block text-xs font-bold uppercase tracking-wider text-muted">
                    Estado de contacto
                  </span>
                  <span className="mt-1 block text-[11px] text-muted">
                    Solo indica si ya se realizó el contacto.
                  </span>
                </span>
                <select
                  value={selectedMessage.status}
                  disabled={Boolean(selectedMessage.owner && !selectedMessage.isMine)}
                  onChange={(event) =>
                    updateContactStatus(selectedMessage.id, event.target.value as MessageStatus)
                  }
                  className={`rounded-xl border px-3 py-2 text-xs font-bold outline-none disabled:cursor-not-allowed disabled:opacity-50 ${
                    selectedMessage.status === "Contactado"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-amber-200 bg-amber-50 text-amber-700"
                  }`}
                >
                  <option>Nuevo</option>
                  <option>Contactado</option>
                </select>
              </label>
            </div>
            {selectedMessage.phone && (
              <a
                href={`tel:${selectedMessage.phone.replaceAll(" ", "")}`}
                className="mt-7 flex h-12 items-center justify-center gap-2 rounded-xl bg-primary text-sm font-bold text-white"
              >
                <Phone size={17} /> Llamar al contacto
              </a>
            )}
            <button
              type="button"
              disabled={Boolean(selectedMessage.owner)}
              onClick={() => claimFollowUp(selectedMessage.id)}
              className={`mt-3 flex h-12 w-full items-center justify-center gap-2 rounded-xl border text-sm font-bold transition ${
                selectedMessage.isMine
                  ? "border-primary bg-primary-soft text-primary"
                  : selectedMessage.owner
                    ? "border-line bg-slate-50 text-slate-400"
                    : "border-line text-slate-600 hover:border-primary/30"
              }`}
            >
              <UserPlus size={17} />
              {selectedMessage.isMine
                ? "Asignado a mí"
                : selectedMessage.owner
                  ? `Asignado a ${selectedMessage.owner}`
                  : "Tomar seguimiento"}
            </button>
            <p className="mt-3 text-center text-[11px] leading-5 text-muted">
              Al tomar el seguimiento, este paciente cuenta en tus KPIs y queda reservado para ti.
            </p>
          </aside>
        </>
      )}

      <nav className="sticky bottom-0 z-30 border-t border-line bg-white px-3 py-2 lg:hidden">
        <div className="mx-auto flex max-w-md justify-around">
          {[
            [Activity, "Pulso"],
            [MessagesSquare, "Bandeja"],
            [Users, "Contactos"],
            [Settings, "Ajustes"],
          ].map(([Icon, label]) => {
            const NavIcon = Icon as typeof Activity;
            const active = view === label;
            return (
              <button
                type="button"
                key={label as string}
                onClick={() => goToView(label as View)}
                className={`flex min-w-16 flex-col items-center gap-1 rounded-xl px-2 py-1.5 text-[11px] font-semibold ${
                  active ? "text-primary" : "text-muted"
                }`}
              >
                <NavIcon size={20} />
                {label as string}
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

/**
 * Which screen a person sees is decided by the backend role (/api/auth/me), never by the
 * browser: agente_ventas -> own profile; gerente / jefe_marketing -> marketing;
 * supervisor -> both, with a switch to diagnose problems.
 */
export function Dashboard() {
  const { user } = useAuth();
  const screens = user?.screens ?? [];
  const [marketingStart, setMarketingStart] = useState<MarketingView>("Resumen");
  const [current, setCurrent] = useState<"agent" | "marketing">(
    screens.includes("marketing") && !screens.includes("agent") ? "marketing" : "agent",
  );

  if (!user || screens.length === 0) {
    return (
      <main className="grid min-h-screen place-items-center bg-canvas p-6 text-center text-sm text-muted">
        {user?.reason ?? "Tu usuario aún no tiene una pantalla asignada."} Pide a un administrador
        que te asigne un rol en Clerk y vuelve a iniciar sesión.
      </main>
    );
  }
  if (screens.length === 1) {
    return screens[0] === "marketing" ? <MarketingDashboard /> : <AgentDashboard />;
  }
  return (
    <>
      <div className="fixed bottom-4 right-4 z-50 flex gap-1 rounded-full border border-line bg-white p-1 shadow-lg">
        {(["agent", "marketing"] as const).map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setCurrent(name)}
            className={`rounded-full px-4 py-2 text-xs font-bold ${
              current === name ? "bg-primary text-white" : "text-muted hover:text-ink"
            }`}
          >
            {name === "agent" ? "Vista agente" : "Vista marketing"}
          </button>
        ))}
      </div>
      {current === "marketing" ? (
        <MarketingDashboard key={marketingStart} initialView={marketingStart} />
      ) : (
        <AgentDashboard
          onOpenMarketing={() => {
            setMarketingStart("Alertas");
            setCurrent("marketing");
          }}
        />
      )}
    </>
  );
}
