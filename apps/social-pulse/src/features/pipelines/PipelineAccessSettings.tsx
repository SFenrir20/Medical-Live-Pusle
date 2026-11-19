import { useEffect, useState } from "react";
import apiClient from "@/services/api";
import { problem } from "@/features/chats/api";

type Policy = {
  id: number;
  name: string;
  site_id: number | null;
  allowed_user_ids: string[] | null;
  revision: number;
};
type Person = {
  id: string;
  name: string;
  role: string | null;
  manages_access: boolean;
  eligible_ids: number[];
  visible_ids: number[];
};
type Overview = { pipelines: Policy[]; users: Person[] };
const roles: Record<string, string> = {
  admin: "Admin",
  gerente: "Manager / Gerente",
  jefe_marketing: "Marketing",
  supervisor: "Supervisor",
  agente_ventas: "Agente",
  asesor: "Asesor",
};

export function PipelineAccessSettings() {
  const [data, setData] = useState<Overview | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [allowed, setAllowed] = useState<string[] | null>(null);
  const [revision, setRevision] = useState(0);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const pipe = data?.pipelines.find((p) => p.id === selected);
  const dirty =
    !!pipe &&
    JSON.stringify(allowed?.slice().sort() ?? null) !==
      JSON.stringify(pipe.allowed_user_ids?.slice().sort() ?? null);

  const select = (policy: Policy | undefined) => {
    setSelected(policy?.id ?? null);
    setAllowed(policy?.allowed_user_ids ?? null);
    setRevision(policy?.revision ?? 0);
    setNotice("");
  };
  const refresh = async (prefer?: number) => {
    setBusy(true);
    setError("");
    try {
      const next = (await apiClient.get<Overview>("/crm/pipelines/access")).data;
      setData(next);
      select(next.pipelines.find((p) => p.id === prefer) ?? next.pipelines[0]);
    } catch (e) {
      setError(problem(e));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    void refresh();
  }, []);

  const save = async () => {
    if (!pipe) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await apiClient.put(`/crm/pipelines/${pipe.id}/access`, {
        allowed_user_ids: allowed,
        revision,
      });
      await refresh(pipe.id);
      setNotice("Accesos guardados. Se aplican en la siguiente consulta del usuario.");
    } catch (e) {
      setError(problem(e));
    } finally {
      setBusy(false);
    }
  };

  const visible = (data?.users ?? []).filter((u) =>
    `${u.name} ${u.id} ${roles[u.role ?? ""] ?? ""}`.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <section className="mt-4 rounded-3xl border border-line bg-white p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-bold">Acceso a embudos</h2>
        <button
          type="button"
          disabled={busy}
          onClick={() => void refresh(selected ?? undefined)}
          className="text-sm text-primary disabled:opacity-50"
        >
          Actualizar lista
        </button>
      </div>
      <p className="mt-3 text-sm text-muted">
        Elige quién puede abrir cada embudo. Admin, manager y marketing conservan acceso para
        administrarlos. Las restricciones de sede y de conversaciones siguen vigentes.
      </p>
      <p className="mt-2 text-xs text-muted">
        Si falta un usuario, debe iniciar sesión al menos una vez. Los roles mostrados corresponden
        a su último acceso.
      </p>
      {error && (
        <p role="alert" className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="mt-3 text-sm text-emerald-700">
          {notice}
        </p>
      )}
      {!data && !error && <p className="mt-4 text-sm text-muted">Cargando accesos…</p>}
      {data && (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="text-sm">
              Embudo
              <select
                aria-label="Embudo para configurar accesos"
                value={selected ?? ""}
                disabled={busy}
                onChange={(e) =>
                  select(data.pipelines.find((p) => p.id === Number(e.target.value)))
                }
                className="mt-1 w-full rounded-xl border border-line bg-white p-2"
              >
                {data.pipelines.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              Visibilidad
              <select
                aria-label="Visibilidad del embudo"
                value={allowed === null ? "usual" : "selected"}
                disabled={busy || !pipe}
                onChange={(e) =>
                  setAllowed(
                    e.target.value === "usual"
                      ? null
                      : data.users
                          .filter(
                            (u) =>
                              selected !== null &&
                              u.eligible_ids.includes(selected) &&
                              !u.manages_access,
                          )
                          .map((u) => u.id),
                  )
                }
                className="mt-1 w-full rounded-xl border border-line bg-white p-2"
              >
                <option value="usual">Todos según rol y sede</option>
                <option value="selected">Solo usuarios seleccionados</option>
              </select>
            </label>
          </div>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Buscar usuario para accesos"
            placeholder="Buscar usuario o rol"
            className="mt-4 w-full rounded-xl border border-line px-3 py-2 text-sm"
          />
          <div className="mt-3 max-h-96 overflow-auto rounded-xl border border-line">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-slate-50">
                <tr>
                  <th className="p-3">Usuario</th>
                  <th className="p-3">Rol</th>
                  <th className="p-3">Acceso al embudo</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((u) => {
                  const eligible = selected !== null && u.eligible_ids.includes(selected);
                  const checked =
                    u.manages_access || (eligible && (allowed === null || allowed.includes(u.id)));
                  return (
                    <tr key={u.id} className="border-t border-line">
                      <td className="p-3">
                        <span className="font-semibold">{u.name}</span>
                        <p className="mt-1 text-xs text-muted">
                          Ve:{" "}
                          {data.pipelines
                            .filter((p) => u.visible_ids.includes(p.id))
                            .map((p) => p.name)
                            .join(", ") || "Ningún embudo"}
                        </p>
                      </td>
                      <td className="p-3">{roles[u.role ?? ""] ?? "Sin rol válido"}</td>
                      <td className="p-3">
                        <label className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            aria-label={`Acceso de ${u.name} a ${pipe?.name ?? "embudo"}`}
                            checked={checked}
                            disabled={busy || !eligible || u.manages_access || allowed === null}
                            onChange={(e) =>
                              setAllowed((old) =>
                                e.target.checked
                                  ? [...(old ?? []), u.id]
                                  : (old ?? []).filter((id) => id !== u.id),
                              )
                            }
                          />
                          <span className="text-xs">
                            {u.manages_access
                              ? "Siempre visible"
                              : !eligible
                                ? "Sin acceso por rol o sede"
                                : checked
                                  ? "Visible"
                                  : "Oculto"}
                          </span>
                        </label>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!visible.length && (
              <p className="p-4 text-sm text-muted">No hay usuarios con esa búsqueda.</p>
            )}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={busy || !dirty}
              onClick={() => void save()}
              className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {busy ? "Procesando…" : "Guardar accesos"}
            </button>
            {dirty && (
              <span className="text-xs text-amber-700">
                Cambios sin guardar. La lista «Ve» muestra los accesos guardados.
              </span>
            )}
          </div>
        </>
      )}
    </section>
  );
}
