import { useState } from "react";
import { SignIn } from "@clerk/react";
import { Activity, LogOut, ShieldAlert, Sparkles } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { Dashboard } from "@/features/dashboard/Dashboard";

function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-primary text-white shadow-lg shadow-primary/20">
        <Activity size={23} strokeWidth={2.5} />
      </span>
      {!compact && (
        <span>
          <span className="block text-[15px] font-bold tracking-tight text-ink">
            Medical Social Pulse
          </span>
          <span className="block text-xs text-muted">Centro de monitoreo</span>
        </span>
      )}
    </div>
  );
}

const clerkAppearance = {
  variables: {
    colorPrimary: "#0f92ac",
    colorText: "#14213d",
    colorTextSecondary: "#64748b",
    borderRadius: "0.75rem",
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
  },
  elements: {
    rootBox: "w-full",
    card: "shadow-xl shadow-slate-200/60 border border-line",
  },
};

/** Sign-in is handled by Clerk (username/email, Google, password reset, MFA). */
function LoginScreen() {
  return (
    <main className="min-h-screen bg-canvas lg:grid lg:grid-cols-[1.05fr_.95fr]">
      <section className="relative hidden overflow-hidden bg-deep p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="absolute -left-24 top-1/3 size-80 rounded-full bg-primary/20 blur-3xl" />
        <div className="absolute -right-24 bottom-10 size-96 rounded-full bg-cyan-300/10 blur-3xl" />
        <div className="relative">
          <Logo />
        </div>
        <div className="relative max-w-xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-semibold text-cyan-100">
            <Sparkles size={14} /> Inteligencia para conversaciones reales
          </span>
          <h1 className="mt-6 text-5xl font-bold leading-[1.08] tracking-[-0.04em]">
            Convierte el pulso social en oportunidades de atención.
          </h1>
          <p className="mt-6 max-w-lg text-base leading-7 text-slate-300">
            Monitorea comentarios en vivo y mensajes de TikTok e Instagram desde un solo lugar.
          </p>
          <div className="mt-10 grid grid-cols-3 gap-3">
            {[
              ["24/7", "Monitoreo continuo"],
              ["2 canales", "Bandeja unificada"],
              ["En vivo", "Detección de intención"],
            ].map(([value, label]) => (
              <div key={label} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <strong className="block text-lg">{value}</strong>
                <span className="mt-1 block text-xs text-slate-400">{label}</span>
              </div>
            ))}
          </div>
        </div>
        <p className="relative text-xs text-slate-500">Medical Social Pulse · Acceso seguro</p>
      </section>

      <section className="flex min-h-screen items-center justify-center p-5 sm:p-10">
        <SignIn routing="hash" appearance={clerkAppearance} />
      </section>
    </main>
  );
}

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
          <Logo compact />
          <div className="mx-auto mt-5 size-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      </div>
    );
  }

  if (error) {
    return <AccessProblem message={error} onRetry={() => void reload()} onLogout={() => void logout()} />;
  }

  return isAuthenticated ? <Dashboard /> : <LoginScreen />;
}
