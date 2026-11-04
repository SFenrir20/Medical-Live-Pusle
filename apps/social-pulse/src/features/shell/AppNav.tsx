import { PrimaryNav } from "./PrimaryNav";
import { LogOut } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { BrandLogo } from "@/features/auth/BrandLogo";
import { PresenceControl } from "@/features/presence/PresenceControl";
import { usePresence } from "@/features/presence/usePresence";

const ROLE_LABEL: Record<string, string> = {
  agente_ventas: "Agente call center",
  gerente: "Gerente",
  jefe_marketing: "Jefe de Marketing",
  supervisor: "Supervisor",
  admin: "Administrador",
};

/** Top bar of the pages that live outside the dashboard (Chats, CRM). Sales agents keep sending
 *  their presence here too, so being in a chat counts as being connected. */
export function AppNav() {
  const { user, logout } = useAuth();
  const permissions = user?.permissions ?? [];
  const onShift = user?.role === "agente_ventas";
  const { presence, failed, setStatus } = usePresence(onShift);
  const path = window.location.pathname;
  const active = ["/bandeja", "/whatsapp"].includes(path)
    ? "Bandeja"
    : path === "/contactos"
      ? "Contactos"
      : ["/tools", "/crm"].includes(path)
        ? "TOOLS"
        : path === "/ajustes"
          ? "Ajustes"
          : "Pulso";
  return (
    <header className="z-30 border-b border-line bg-white">
      <div className="mx-auto flex min-h-16 flex-wrap py-2 max-w-[1800px] items-center justify-between gap-3 px-4 sm:px-6">
        <a href="/" aria-label="Ir al inicio">
          <BrandLogo mark className="h-9 sm:hidden" />
          <BrandLogo className="hidden h-9 sm:block" />
        </a>
        <div className="order-3 w-full md:order-none md:w-auto">
          <PrimaryNav active={active} />
        </div>
        <div className="flex items-center gap-2">
          {onShift && <PresenceControl presence={presence} failed={failed} onChange={setStatus} />}
          <button
            type="button"
            onClick={logout}
            className="flex items-center gap-3 rounded-xl p-1.5 pr-3 hover:bg-slate-100"
            title="Cerrar sesión"
          >
            <span className="grid size-9 place-items-center rounded-xl bg-primary-soft text-xs font-bold text-primary">
              {user?.name.slice(0, 2).toUpperCase()}
            </span>
            <span className="hidden text-left sm:block">
              <span className="block text-sm font-semibold">{user?.name}</span>
              <span className="block text-[11px] text-muted">
                {ROLE_LABEL[user?.role ?? ""] ?? ""}
              </span>
            </span>
            <LogOut size={16} className="text-muted" />
          </button>
        </div>
      </div>
    </header>
  );
}
