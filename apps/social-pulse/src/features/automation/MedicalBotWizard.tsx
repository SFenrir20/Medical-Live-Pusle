import { useCallback, useEffect, useState } from "react";
import { Bot, Check, MessageCircle, Play, Settings2, Sparkles, Workflow } from "lucide-react";
import { api, Overview, problemText } from "./api";
import { AiTab } from "./AiTab";
import { ChannelsTab } from "./ChannelsTab";
import { FlowsTab } from "./FlowsTab";
import { SimulatorTab } from "./SimulatorTab";
import { Banner } from "./ui";

const STEPS = [
  { title: "Canales", icon: MessageCircle },
  { title: "Conversaciones", icon: Sparkles },
  { title: "Diseñar flujo", icon: Bot },
  { title: "Probar bot", icon: Play },
  { title: "Activar", icon: Check },
  { title: "Mejorar", icon: Settings2 },
];
export function MedicalBotWizard() {
  const [step, setStep] = useState(0);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      setOverview(await api.overview());
      setError("");
    } catch (e) {
      setError(problemText(e));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <div className="mt-5 space-y-5">
      <section className="rounded-3xl border border-line bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-primary">
              Configuración MedicalBot
            </p>
            <h2 className="mt-2 text-xl font-bold">Construye el recorrido del paciente</h2>
          </div>
          <span className="rounded-full bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700">
            Paso {step + 1} de 6
          </span>
        </div>
        <nav
          className="mt-5 grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6"
          aria-label="Configuración de MedicalBot"
        >
          {STEPS.map(({ title, icon: Icon }, i) => (
            <button
              type="button"
              key={title}
              aria-current={i === step ? "step" : undefined}
              onClick={() => setStep(i)}
              className={`rounded-2xl border p-3 text-left ${i === step ? "border-primary bg-primary-soft" : "border-line bg-slate-50 hover:bg-white"}`}
            >
              <span className="flex justify-between text-primary">
                <Icon size={16} />
                <span className="text-[10px]">{String(i + 1).padStart(2, "0")}</span>
              </span>
              <span className="mt-3 block text-xs font-bold">{title}</span>
            </button>
          ))}
        </nav>
      </section>
      {error && <Banner tone="error">{error}</Banner>}
      {overview && (
        <>
          {!overview.can_manage && (
            <Banner tone="info">
              Modo de consulta. Solo un administrador puede guardar o activar automatizaciones.
            </Banner>
          )}
          {step === 0 && (
            <ChannelsTab
              channels={overview.channels}
              canManage={overview.can_manage}
              onChanged={() => void load()}
            />
          )}
          {step === 1 && <AiTab overview={overview} canManage={overview.can_manage} />}
          {step === 2 && (
            <FlowsTab
              overview={overview}
              channels={overview.channels}
              canManage={overview.can_manage}
              onChanged={() => void load()}
            />
          )}
          {step === 3 && <SimulatorTab canManage={overview.can_manage} />}
          {step === 4 && (
            <>
              <Banner tone="info">
                Activa cada flujo desde «Diseñar flujo». El canal y sus permisos son controles
                separados. El espejo real todavía no ejecuta estos bots.
              </Banner>
              <ChannelsTab
                channels={overview.channels}
                canManage={overview.can_manage}
                onChanged={() => void load()}
              />
            </>
          )}
          {step === 5 && (
            <section className="rounded-3xl border border-line bg-white p-6">
              <Workflow className="text-primary" />
              <h3 className="mt-3 text-xl font-bold">Revisa y mejora tu atención</h3>
              <p className="mt-2 text-sm text-muted">
                Tienes {overview.flows.enabled} flujos activos y {overview.flows.disabled}{" "}
                borradores. Abre un flujo para consultar sus ejecuciones y probar cambios. Las
                pruebas no representan conversaciones reales.
              </p>
              <button
                className="mt-4 rounded-xl bg-primary px-4 py-2 text-sm font-bold text-white"
                onClick={() => setStep(2)}
              >
                Revisar flujos →
              </button>
            </section>
          )}
        </>
      )}
    </div>
  );
}
