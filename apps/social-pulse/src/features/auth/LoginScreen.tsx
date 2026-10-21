import { SignIn } from "@clerk/react";
import { ArrowRight, CalendarCheck, Inbox, ShieldCheck, UserCheck, Zap } from "lucide-react";
import { BrandLogo } from "./BrandLogo";

const clerkAppearance = {
  variables: {
    colorPrimary: "#0f92ac",
    colorText: "#14213d",
    colorTextSecondary: "#64748b",
    borderRadius: "0.75rem",
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
  },
  elements: {
    rootBox: { width: "100%" },
    // Flat: our own card around it is the card. Style objects beat Clerk's own CSS.
    cardBox: { width: "100%", boxShadow: "none", border: "none", background: "transparent" },
    card: {
      width: "100%",
      maxWidth: "none",
      boxShadow: "none",
      border: "none",
      background: "transparent",
      padding: 0,
    },
    footer: { background: "transparent", width: "100%" },
    // Accounts and roles are created by the administrator in Clerk: no self sign-up link.
    footerAction: { display: "none" },
    // The card already carries the title and subtitle; Clerk's own would repeat them.
    headerTitle: "hidden",
    headerSubtitle: "hidden",
    header: "hidden",
    formButtonPrimary:
      "h-12 rounded-xl bg-primary text-sm font-bold shadow-lg shadow-primary/25 hover:bg-primary-dark",
    formFieldInput: "h-12 rounded-xl border-line",
    socialButtonsBlockButton: "h-12 rounded-xl border-line",
  },
};

const FLOW = [
  { icon: Inbox, title: "Captura", text: "WhatsApp, TikTok e Instagram en una sola bandeja" },
  { icon: UserCheck, title: "Seguimiento", text: "Cada paciente con su asesor y su estado" },
  { icon: CalendarCheck, title: "Consulta agendada", text: "Del primer mensaje a la cita" },
];

const CHANNELS = [
  ["WhatsApp", "bg-emerald-400"],
  ["TikTok", "bg-cyan-300"],
  ["Instagram", "bg-fuchsia-400"],
];

/** Sign-in is handled by Clerk (username/email, Google, password reset, MFA). */
export function LoginScreen() {
  return (
    <main className="min-h-screen bg-white lg:grid lg:grid-cols-[1.1fr_.9fr]">
      <section className="relative hidden overflow-hidden bg-gradient-to-br from-[#0b3556] via-[#0a5f7d] to-[#0a93ad] p-12 text-white lg:flex lg:flex-col lg:justify-between xl:p-16">
        <div
          aria-hidden
          className="absolute -right-40 -top-40 size-[34rem] rounded-full border-[56px] border-white/[0.05]"
        />
        <div
          aria-hidden
          className="absolute -bottom-48 -left-32 size-[30rem] rounded-full border-[48px] border-white/[0.05]"
        />
        <div
          aria-hidden
          className="absolute right-10 top-1/3 size-72 rounded-full bg-cyan-300/10 blur-3xl"
        />

        <div className="relative">
          <BrandLogo light className="h-14" />
        </div>

        <div className="relative max-w-2xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 py-2 text-xs font-semibold text-cyan-50 backdrop-blur">
            <Zap size={14} className="text-amber-300" fill="currentColor" /> Gestión inteligente de
            pacientes
          </span>
          <h1 className="mt-6 text-4xl font-bold leading-[1.1] tracking-[-0.035em] xl:text-[3.4rem]">
            Convierte tus redes sociales en{" "}
            <span className="bg-gradient-to-r from-cyan-100 to-teal-200 bg-clip-text text-transparent">
              consultas médicas agendadas.
            </span>
          </h1>
          <p className="mt-6 max-w-xl text-base leading-7 text-cyan-50/80 xl:text-lg xl:leading-8">
            Centraliza la atención de tus pacientes de WhatsApp, TikTok e Instagram en un solo flujo
            de trabajo inteligente.
          </p>

          <div className="mt-10 rounded-3xl border border-white/10 bg-white/[0.07] p-5 backdrop-blur-sm xl:p-6">
            <div className="flex flex-wrap items-center gap-2">
              {CHANNELS.map(([name, dot]) => (
                <span
                  key={name}
                  className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold text-slate-100"
                >
                  <span className={`size-2 rounded-full ${dot}`} />
                  {name}
                </span>
              ))}
            </div>
            <ol className="mt-5 grid grid-cols-3 items-start gap-2">
              {FLOW.map(({ icon: Icon, title, text }, index) => (
                <li key={title} className="relative pr-5">
                  <span className="grid size-11 place-items-center rounded-2xl bg-white/15 text-white ring-1 ring-white/20">
                    <Icon size={20} />
                  </span>
                  <strong className="mt-3 block text-sm">{title}</strong>
                  <span className="mt-1 block text-xs leading-5 text-cyan-50/70">{text}</span>
                  {index < FLOW.length - 1 && (
                    <ArrowRight
                      size={16}
                      aria-hidden
                      className="absolute right-0 top-4 text-cyan-100/60"
                    />
                  )}
                </li>
              ))}
            </ol>
          </div>
        </div>

        <p className="relative text-xs text-cyan-50/60">
          Medical © {new Date().getFullYear()} · Social Pulse CRM
        </p>
      </section>

      <section className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-[#f1f8fb] via-white to-[#dff1f6] px-4 py-10 sm:px-8">
        <div
          aria-hidden
          className="absolute -right-24 -top-24 size-80 rounded-full bg-primary/10 blur-3xl"
        />
        <div
          aria-hidden
          className="absolute -bottom-28 -left-20 size-80 rounded-full bg-cyan-300/20 blur-3xl"
        />
        <div className="relative w-full max-w-[440px] rounded-[28px] border border-white bg-white p-7 shadow-2xl shadow-cyan-900/10 sm:p-9">
          <BrandLogo className="mx-auto h-14" />
          <h2 className="mt-6 text-center text-[1.65rem] font-bold tracking-tight text-ink">
            Bienvenido de nuevo
          </h2>
          <p className="mt-2 text-center text-sm leading-6 text-muted">
            Ingresa para gestionar la atención de tus pacientes
          </p>
          <div className="mt-6">
            <SignIn routing="hash" appearance={clerkAppearance} />
          </div>
          <p className="mt-5 flex items-center justify-center gap-2 border-t border-line pt-5 text-xs text-muted">
            <span className="grid size-6 place-items-center rounded-full bg-primary-soft text-primary">
              <ShieldCheck size={14} />
            </span>
            Acceso seguro para personal autorizado
          </p>
        </div>
      </section>
    </main>
  );
}
