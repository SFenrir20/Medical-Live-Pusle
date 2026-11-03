import { useCallback, useEffect, useState } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { api, Channel, Flow, FlowGraph, Overview, problemText } from "./api";
import { FlowEditor } from "./FlowEditor";
import { Banner, buttonClass, ghostButtonClass, Section, Toggle, when } from "./ui";

type Template = { title: string; help: string; graph: FlowGraph };

const at = (x: number, y: number) => ({ x, y });
const TEMPLATES: Template[] = [
  {
    title: "En blanco",
    help: "Solo el disparador: agrega tú los pasos.",
    graph: {
      nodes: [{ id: "inicio", type: "trigger.message", config: { match: "any" }, pos: at(40, 80) }],
      edges: [],
    },
  },
  {
    title: "Responder por palabra clave",
    help: "Si escriben «precio» o «costo», responde y etiqueta la conversación.",
    graph: {
      nodes: [
        {
          id: "inicio",
          type: "trigger.message",
          config: { match: "keyword", keywords: ["precio", "costo"] },
          pos: at(40, 80),
        },
        {
          id: "respuesta",
          type: "action.send_text",
          config: {
            text: "Hola {{nombre|}}, la valoración con el cirujano cuesta S/ 80. ¿Te ayudo a agendar?",
          },
          pos: at(300, 80),
        },
        {
          id: "etiqueta",
          type: "action.add_tag",
          config: { tag: "pidio-precio" },
          pos: at(560, 80),
        },
      ],
      edges: [
        { from: "inicio", to: "respuesta" },
        { from: "respuesta", to: "etiqueta" },
      ],
    },
  },
  {
    title: "Fuera de horario",
    help: "Si escriben fuera del horario, avisa cuándo los atenderán.",
    graph: {
      nodes: [
        { id: "inicio", type: "trigger.message", config: { match: "any" }, pos: at(40, 120) },
        {
          id: "horario",
          type: "condition.business_hours",
          config: { start: "09:00", end: "18:00", days: [0, 1, 2, 3, 4, 5] },
          pos: at(300, 120),
        },
        { id: "dentro", type: "action.assign", config: {}, pos: at(580, 40) },
        {
          id: "fuera",
          type: "action.send_text",
          config: { text: "Gracias por escribirnos. Te responderemos mañana a primera hora." },
          pos: at(580, 220),
        },
      ],
      edges: [
        { from: "inicio", to: "horario" },
        { from: "horario", to: "dentro", when: "yes" },
        { from: "horario", to: "fuera", when: "no" },
      ],
    },
  },
  {
    title: "Agente de IA responde",
    help: "La IA contesta con la información cargada y pasa a una persona si hace falta.",
    graph: {
      nodes: [
        { id: "inicio", type: "trigger.message", config: { match: "any" }, pos: at(40, 80) },
        { id: "ia", type: "action.ai_reply", config: {}, pos: at(300, 80) },
      ],
      edges: [{ from: "inicio", to: "ia" }],
    },
  },
];

export function FlowsTab({
  overview,
  channels,
  canManage,
  onChanged,
}: {
  overview: Overview;
  channels: Channel[];
  canManage: boolean;
  onChanged: () => void;
}) {
  const [flows, setFlows] = useState<Flow[]>([]);
  const [editing, setEditing] = useState<Flow | null>(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [channelId, setChannelId] = useState(channels[0]?.id ?? "simulador");

  const load = useCallback(async () => {
    try {
      setFlows(await api.flows());
    } catch (e) {
      setError(problemText(e));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const open = async (id: number) => {
    try {
      setEditing(await api.flow(id));
    } catch (e) {
      setError(problemText(e));
    }
  };

  const create = async (template: Template) => {
    try {
      const flow = await api.createFlow({
        name: template.title,
        channel_id: channelId,
        graph: template.graph,
      });
      setCreating(false);
      await load();
      setEditing(flow);
    } catch (e) {
      setError(problemText(e));
    }
  };

  const toggle = async (flow: Flow) => {
    setError("");
    try {
      if (flow.enabled) await api.disableFlow(flow.id);
      else await api.enableFlow(flow.id);
      await load();
      onChanged();
    } catch (e) {
      setError(problemText(e));
    }
  };

  const remove = async (flow: Flow) => {
    if (!window.confirm(`¿Borrar el flujo «${flow.name}»? No se puede deshacer.`)) return;
    try {
      await api.deleteFlow(flow.id);
      await load();
    } catch (e) {
      setError(problemText(e));
    }
  };

  if (editing) {
    return (
      <FlowEditor
        flow={editing}
        catalog={overview.catalog}
        channels={channels}
        canManage={canManage}
        onBack={() => {
          setEditing(null);
          void load();
          onChanged();
        }}
        onChanged={() => void load()}
      />
    );
  }

  return (
    <Section
      title="Flujos de automatización"
      help="Diagramas que se ejecutan cuando alguien escribe: responder, esperar, etiquetar, asignar a un agente, pasar a una persona o dejar que conteste la IA. Nacen apagados y puedes probarlos en el simulador antes de activarlos."
      action={
        canManage && (
          <button type="button" className={buttonClass} onClick={() => setCreating((v) => !v)}>
            Nuevo flujo
          </button>
        )
      }
    >
      {error && (
        <div className="mb-4">
          <Banner tone="error">{error}</Banner>
        </div>
      )}
      {creating && (
        <div className="mb-5 rounded-2xl border border-line bg-white p-5">
          <div className="flex flex-wrap items-center gap-3">
            <strong className="text-sm">Empezar desde una plantilla, en el canal:</strong>
            <select
              className="rounded-xl border border-line px-3 py-2 text-sm"
              value={channelId}
              onChange={(e) => setChannelId(e.target.value)}
            >
              {channels.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {TEMPLATES.map((t) => (
              <button
                key={t.title}
                type="button"
                onClick={() => void create(t)}
                className="rounded-xl border border-line p-4 text-left hover:border-primary hover:bg-primary-soft"
              >
                <strong className="text-sm">{t.title}</strong>
                <p className="mt-1 text-xs text-muted">{t.help}</p>
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="overflow-x-auto rounded-2xl border border-line bg-white">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-[11px] uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-3">Flujo</th>
              <th className="px-2 py-3">Canal</th>
              <th className="px-2 py-3">Estado</th>
              <th className="px-2 py-3">Actualizado</th>
              <th className="px-2 py-3" />
            </tr>
          </thead>
          <tbody>
            {flows.map((flow) => (
              <tr key={flow.id} className="border-t border-line">
                <td className="px-4 py-3">
                  <strong>{flow.name}</strong>
                  {!flow.valid && (
                    <span className="ml-2 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                      incompleto
                    </span>
                  )}
                </td>
                <td className="px-2 py-3 text-xs text-muted">
                  {channels.find((c) => c.id === flow.channel_id)?.name ?? flow.channel_id}
                </td>
                <td className="px-2 py-3">
                  <Toggle
                    checked={flow.enabled}
                    onChange={() => void toggle(flow)}
                    disabled={!canManage}
                    label={`Activar ${flow.name}`}
                  />
                </td>
                <td className="px-2 py-3 text-xs text-muted">{when(flow.updated_at)}</td>
                <td className="px-2 py-3 text-right">
                  <button
                    type="button"
                    className={ghostButtonClass}
                    onClick={() => void open(flow.id)}
                  >
                    <Pencil size={13} className="mr-1 inline" /> {canManage ? "Editar" : "Ver"}
                  </button>
                  {canManage && !flow.enabled && (
                    <button
                      type="button"
                      className="ml-2 p-2 text-red-500"
                      onClick={() => void remove(flow)}
                      aria-label={`Borrar ${flow.name}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!flows.length && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-sm text-muted">
                  Todavía no hay flujos. {canManage ? "Crea el primero con «Nuevo flujo»." : ""}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Section>
  );
}
