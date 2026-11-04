import { FormEvent, useCallback, useEffect, useState } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { chatApi, problem, QuickReply } from "@/features/chats/api";

const input =
  "w-full rounded-xl border border-line bg-white px-3 py-2 text-sm outline-none focus:border-primary";
const empty = { title: "", shortcut: "", body: "", active: true };

/** The pre-written messages ("mensajes pregrabados"): a supervisor or admin writes them once and
 *  every agent inserts them in a chat with a shortcut (/precio) or the lightning button.
 *  {{nombre}} (or {{nombre|paciente}} with a fallback) is replaced by the contact's name. */
export function QuickRepliesManager({ canManage }: { canManage: boolean }) {
  const [items, setItems] = useState<QuickReply[]>([]);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await chatApi.quickReplies(true));
    } catch (e) {
      setError(problem(e));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (editing) await chatApi.updateReply(editing, form);
      else await chatApi.createReply(form);
      setForm(empty);
      setEditing(null);
      await load();
    } catch (e) {
      setError(problem(e));
    } finally {
      setBusy(false);
    }
  };
  const remove = async (reply: QuickReply) => {
    if (!window.confirm(`¿Borrar «${reply.title}»?`)) return;
    try {
      await chatApi.deleteReply(reply.id);
      await load();
    } catch (e) {
      setError(problem(e));
    }
  };

  return (
    <section className="mt-5 rounded-2xl border border-line bg-white p-5">
      <h3 className="text-lg font-bold">Mensajes pregrabados</h3>
      <p className="mt-1 text-sm text-muted">
        Respuestas para precios, ubicaciones, preparación, recuperación y horarios. Las asesoras las
        usan con un atajo como <code>/precio</code>.
      </p>
      {error && (
        <p role="alert" className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {items.map((r) => (
          <article
            key={r.id}
            className={`rounded-xl border border-line p-4 ${r.active ? "" : "opacity-60"}`}
          >
            <p className="flex items-center gap-2 font-semibold">
              {r.title}{" "}
              <code className="rounded bg-slate-100 px-1.5 text-xs font-normal text-muted">
                /{r.shortcut}
              </code>
              {!r.active && <span className="text-[10px] font-bold text-amber-700">OCULTO</span>}
            </p>
            <p className="mt-2 whitespace-pre-wrap text-sm text-muted">{r.body}</p>
            {canManage && (
              <p className="mt-3 flex gap-3 text-xs font-bold">
                <button
                  type="button"
                  className="flex items-center gap-1 text-primary"
                  onClick={() => {
                    setEditing(r.id);
                    setForm({
                      title: r.title,
                      shortcut: r.shortcut,
                      body: r.body,
                      active: r.active,
                    });
                  }}
                >
                  <Pencil size={12} /> Editar
                </button>
                <button
                  type="button"
                  className="flex items-center gap-1 text-red-600"
                  onClick={() => void remove(r)}
                >
                  <Trash2 size={12} /> Borrar
                </button>
              </p>
            )}
          </article>
        ))}
        {!items.length && (
          <p className="rounded-xl border border-dashed border-line p-6 text-sm text-muted md:col-span-2">
            Todavía no hay mensajes pregrabados.
          </p>
        )}
      </div>
      {canManage && (
        <form onSubmit={save} className="mt-5 space-y-3 rounded-xl bg-slate-50 p-4">
          <p className="text-sm font-bold">{editing ? "Editar mensaje" : "Nuevo mensaje"}</p>
          <div className="grid gap-3 md:grid-cols-[1fr_200px]">
            <label className="text-xs font-bold">
              Título
              <input
                className={`${input} mt-1`}
                value={form.title}
                maxLength={80}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="Precio de la valoración"
                required
              />
            </label>
            <label className="text-xs font-bold">
              Atajo
              <input
                className={`${input} mt-1`}
                value={form.shortcut}
                maxLength={31}
                onChange={(e) => setForm({ ...form, shortcut: e.target.value })}
                placeholder="/precio"
                required
              />
            </label>
          </div>
          <label className="block text-xs font-bold">
            Mensaje
            <textarea
              className={`${input} mt-1 h-28`}
              value={form.body}
              maxLength={4000}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
              placeholder="Hola {{nombre|}}, la valoración con el cirujano es gratuita…"
              required
            />
          </label>
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={form.active}
              onChange={(e) => setForm({ ...form, active: e.target.checked })}
            />{" "}
            Disponible para las asesoras
          </label>
          <div className="flex gap-2">
            <button
              disabled={busy}
              className="rounded-xl bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
            >
              {editing ? "Guardar cambios" : "Crear mensaje"}
            </button>
            {editing && (
              <button
                type="button"
                onClick={() => {
                  setEditing(null);
                  setForm(empty);
                }}
                className="rounded-xl border border-line bg-white px-4 py-2 text-sm font-semibold"
              >
                Cancelar
              </button>
            )}
          </div>
        </form>
      )}
    </section>
  );
}
