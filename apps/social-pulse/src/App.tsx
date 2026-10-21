import { useState } from "react";
import { LogOut, ShieldAlert } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { BrandLogo } from "@/features/auth/BrandLogo";
import { LoginScreen } from "@/features/auth/LoginScreen";
import { Dashboard } from "@/features/dashboard/Dashboard";
import { TikTokConnection } from "@/features/integrations/TikTokConnection";

function AccessProblem({
  message,
  onRetry,
  onLogout,
}: {
  message: string;
  onRetry: () => void;
  onLogout: () => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <main className="grid min-h-screen place-items-center bg-canvas p-5">
      <section className="w-full max-w-md rounded-[28px] border border-line bg-white p-8 text-center shadow-xl shadow-slate-200/60">
        <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-amber-50 text-amber-600">
          <ShieldAlert size={22} />
        </span>
        <h1 className="mt-5 text-xl font-bold text-ink">No pudimos abrir tu espacio</h1>
        <p className="mt-2 text-sm leading-6 text-muted">{message}</p>
        <div className="mt-6 flex flex-col gap-3">
          <button
            type="button"
            className="primary-button"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              onRetry();
              setTimeout(() => setBusy(false), 1500);
            }}
          >
            {busy ? "Verificando..." : "Reintentar"}
          </button>
          <button
            type="button"
            onClick={onLogout}
            className="inline-flex items-center justify-center gap-2 text-sm font-semibold text-primary hover:text-primary-dark"
          >
            <LogOut size={16} /> Cerrar sesión
          </button>
        </div>
      </section>
    </main>
  );
}

export default function App() {
  const { isAuthenticated, isLoading, error, reload, logout } = useAuth();

  if (isLoading) {
    return (
      <div className="grid min-h-screen place-items-center bg-canvas">
        <div className="text-center">
          <BrandLogo mark className="mx-auto h-14" />
          <div className="mx-auto mt-5 size-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <AccessProblem message={error} onRetry={() => void reload()} onLogout={() => void logout()} />
    );
  }

  if (!isAuthenticated) return <LoginScreen />;
  return window.location.pathname === "/integraciones/tiktok" ? (
    <TikTokConnection />
  ) : (
    <Dashboard />
  );
}
