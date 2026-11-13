import { SitesSettings } from "@/features/sites/SitesSettings";
import { WhatsAppConnection } from "@/features/integrations/WhatsAppConnection";
import { useAuth } from "@/context/AuthContext";
import { AppNav } from "./AppNav";

export function SettingsPage() {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <AppNav />
      <main className="mx-auto max-w-4xl px-6 py-8">
        <p className="text-xs font-bold uppercase tracking-widest text-primary">Tu espacio</p>
        <h1 className="mt-2 text-3xl font-bold">Ajustes</h1>
        <section className="mt-6 rounded-3xl border border-line bg-white p-6">
          <h2 className="font-bold">Cuenta y sesión</h2>
          <p className="mt-2 text-sm text-muted">{user?.name}</p>
          <p className="mt-4 text-sm leading-6 text-muted">
            Tu sesión de trabajo se muestra en la barra superior. Tras 5 minutos sin actividad o al
            ocultar la pestaña pasa a amarillo. Después de 15 minutos continuos en amarillo se
            desconecta y debes pulsar Conectarme.
          </p>
          <button
            type="button"
            onClick={() => void logout()}
            className="mt-5 rounded-xl border border-line px-4 py-2 text-sm text-primary"
          >
            Cerrar sesión
          </button>
        </section>
        {user?.screens.includes("marketing") && (
          <section className="mt-4 rounded-3xl border border-line bg-white p-6">
            <h2 className="font-bold">Conexiones</h2>
            <div className="mt-4 flex flex-wrap gap-4 text-sm text-primary">
              <a href="/integraciones/tiktok">Conexión de TikTok</a>
            </div>
          </section>
        )}
        {user?.permissions.includes("wa:manage") && <WhatsAppConnection />}
        {user?.permissions.includes("sites:manage") && <SitesSettings />}
      </main>
    </div>
  );
}
