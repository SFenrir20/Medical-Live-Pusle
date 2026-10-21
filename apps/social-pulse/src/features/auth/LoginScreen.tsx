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
    // Flat: the page around it is already the card. Style objects beat Clerk's own CSS.
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
    // The page already says "Bienvenido de nuevo"; Clerk's own title would repeat it.
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
      <section className="relative hidden overflow-hidden bg-gradient-to-br from-[#08202c] via-deep to-[#0b5163] p-12 text-white lg:flex lg:flex-col lg:justify-between xl:p-16">
        <div
          aria-hidden
          className="absolute inset-0 opacity-[0.07] [background-image:linear-gradient(white_1px,transparent_1px),linear-gradient(90deg,white_1px,transparent_1px)] [background-size:44px_44px]"
        />
        <div
          aria-hidden
          className="absolute -left-28 top-1/4 size-96 rounded-full bg-primary/25 blur-3xl"
        />
        <div
          aria-hidden
          className="absolute -right-24 bottom-0 size-[28rem] rounded-full bg-cyan-300/10 blur-3xl"
        />

        <div className="relative">
          <span className="inline-flex rounded-2xl bg-white px-5 py-3 shadow-2xl shadow-black/25">
            <BrandLogo className="h-12" />
          </span>
        </div>

        <div className="relative max-w-2xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 py-2 text-xs font-semibold text-cyan-100 backdrop-blur">
            <Zap size={14} className="text-amber-300" fill="currentColor" /> Gestión inteligente de
            pacientes
          </span>
          <h1 className="mt-6 text-4xl font-bold leading-[1.1] tracking-[-0.035em] xl:text-[3.4rem]">
            Convierte tus redes sociales en{" "}
            <span className="bg-gradient-to-r from-cyan-200 to-teal-300 bg-clip-text text-transparent">
              consultas médicas agendadas.
            </span>
          </h1>
          <p className="mt-6 max-w-xl text-base leading-7 text-slate-300 xl:text-lg xl:leading-8">
            Centraliza la atención de tus pacientes de WhatsApp, TikTok e Instagram en un solo flujo
            de trabajo inteligente.
          </p>

          <div className="mt-10 rounded-3xl border border-white/10 bg-white/[0.06] p-5 backdrop-blur-sm xl:p-6">
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
                  <span className="grid size-11 place-items-center rounded-2xl bg-primary/90 text-white shadow-lg shadow-primary/30">
                    <Icon size={20} />
                  </span>
                  <strong className="mt-3 block text-sm">{title}</strong>
                  <span className="mt-1 block text-xs leading-5 text-slate-400">{text}</span>
                  {index < FLOW.length - 1 && (
                    <ArrowRight
                      size={16}
                      aria-hidden
                      className="absolute right-0 top-4 text-cyan-200/60"
                    />
                  )}
                </li>
              ))}
            </ol>
          </div>
        </div>

        <p className="relative flex items-center gap-2 text-xs text-slate-400">
          <ShieldCheck size={15} className="text-cyan-300" /> Acceso seguro · Medical Social Pulse
          CRM
        </p>
      </section>

      <section className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-white to-canvas px-5 py-10 sm:px-10">
        <div className="w-full max-w-[420px]">
          <div className="mb-8 lg:hidden">
            <BrandLogo className="mx-auto h-12" />
          </div>
          <h2 className="text-[1.75rem] font-bold tracking-tight text-ink">Bienvenido de nuevo</h2>
          <p className="mt-2 text-sm leading-6 text-muted">
            Ingresa con tu cuenta para continuar con la atención de tus pacientes.
          </p>
          <div className="mt-7">
            <SignIn routing="hash" appearance={clerkAppearance} />
          </div>
          <p className="mt-8 flex items-center justify-center gap-2 text-center text-xs text-muted">
            <ShieldCheck size={14} className="text-primary" /> ¿Problemas para ingresar? Escribe a
            tu administrador.
          </p>
        </div>
      </section>
    </main>
  );
}
