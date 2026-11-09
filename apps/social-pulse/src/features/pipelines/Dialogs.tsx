import { FormEvent, ReactNode, useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { chatApi, type ConversationItem, problem } from "@/features/chats/api";
import { nice } from "@/features/chats/format";
import { funnelApi, type FunnelStage, type Template } from "./api";

export function Modal({
  title,
  onClose,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`flex max-h-[92dvh] w-full flex-col rounded-2xl bg-white shadow-2xl ${wide ? "max-w-4xl" : "max-w-lg"}`}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-base font-bold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="rounded-lg p-1 text-muted hover:bg-slate-100"
          >
            <X size={18} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}

export function NewFunnelDialog({
  templates,
  onCreate,
  onClose,
}: {
  templates: Template[];
  onCreate: (name: string, template: string) => Promise<string | null>;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [template, setTemplate] = useState("tiktok_live");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const chosen = templates.find((t) => t.key === template);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    const failed = await onCreate(name.trim() || chosen?.name || "Nuevo embudo", template);
    setBusy(false);
    if (failed) setError(failed);
  };
  return (
    <Modal title="Nuevo embudo" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <label className="block text-sm font-semibold">
          Nombre del embudo
          <input
            autoFocus
            maxLength={60}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={chosen?.name ?? "Comercial"}
            className="mt-1 w-full rounded-xl border border-line px-3 py-2 text-sm font-normal outline-none focus:border-primary"
          />
        </label>
        <fieldset>
          <legend className="text-sm font-semibold">Punto de partida</legend>
          <div className="mt-2 space-y-2">
            {templates.map((t) => (
              <label
                key={t.key}
                className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 ${template === t.key ? "border-primary bg-primary-soft" : "border-line"}`}
              >
                <input
                  type="radio"
                  name="template"
                  checked={template === t.key}
                  onChange={() => setTemplate(t.key)}
                  className="mt-1"
                />
                <span>
                  <span className="block text-sm font-semibold">
                    {t.key === "blank" ? "En blanco" : t.name}
                  </span>
                  <span className="block text-xs text-muted">{t.stages.join(" → ")}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        {error && (
          <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-line px-4 py-2 text-sm font-semibold"
          >
            Cancelar
          </button>
          <button
            disabled={busy}
            className="rounded-xl bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            Crear embudo
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Pick conversations (the ones you may see) and put them in a stage of this funnel. */
export function AddChatsDialog({
  funnelId,
  stages,
  onClose,
  onChanged,
}: {
  funnelId: number;
  stages: FunnelStage[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<ConversationItem[]>([]);
  const [stage, setStage] = useState(stages[0]?.id ?? 0);
  const [added, setAdded] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let stopped = false;
    const timer = setTimeout(() => {
      void chatApi
        .conversations("all", q, 0)
        .then((r) => !stopped && setItems(r.items))
        .catch((e) => !stopped && setError(problem(e)));
    }, 250);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [q]);
  const add = async (item: ConversationItem) => {
    setBusy(item.id);
    setError("");
    try {
      await funnelApi.putCard(funnelId, item.id, { stage_id: stage });
      setAdded((old) => new Set(old).add(item.id));
      onChanged();
    } catch (e) {
      setError(problem(e));
    } finally {
      setBusy(null);
    }
  };
  return (
    <Modal title="Agregar chats al embudo" onClose={onClose}>
      <div className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <label className="relative min-w-48 flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Buscar por nombre, teléfono o mensaje"
              className="w-full rounded-xl border border-line py-2 pl-9 pr-3 text-sm outline-none focus:border-primary"
            />
          </label>
          <select
            aria-label="Etapa de destino"
            value={stage}
            onChange={(e) => setStage(Number(e.target.value))}
            className="rounded-xl border border-line px-3 py-2 text-sm"
          >
            {stages.map((s) => (
              <option key={s.id} value={s.id}>
                Entra a: {s.name}
              </option>
            ))}
          </select>
        </div>
        <p className="text-xs text-muted">
          Si el chat ya estaba en este embudo, pasa a la etapa elegida. Para agregar o mover un chat
          debe ser tuyo (o tomarlo primero en la bandeja).
        </p>
        {error && (
          <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">
            {error}
          </p>
        )}
        <ul className="divide-y divide-slate-100 rounded-xl border border-line">
          {items.map((item) => (
            <li key={item.id} className="flex items-center gap-3 px-3 py-2.5">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold">
                  {item.name || nice(item.phone)}
                </span>
                <span className="block truncate text-xs text-muted">
                  {nice(item.phone)} · {item.is_mine ? "Tuyo" : item.advisor_name || "Sin asignar"}
                </span>
              </span>
              <button
                type="button"
                disabled={busy === item.id || added.has(item.id)}
                onClick={() => void add(item)}
                className="rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50"
              >
                {added.has(item.id) ? "Agregado" : "Agregar"}
              </button>
            </li>
          ))}
          {!items.length && <li className="p-6 text-center text-sm text-muted">Sin resultados.</li>}
        </ul>
      </div>
    </Modal>
  );
}
