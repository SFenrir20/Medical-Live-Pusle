import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { problem } from "@/features/chats/api";
import { type Funnel, funnelApi, type FunnelStage, type StageDraft, type StageMetric } from "./api";
import { Modal } from "./Dialogs";

const COLORS = [
  "#0f92ac",
  "#14b8a6",
  "#22c55e",
  "#f59e0b",
  "#7c3aed",
  "#ec4899",
  "#0ea5e9",
  "#94a3b8",
];
const MAX_STAGES = 12;

const draftOf = (s: FunnelStage): StageDraft => ({
  id: s.id,
  name: s.name,
  color: s.color,
  description: s.description ?? "",
});

/** Builder of a funnel: name, stages (order, color, description) and the numbers of each stage.
 *  The built-in funnel only shows its numbers: it mirrors the contact status. */
export function FunnelBuilder({
  funnel,
  stages,
  onClose,
  onSaved,
  onArchived,
}: {
  funnel: Funnel;
  stages: FunnelStage[];
  onClose: () => void;
  onSaved: () => void;
  onArchived: () => void;
}) {
  const [name, setName] = useState(funnel.name);
  const [drafts, setDrafts] = useState<StageDraft[]>(() => stages.map(draftOf));
  const [metrics, setMetrics] = useState<Record<number, StageMetric>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const locked = funnel.default;

  useEffect(() => {
    let stopped = false;
    void funnelApi
      .metrics(funnel.id)
      .then((rows) => !stopped && setMetrics(Object.fromEntries(rows.map((r) => [r.stage_id, r]))))
      .catch(() => undefined);
    return () => {
      stopped = true;
    };
  }, [funnel.id]);

  const entered = (draft: StageDraft) => (draft.id ? (metrics[draft.id]?.entered ?? 0) : 0);
  const summary = useMemo(() => {
    const first = drafts.length ? entered(drafts[0]) : 0;
    const last = drafts.length ? entered(drafts[drafts.length - 1]) : 0;
    const steps = drafts.slice(1).map((d, i) => {
      const before = entered(drafts[i]);
      return before ? entered(d) / before : null;
    });
    const known = steps.filter((v): v is number => v !== null);
    return {
      first,
      last,
      total: first ? Math.round((last / first) * 100) : null,
      average: known.length
        ? Math.round((known.reduce((a, b) => a + b, 0) / known.length) * 100)
        : null,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drafts, metrics]);

  const edit = (index: number, patch: Partial<StageDraft>) =>
    setDrafts((all) => all.map((d, i) => (i === index ? { ...d, ...patch } : d)));
  const move = (index: number, delta: number) =>
    setDrafts((all) => {
      const target = index + delta;
      if (target < 0 || target >= all.length) return all;
      const copy = [...all];
      [copy[index], copy[target]] = [copy[target], copy[index]];
      return copy;
    });

  const save = async () => {
    if (drafts.some((d) => !d.name.trim())) return setError("Cada etapa necesita un nombre.");
    setBusy(true);
    setError("");
    try {
      if (name.trim() && name.trim() !== funnel.name)
        await funnelApi.patch(funnel.id, { name: name.trim() });
      await funnelApi.saveStages(
        funnel.id,
        drafts.map((d) => ({ ...d, name: d.name.trim(), description: d.description.trim() })),
      );
      onSaved();
    } catch (e) {
      setError(problem(e));
    } finally {
      setBusy(false);
    }
  };
  const archive = async () => {
    if (!window.confirm(`¿Archivar el embudo «${funnel.name}»? Los chats siguen en la bandeja.`))
      return;
    setBusy(true);
    try {
      await funnelApi.patch(funnel.id, { archived: true });
      onArchived();
    } catch (e) {
      setError(problem(e));
      setBusy(false);
    }
  };

  const stat = (label: string, value: string) => (
    <div className="rounded-xl bg-slate-50 p-3">
      <p className="text-xl font-bold tabular-nums">{value}</p>
      <p className="text-xs text-muted">{label}</p>
    </div>
  );
  return (
    <Modal title={locked ? "Embudo «Contactos»" : "Configurar embudo"} onClose={onClose} wide>
      <div className="space-y-5">
        {locked ? (
          <p className="rounded-xl bg-primary-soft p-3 text-sm text-primary">
            Este embudo refleja el estado de cada contacto (Nuevo, Contactado, Cita agendada,
            Descartado) y es el mismo que ves en la bandeja. No se edita; para flujos propios, crea
            otro embudo.
          </p>
        ) : (
          <label className="block text-sm font-semibold">
            Nombre del embudo
            <input
              maxLength={60}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded-xl border border-line px-3 py-2 text-sm font-normal outline-none focus:border-primary"
            />
          </label>
        )}

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stat("Entraron a la primera etapa", String(summary.first))}
          {stat("Llegaron a la última", String(summary.last))}
          {stat("Conversión total", summary.total === null ? "—" : `${summary.total}%`)}
          {stat("Promedio por etapa", summary.average === null ? "—" : `${summary.average}%`)}
        </div>
        <p className="-mt-3 text-xs text-muted">
          Las cifras salen del registro de movimientos entre etapas, que empieza cuando se activaron
          los embudos: no incluyen lo anterior.
        </p>

        <ol className="space-y-2">
          {drafts.map((draft, index) => {
            const before = index ? entered(drafts[index - 1]) : 0;
            const here = entered(draft);
            return (
              <li
                key={draft.id ?? `new-${index}`}
                className="rounded-xl border border-line p-3"
                style={{ borderLeft: `4px solid ${draft.color}` }}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className="grid size-7 shrink-0 place-items-center rounded-full text-xs font-bold text-white"
                    style={{ background: draft.color }}
                  >
                    {index + 1}
                  </span>
                  <input
                    aria-label={`Nombre de la etapa ${index + 1}`}
                    maxLength={60}
                    disabled={locked}
                    value={draft.name}
                    onChange={(e) => edit(index, { name: e.target.value })}
                    className="min-w-40 flex-1 rounded-lg border border-line px-3 py-1.5 text-sm font-semibold outline-none focus:border-primary disabled:bg-slate-50"
                  />
                  <span className="text-xs text-muted tabular-nums">
                    {here} entraron
                    {index && before
                      ? ` · ${Math.round((here / before) * 100)}% de la anterior`
                      : ""}
                    {draft.id && metrics[draft.id] ? ` · ${metrics[draft.id].current} ahora` : ""}
                  </span>
                  {!locked && (
                    <span className="flex items-center gap-1">
                      <button
                        type="button"
                        aria-label="Subir etapa"
                        disabled={index === 0}
                        onClick={() => move(index, -1)}
                        className="rounded-md p-1.5 hover:bg-slate-100 disabled:opacity-30"
                      >
                        <ArrowUp size={15} />
                      </button>
                      <button
                        type="button"
                        aria-label="Bajar etapa"
                        disabled={index === drafts.length - 1}
                        onClick={() => move(index, 1)}
                        className="rounded-md p-1.5 hover:bg-slate-100 disabled:opacity-30"
                      >
                        <ArrowDown size={15} />
                      </button>
                      <button
                        type="button"
                        aria-label="Eliminar etapa"
                        disabled={drafts.length === 1}
                        onClick={() => setDrafts((all) => all.filter((_, i) => i !== index))}
                        className="rounded-md p-1.5 text-red-600 hover:bg-red-50 disabled:opacity-30"
                      >
                        <Trash2 size={15} />
                      </button>
                    </span>
                  )}
                </div>
                {!locked && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <input
                      aria-label={`Descripción de la etapa ${index + 1}`}
                      maxLength={200}
                      placeholder="Descripción (opcional)"
                      value={draft.description}
                      onChange={(e) => edit(index, { description: e.target.value })}
                      className="min-w-48 flex-1 rounded-lg border border-line px-3 py-1.5 text-xs outline-none focus:border-primary"
                    />
                    <span className="flex gap-1.5" role="radiogroup" aria-label="Color de la etapa">
                      {COLORS.map((color) => (
                        <button
                          key={color}
                          type="button"
                          role="radio"
                          aria-checked={draft.color === color}
                          aria-label={`Color ${color}`}
                          onClick={() => edit(index, { color })}
                          className={`size-6 rounded-full ${draft.color === color ? "ring-2 ring-ink ring-offset-1" : ""}`}
                          style={{ background: color }}
                        />
                      ))}
                    </span>
                  </div>
                )}
                {locked && draft.description && (
                  <p className="mt-1 text-xs text-muted">{draft.description}</p>
                )}
              </li>
            );
          })}
        </ol>

        {!locked && (
          <button
            type="button"
            disabled={drafts.length >= MAX_STAGES}
            onClick={() =>
              setDrafts((all) => [
                ...all,
                { id: null, name: "", color: COLORS[all.length % COLORS.length], description: "" },
              ])
            }
            className="flex items-center gap-2 rounded-xl border border-dashed border-primary px-4 py-2 text-sm font-semibold text-primary disabled:opacity-40"
          >
            <Plus size={16} /> Agregar etapa
          </button>
        )}
        {error && (
          <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">
            {error}
          </p>
        )}
        {!locked && (
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4">
            <button
              type="button"
              disabled={busy}
              onClick={() => void archive()}
              className="rounded-xl border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              Archivar embudo
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void save()}
              className="rounded-xl bg-primary px-5 py-2 text-sm font-bold text-white disabled:opacity-50"
            >
              Guardar embudo
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}
