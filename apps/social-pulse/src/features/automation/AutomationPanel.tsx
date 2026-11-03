import { useCallback, useEffect, useState } from "react";
import { AiTab } from "./AiTab";
import { api, Overview, problemText } from "./api";
import { BroadcastsTab } from "./BroadcastsTab";
import { ChannelsTab } from "./ChannelsTab";
import { FlowsTab } from "./FlowsTab";
import { SimulatorTab } from "./SimulatorTab";
import { Banner } from "./ui";

const TABS = [
  ["flows", "Flujos"],
  ["ai", "Agente IA"],
  ["broadcasts", "Difusiones"],
  ["simulator", "Simulador"],
  ["channels", "Canales y seguridad"],
] as const;
type Tab = (typeof TABS)[number][0];

/** Automation tools: flows (diagrams), AI agent, mass messages and the safety policy of each
 *  channel. Only an admin changes things; supervisors and managers can look. */
export function AutomationPanel() {
  const [tab, setTab] = useState<Tab>("flows");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setOverview(await api.overview());
      setError("");
    } catch (e) {
      setError(problemText(e, "No se pudo cargar la automatización."));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  if (error)
    return (
      <div className="mt-6">
        <Banner tone="error">{error}</Banner>
      </div>
    );
  if (!overview) return <p className="mt-6 text-sm text-muted">Cargando…</p>;
  const canManage = overview.can_manage;
  const mirror = overview.channels.find((c) => c.kind === "whatsapp_mirror");

  return (
    <div>
      <div className="mt-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-primary">
            Automatización
          </p>
          <h2 className="mt-1 text-2xl font-bold">Flujos, agente de IA y mensajes masivos</h2>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-bold">
          <span className="rounded-full bg-slate-100 px-3 py-1.5 text-slate-600">
            {overview.flows.enabled} flujos activos
          </span>
          <span
            className={`rounded-full px-3 py-1.5 ${overview.ai.enabled ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}
          >
            IA {overview.ai.enabled ? "activa" : "apagada"}
          </span>
        </div>
      </div>
      <div className="mt-4 space-y-2">
        {!canManage && (
          <Banner tone="info">
            Estás en modo solo lectura: puedes ver flujos, resultados y configuración, pero solo un
            administrador puede cambiarlos.
          </Banner>
        )}
        {!mirror && (
          <Banner tone="info">
            Todo se prueba en el <strong>simulador</strong>. Cuando se vincule el WhatsApp Business
            (espejo) o llegue la API oficial, se agrega el canal en «Canales y seguridad» y los
            flujos ya hechos funcionan igual.
          </Banner>
        )}
      </div>
      <nav className="mt-5 flex gap-2 overflow-x-auto border-b border-line pb-3">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`whitespace-nowrap rounded-xl px-4 py-2 text-sm font-semibold ${tab === key ? "bg-primary-soft text-primary" : "text-muted hover:bg-slate-50"}`}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "flows" && (
        <FlowsTab
          overview={overview}
          channels={overview.channels}
          canManage={canManage}
          onChanged={() => void load()}
        />
      )}
      {tab === "ai" && <AiTab overview={overview} canManage={canManage} />}
      {tab === "broadcasts" && <BroadcastsTab channels={overview.channels} canManage={canManage} />}
      {tab === "simulator" && <SimulatorTab canManage={canManage} />}
      {tab === "channels" && (
        <ChannelsTab
          channels={overview.channels}
          canManage={canManage}
          onChanged={() => void load()}
        />
      )}
    </div>
  );
}
