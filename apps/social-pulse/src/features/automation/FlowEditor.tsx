import { useCallback, useMemo, useState } from "react";
import {
  addEdge,
  Background,
  Connection,
  Controls,
  Edge,
  Handle,
  MarkerType,
  Node,
  NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ArrowLeft, Play, Save, Trash2, Undo2, Redo2 } from "lucide-react";
import { api, CatalogEntry, Channel, Flow, FlowGraph, problemText, TestResult } from "./api";
import { Banner, buttonClass, Field, ghostButtonClass, inputClass, Toggle } from "./ui";

type StepData = { kind: string; config: Record<string, unknown>; label: string };
type StepNode = Node<StepData, "step">;

const STATUSES = [
  ["new", "Nuevo"],
  ["contacted", "Contactado"],
  ["qualified", "Calificado"],
  ["discarded", "Descartado"],
];
const DAYS = ["L", "M", "X", "J", "V", "S", "D"];
const GROUPS: [string, string[]][] = [
  ["Mensaje", ["trigger.message", "trigger.manual", "action.send_text"]],
  ["MedicalBot", ["action.ai_reply"]],
  [
    "Condiciones",
    ["condition.keyword", "condition.tag", "condition.status", "condition.business_hours"],
  ],
  [
    "Acciones",
    [
      "action.wait",
      "action.add_tag",
      "action.set_status",
      "action.assign",
      "action.handoff",
      "action.webhook",
      "action.end",
    ],
  ],
];
const DEFAULTS: Record<string, Record<string, unknown>> = {
  "trigger.message": { match: "any", keywords: [] },
  "condition.keyword": { keywords: [] },
  "condition.tag": { tag: "" },
  "condition.status": { statuses: ["new"] },
  "condition.business_hours": { start: "09:00", end: "18:00", days: [0, 1, 2, 3, 4] },
  "action.send_text": { text: "" },
  "action.wait": { minutes: 5 },
  "action.add_tag": { tag: "" },
  "action.set_status": { status: "contacted" },
  "action.handoff": { text: "" },
  "action.webhook": { url: "https://" },
};

const tone = (kind: string) =>
  kind.startsWith("trigger")
    ? { ring: "border-violet-300", head: "bg-violet-50 text-violet-700" }
    : kind.startsWith("condition")
      ? { ring: "border-amber-300", head: "bg-amber-50 text-amber-700" }
      : { ring: "border-sky-300", head: "bg-sky-50 text-sky-700" };

function summary(kind: string, c: Record<string, unknown>): string {
  const words = Array.isArray(c.keywords) ? (c.keywords as string[]).join(", ") : "";
  if (kind === "trigger.message")
    return c.match === "keyword" ? `Si dice: ${words || "…"}` : "Cualquier mensaje";
  if (kind === "condition.keyword") return `¿Dice: ${words || "…"}?`;
  if (kind === "condition.tag" || kind === "action.add_tag")
    return String(c.tag || "(sin etiqueta)");
  if (kind === "condition.status") return (c.statuses as string[] | undefined)?.join(", ") ?? "";
  if (kind === "condition.business_hours") return `${c.start}–${c.end}`;
  if (kind === "action.send_text" || kind === "action.handoff")
    return String(c.text || "(sin texto)").slice(0, 60);
  if (kind === "action.wait") return `${c.minutes} min`;
  if (kind === "action.set_status") return String(c.status);
  if (kind === "action.webhook") return String(c.url);
  if (kind === "action.ai_reply") return "Contesta el agente de IA";
  if (kind === "action.assign") return "Al siguiente agente conectado";
  if (kind === "action.end") return "Fin del flujo";
  return "";
}

function StepCard({ id, data, selected }: NodeProps<StepNode>) {
  const style = tone(data.kind);
  const isTrigger = data.kind.startsWith("trigger");
  const isCondition = data.kind.startsWith("condition");
  return (
    <div
      className={`w-52 rounded-xl border-2 bg-white shadow-sm ${style.ring} ${
        selected ? "ring-4 ring-primary/20" : ""
      }`}
    >
      {!isTrigger && <Handle type="target" position={Position.Left} />}
      <div className={`rounded-t-[9px] px-3 py-1.5 text-[11px] font-bold ${style.head}`}>
        {data.label}
      </div>
      <div className="px-3 py-2 text-xs text-slate-600">
        {summary(data.kind, data.config) || "—"}
      </div>
      <span className="sr-only">{id}</span>
      {isCondition ? (
        <>
          <Handle
            id="yes"
            type="source"
            position={Position.Right}
            style={{ top: "30%", background: "#059669" }}
          />
          <Handle
            id="no"
            type="source"
            position={Position.Right}
            style={{ top: "75%", background: "#dc2626" }}
          />
          <span className="absolute -right-6 top-[18%] text-[10px] font-bold text-emerald-600">
            Sí
          </span>
          <span className="absolute -right-6 top-[63%] text-[10px] font-bold text-red-600">No</span>
        </>
      ) : (
        data.kind !== "action.end" && <Handle id="out" type="source" position={Position.Right} />
      )}
    </div>
  );
}

const nodeTypes = { step: StepCard };

function toFlow(graph: FlowGraph, catalog: Record<string, CatalogEntry>) {
  const nodes: StepNode[] = graph.nodes.map((n, i) => ({
    id: n.id,
    type: "step",
    position: n.pos ?? { x: 40 + (i % 4) * 250, y: 40 + Math.floor(i / 4) * 150 },
    data: {
      kind: n.type,
      config: n.config ?? {},
      label: String(n.config?._title || catalog[n.type]?.label || n.type),
    },
  }));
  const edges: Edge[] = graph.edges.map((e) => edgeOf(e.from, e.to, e.when));
  return { nodes, edges };
}

function edgeOf(source: string, target: string, when?: string): Edge {
  return {
    id: `${source}-${when ?? "out"}-${target}`,
    source,
    target,
    sourceHandle: when ?? "out",
    label: when === "yes" ? "Sí" : when === "no" ? "No" : undefined,
    markerEnd: { type: MarkerType.ArrowClosed },
  };
}

function toGraph(nodes: StepNode[], edges: Edge[]): FlowGraph {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.data.kind,
      config: n.data.config,
      pos: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
    })),
    edges: edges.map((e) => ({
      from: e.source,
      to: e.target,
      ...(e.sourceHandle === "yes" || e.sourceHandle === "no" ? { when: e.sourceHandle } : {}),
    })),
  };
}

function ConfigForm({
  node,
  entry,
  onChange,
}: {
  node: StepNode;
  entry?: CatalogEntry;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const c = node.data.config;
  const set = (patch: Record<string, unknown>) => onChange({ ...c, ...patch });
  const words = (Array.isArray(c.keywords) ? (c.keywords as string[]) : []).join(", ");
  const setWords = (text: string) =>
    set({
      keywords: text
        .split(",")
        .map((w) => w.trim())
        .filter(Boolean),
    });
  const kind = node.data.kind;
  return (
    <div className="space-y-3">
      <Field label="Nombre del nodo">
        <input
          className={inputClass}
          maxLength={80}
          value={String(c._title ?? "")}
          placeholder={entry?.label}
          onChange={(e) => set({ _title: e.target.value })}
        />
      </Field>
      <div>
        <strong className="text-sm">{entry?.label ?? kind}</strong>
        <p className="mt-1 text-xs text-muted">{entry?.help}</p>
      </div>
      {kind === "trigger.message" && (
        <>
          <Field label="Cuándo empieza">
            <select
              className={inputClass}
              value={String(c.match ?? "any")}
              onChange={(e) => set({ match: e.target.value })}
            >
              <option value="any">Con cualquier mensaje</option>
              <option value="keyword">Si dice una palabra clave</option>
            </select>
          </Field>
          {c.match === "keyword" && (
            <Field label="Palabras clave" hint="separadas por coma">
              <input
                className={inputClass}
                value={words}
                onChange={(e) => setWords(e.target.value)}
                placeholder="precio, costo, cita"
              />
            </Field>
          )}
        </>
      )}
      {kind === "condition.keyword" && (
        <Field label="Palabras" hint="separadas por coma">
          <input
            className={inputClass}
            value={words}
            onChange={(e) => setWords(e.target.value)}
            placeholder="cita, agendar"
          />
        </Field>
      )}
      {(kind === "condition.tag" || kind === "action.add_tag") && (
        <Field label="Etiqueta">
          <input
            className={inputClass}
            maxLength={30}
            value={String(c.tag ?? "")}
            onChange={(e) => set({ tag: e.target.value })}
          />
        </Field>
      )}
      {kind === "condition.status" && (
        <Field label="Estados del contacto">
          <div className="flex flex-wrap gap-2">
            {STATUSES.map(([value, label]) => {
              const list = (c.statuses as string[] | undefined) ?? [];
              const on = list.includes(value);
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() =>
                    set({ statuses: on ? list.filter((s) => s !== value) : [...list, value] })
                  }
                  className={`rounded-full border px-3 py-1 text-xs font-semibold ${on ? "border-primary bg-primary-soft text-primary" : "border-line text-muted"}`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </Field>
      )}
      {kind === "condition.business_hours" && (
        <>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Desde">
              <input
                type="time"
                className={inputClass}
                value={String(c.start ?? "09:00")}
                onChange={(e) => set({ start: e.target.value })}
              />
            </Field>
            <Field label="Hasta">
              <input
                type="time"
                className={inputClass}
                value={String(c.end ?? "18:00")}
                onChange={(e) => set({ end: e.target.value })}
              />
            </Field>
          </div>
          <Field label="Días (hora de Lima)">
            <div className="flex gap-1">
              {DAYS.map((label, day) => {
                const list = (c.days as number[] | undefined) ?? [];
                const on = list.includes(day);
                return (
                  <button
                    key={day}
                    type="button"
                    onClick={() =>
                      set({ days: on ? list.filter((d) => d !== day) : [...list, day].sort() })
                    }
                    className={`size-8 rounded-lg border text-xs font-bold ${on ? "border-primary bg-primary-soft text-primary" : "border-line text-muted"}`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </Field>
        </>
      )}
      {(kind === "action.send_text" || kind === "action.handoff") && (
        <Field
          label={kind === "action.send_text" ? "Mensaje" : "Mensaje antes de pasar (opcional)"}
          hint="{{nombre}} {{telefono}} · {{nombre|paciente}} con valor por defecto"
        >
          <textarea
            className={`${inputClass} h-28`}
            maxLength={1000}
            value={String(c.text ?? "")}
            onChange={(e) => set({ text: e.target.value })}
          />
        </Field>
      )}
      {kind === "action.wait" && (
        <Field label="Minutos de espera" hint="1 a 10080">
          <input
            type="number"
            min={1}
            max={10080}
            className={inputClass}
            value={Number(c.minutes ?? 5)}
            onChange={(e) => set({ minutes: Number(e.target.value) })}
          />
        </Field>
      )}
      {kind === "action.set_status" && (
        <Field label="Nuevo estado">
          <select
            className={inputClass}
            value={String(c.status ?? "contacted")}
            onChange={(e) => set({ status: e.target.value })}
          >
            {STATUSES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
      )}
      {kind === "action.webhook" && (
        <Field label="URL (https)">
          <input
            className={inputClass}
            value={String(c.url ?? "")}
            onChange={(e) => set({ url: e.target.value })}
          />
        </Field>
      )}
      {kind === "action.ai_reply" && (
        <p className="rounded-xl bg-slate-50 p-3 text-xs text-muted">
          Usa el agente de IA configurado en la pestaña «Agente IA». Si la IA está apagada, este
          paso no responde.
        </p>
      )}
    </div>
  );
}

function Editor({
  flow,
  catalog,
  channels,
  canManage,
  onBack,
  onChanged,
}: {
  flow: Flow;
  catalog: Record<string, CatalogEntry>;
  channels: Channel[];
  canManage: boolean;
  onBack: () => void;
  onChanged: () => void;
}) {
  const initial = useMemo(() => toFlow(flow.graph ?? { nodes: [], edges: [] }, catalog), []); // eslint-disable-line react-hooks/exhaustive-deps
  const [nodes, setNodes, onNodesChange] = useNodesState<StepNode>(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initial.edges);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState(flow.name);
  const [channelId, setChannelId] = useState(flow.channel_id);
  const [enabled, setEnabled] = useState(flow.enabled);
  const [errors, setErrors] = useState<string[]>(flow.errors ?? []);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [notice, setNotice] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [testText, setTestText] = useState("Hola, quiero información");
  const [result, setResult] = useState<TestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [past, setPast] = useState<{ nodes: StepNode[]; edges: Edge[] }[]>([]);
  const [future, setFuture] = useState<{ nodes: StepNode[]; edges: Edge[] }[]>([]);
  const remember = useCallback(() => {
    setPast((old) => [...old.slice(-39), structuredClone({ nodes, edges })]);
    setFuture([]);
  }, [nodes, edges]);
  const undo = () => {
    const previous = past.at(-1);
    if (!previous) return;
    setFuture((old) => [...old, structuredClone({ nodes, edges })]);
    setPast((old) => old.slice(0, -1));
    setNodes(previous.nodes);
    setEdges(previous.edges);
    setSelected(null);
  };
  const redo = () => {
    const next = future.at(-1);
    if (!next) return;
    setPast((old) => [...old, structuredClone({ nodes, edges })]);
    setFuture((old) => old.slice(0, -1));
    setNodes(next.nodes);
    setEdges(next.edges);
    setSelected(null);
  };

  const onConnect = useCallback(
    (c: Connection) => {
      if (!c.source || !c.target) return;
      remember();
      setEdges((current) => {
        const kept = current.filter(
          (e) =>
            !(e.source === c.source && (e.sourceHandle ?? "out") === (c.sourceHandle ?? "out")),
        );
        const when =
          c.sourceHandle === "yes" || c.sourceHandle === "no" ? c.sourceHandle : undefined;
        return addEdge(edgeOf(c.source, c.target, when), kept);
      });
    },
    [setEdges, remember],
  );

  const isValidConnection = useCallback(
    (c: Connection | Edge) => {
      const target = nodes.find((n) => n.id === c.target);
      return !!target && c.source !== c.target && !target.data.kind.startsWith("trigger");
    },
    [nodes],
  );

  const add = (kind: string) => {
    remember();
    const id = `n${Math.random().toString(36).slice(2, 7)}`;
    setNodes((current) => [
      ...current,
      {
        id,
        type: "step",
        position: {
          x: 60 + (current.length % 4) * 250,
          y: 60 + Math.floor(current.length / 4) * 150,
        },
        data: { kind, config: { ...(DEFAULTS[kind] ?? {}) }, label: catalog[kind]?.label ?? kind },
      },
    ]);
    setSelected(id);
  };

  const removeSelected = () => {
    if (!selected) return;
    remember();
    setNodes((current) => current.filter((n) => n.id !== selected));
    setEdges((current) => current.filter((e) => e.source !== selected && e.target !== selected));
    setSelected(null);
  };

  const current = nodes.find((n) => n.id === selected) ?? null;
  const setConfig = (config: Record<string, unknown>) => {
    remember();
    setNodes((list) =>
      list.map((n) =>
        n.id === selected
          ? {
              ...n,
              data: {
                ...n.data,
                config,
                label: String(config._title || catalog[n.data.kind]?.label || n.data.kind),
              },
            }
          : n,
      ),
    );
  };

  const save = async (): Promise<boolean> => {
    setBusy(true);
    setNotice(null);
    try {
      const saved = await api.saveFlow(flow.id, {
        name,
        description: flow.description,
        channel_id: channelId,
        graph: toGraph(nodes, edges),
      });
      setErrors(saved.errors ?? []);
      setNotice({
        tone: saved.errors?.length ? "error" : "ok",
        text: saved.errors?.length ? "Guardado, pero el flujo tiene errores." : "Guardado.",
      });
      onChanged();
      return true;
    } catch (error) {
      setNotice({ tone: "error", text: problemText(error) });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (value: boolean) => {
    setBusy(true);
    setNotice(null);
    try {
      if (value) {
        if (!(await save())) return;
        const response = await api.enableFlow(flow.id);
        setWarnings(response.warnings ?? []);
      } else {
        await api.disableFlow(flow.id);
        setWarnings([]);
      }
      setEnabled(value);
      onChanged();
    } catch (error) {
      setNotice({ tone: "error", text: problemText(error) });
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    if (!(await save())) return;
    setBusy(true);
    try {
      setResult(await api.testFlow(flow.id, testText));
    } catch (error) {
      setResult(null);
      setNotice({ tone: "error", text: problemText(error) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-6">
      <div className="flex flex-wrap items-center gap-3 rounded-t-3xl bg-deep p-4 text-white">
        <button type="button" className={ghostButtonClass} onClick={onBack}>
          <ArrowLeft size={14} className="mr-1 inline" /> Flujos
        </button>
        <input
          className={`${inputClass} max-w-xs font-bold`}
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={!canManage}
          aria-label="Nombre del flujo"
        />
        <select
          className={`${inputClass} max-w-[220px]`}
          value={channelId}
          onChange={(e) => setChannelId(e.target.value)}
          disabled={!canManage || enabled}
          aria-label="Canal"
        >
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <span className="ml-auto flex items-center gap-3">
          <span className="flex items-center gap-2 text-xs font-semibold text-muted">
            {enabled ? "Activo" : "Apagado"}
            <Toggle
              checked={enabled}
              onChange={(v) => void toggle(v)}
              disabled={!canManage || busy}
              label="Flujo activo"
            />
          </span>
          {canManage && (
            <button
              type="button"
              className={buttonClass}
              disabled={busy}
              onClick={() => void save()}
            >
              <Save size={14} className="mr-1 inline" /> Guardar
            </button>
          )}
        </span>
      </div>
      <div className="flex items-center gap-2 border-x border-line bg-white px-4 py-2">
        <button
          type="button"
          aria-label="Deshacer"
          disabled={!canManage || !past.length || busy}
          onClick={undo}
          className="rounded-lg p-2 text-primary disabled:opacity-30"
        >
          <Undo2 size={16} />
        </button>
        <button
          type="button"
          aria-label="Rehacer"
          disabled={!canManage || !future.length || busy}
          onClick={redo}
          className="rounded-lg p-2 text-primary disabled:opacity-30"
        >
          <Redo2 size={16} />
        </button>
        <span className="text-xs text-muted">
          Arrastra los nodos, conecta sus puntos y selecciona un bloque para editarlo.
        </span>
      </div>
      <div className="mt-3 space-y-2">
        {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
        {warnings.map((w) => (
          <Banner key={w} tone="warn">
            {w}
          </Banner>
        ))}
        {errors.length > 0 && (
          <Banner tone="error">
            <strong>Para activarlo hay que corregir:</strong>
            <ul className="mt-1 list-disc pl-5">
              {errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </Banner>
        )}
      </div>

      <div className="grid gap-0 overflow-hidden rounded-b-3xl border border-line lg:grid-cols-[175px_minmax(0,1fr)_270px]">
        <aside className="space-y-4 rounded-2xl border border-line bg-white p-4">
          {GROUPS.map(([group, kinds]) => (
            <div key={group}>
              <h4 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted">
                {group}
              </h4>
              <div className="space-y-1.5">
                {kinds.map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    disabled={!canManage}
                    onClick={() => add(kind)}
                    title={catalog[kind]?.help}
                    className={`w-full rounded-lg border px-2.5 py-1.5 text-left text-xs font-semibold ${tone(kind).ring} ${tone(kind).head} disabled:opacity-50`}
                  >
                    + {catalog[kind]?.label ?? kind}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </aside>

        <div className="h-[640px] overflow-hidden bg-[#f3f9fa]">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={(changes) => {
              if (changes.some((c) => c.type === "remove")) remember();
              onNodesChange(changes);
            }}
            onNodeDragStart={() => remember()}
            onEdgesChange={(changes) => {
              if (changes.some((c) => c.type === "remove")) remember();
              onEdgesChange(changes);
            }}
            onConnect={onConnect}
            isValidConnection={isValidConnection}
            onNodeClick={(_, node) => setSelected(node.id)}
            onPaneClick={() => setSelected(null)}
            nodesDraggable={canManage}
            nodesConnectable={canManage}
            deleteKeyCode={canManage ? ["Backspace", "Delete"] : null}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={20} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>

        <aside className="space-y-4 bg-white p-4">
          <div className="rounded-2xl border border-line bg-white p-4">
            {current ? (
              <>
                <fieldset disabled={!canManage || busy}>
                  <ConfigForm
                    node={current}
                    entry={catalog[current.data.kind]}
                    onChange={setConfig}
                  />
                </fieldset>
                {canManage && (
                  <button
                    type="button"
                    className={`${ghostButtonClass} mt-4 text-red-600`}
                    onClick={removeSelected}
                  >
                    <Trash2 size={14} className="mr-1 inline" /> Quitar este paso
                  </button>
                )}
              </>
            ) : (
              <p className="text-sm text-muted">
                Agrega pasos con los botones de la izquierda, arrastra para ordenarlos y une un paso
                con otro desde su punto de salida. Toca un paso para configurarlo. Las condiciones
                tienen dos salidas: Sí y No.
              </p>
            )}
          </div>
          {canManage && (
            <div className="rounded-2xl border border-line bg-white p-4">
              <h4 className="text-sm font-bold">Probar con una paciente inventada</h4>
              <p className="mt-1 text-xs text-muted">
                Corre el flujo ahora en el simulador. No envía nada real, omite las esperas y no
                toca contactos ni agentes.
              </p>
              <textarea
                className={`${inputClass} mt-3 h-16`}
                value={testText}
                onChange={(e) => setTestText(e.target.value)}
              />
              <button
                type="button"
                className={`${buttonClass} mt-2`}
                disabled={busy || !testText.trim()}
                onClick={() => void test()}
              >
                <Play size={14} className="mr-1 inline" /> Guardar y probar
              </button>
              {result && (
                <div className="mt-4 space-y-3 text-xs">
                  <div className="space-y-1.5">
                    {result.messages.map((m, i) => (
                      <p
                        key={i}
                        className="rounded-xl rounded-tl-sm bg-emerald-50 px-3 py-2 text-emerald-900"
                      >
                        {m.body}
                      </p>
                    ))}
                    {!result.messages.length && (
                      <p className="text-muted">El bot no envió mensajes.</p>
                    )}
                  </div>
                  <ol className="space-y-1 border-l-2 border-line pl-3">
                    {result.steps.map((s, i) => (
                      <li key={i}>
                        <span className="font-semibold">{catalog[s.type]?.label ?? s.type}:</span>{" "}
                        {s.outcome}
                      </li>
                    ))}
                  </ol>
                  <p className="font-semibold">
                    Resultado: {result.status}
                    {result.reason ? ` · ${result.reason}` : ""}
                  </p>
                </div>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

export function FlowEditor(props: Parameters<typeof Editor>[0]) {
  return (
    <ReactFlowProvider>
      <Editor {...props} />
    </ReactFlowProvider>
  );
}
