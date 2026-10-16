import { useCallback, useEffect, useState } from "react";
import { Bell, BellRing, ShieldAlert, X } from "lucide-react";
import { fetchNotifications, Notifications } from "./api";

const POLL_MS = 30000;

/**
 * The bell. Each role receives only its own notifications from the server:
 * - sales agents: reminders about their pending chats (never alerts);
 * - supervisor / marketing head / manager: alerts and "no me contactan" comments.
 */
export function NotificationBell({
  onOpenInbox,
  onOpenAlerts,
}: {
  onOpenInbox?: () => void;
  onOpenAlerts?: () => void;
}) {
  const [data, setData] = useState<Notifications | null>(null);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await fetchNotifications());
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const agent = data?.agent ?? null;
  const alerts = data?.alerts ?? null;
  const items: { key: string; tone: string; title: string; detail: string; go?: () => void }[] =
    [];

  if (agent && agent.mine_over_first > 0) {
    const second = agent.mine_over_second;
    items.push({
      key: "mine",
      tone: second > 0 ? "red" : "amber",
      title: `Tienes ${agent.mine_over_first} chat${agent.mine_over_first === 1 ? "" : "s"} pendiente${agent.mine_over_first === 1 ? "" : "s"}`,
      detail:
        `Llevan más de ${agent.first_minutes} min sin contactar` +
        (second > 0 ? `; ${second} más de ${agent.second_minutes} min.` : "."),
      go: onOpenInbox,
    });
  }
  if (agent && agent.unclaimed_waiting > 0) {
    items.push({
      key: "unclaimed",
      tone: "amber",
      title: `${agent.unclaimed_waiting} contacto${agent.unclaimed_waiting === 1 ? "" : "s"} sin tomar`,
      detail: `Esperan más de ${agent.first_minutes} min en la bandeja.`,
      go: onOpenInbox,
    });
  }
  if (alerts && alerts.open > 0) {
    items.push({
      key: "alerts",
      tone: "red",
      title: `${alerts.open} alerta${alerts.open === 1 ? "" : "s"} de números por revisar`,
      detail: "Contactos marcados como contactados que volvieron a escribir su número.",
      go: onOpenAlerts,
    });
  }
  if (alerts && alerts.complaints_open > 0) {
    items.push({
      key: "complaints",
      tone: "red",
      title: `${alerts.complaints_open} comentario${alerts.complaints_open === 1 ? "" : "s"} “no me contactan”`,
      detail: "Personas que dicen no haber sido atendidas.",
      go: onOpenAlerts,
    });
  }

  const count = items.length ? (data?.count ?? items.length) : 0;
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="relative rounded-xl p-2.5 text-muted hover:bg-slate-100"
        aria-label={count ? `Notificaciones (${count} pendientes)` : "Notificaciones"}
      >
        <Bell size={20} />
        {count > 0 && (
          <span className="absolute -right-0.5 -top-0.5 grid min-w-[18px] place-items-center rounded-full border-2 border-white bg-red-500 px-1 text-[10px] font-bold leading-4 text-white">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-12 z-40 w-80 rounded-2xl border border-line bg-white p-3 shadow-xl">
          <div className="flex items-center justify-between px-2 py-2">
            <strong className="text-sm">Notificaciones</strong>
            <button type="button" onClick={() => setOpen(false)} aria-label="Cerrar">
              <X size={16} className="text-muted" />
            </button>
          </div>
          {failed && (
            <p className="px-2 pb-2 text-[11px] text-red-600">
              No se pudieron actualizar las notificaciones.
            </p>
          )}
          {!items.length && !failed && (
            <p className="px-2 pb-3 text-xs text-muted">No tienes notificaciones pendientes.</p>
          )}
          {items.map((item) => {
            const Icon = item.tone === "red" ? ShieldAlert : BellRing;
            return (
              <button
                key={item.key}
                type="button"
                disabled={!item.go}
                onClick={() => {
                  item.go?.();
                  setOpen(false);
                }}
                className={`flex w-full gap-3 rounded-xl p-3 text-left ${
                  item.tone === "red" ? "hover:bg-red-50" : "hover:bg-amber-50"
                }`}
              >
                <Icon
                  size={18}
                  className={`mt-0.5 shrink-0 ${item.tone === "red" ? "text-red-600" : "text-amber-600"}`}
                />
                <span>
                  <strong className="block text-xs">{item.title}</strong>
                  <span className="mt-1 block text-[11px] text-muted">{item.detail}</span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
