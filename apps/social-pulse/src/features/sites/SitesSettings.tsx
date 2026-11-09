import { useCallback, useEffect, useState } from "react";
import apiClient from "@/services/api";
import { problem } from "@/features/chats/api";

type Site = {
  id: number;
  key: string;
  name: string;
  aliases: string[];
  active: boolean;
  pipeline_id: number | null;
};
type Advisor = {
  user_id: string;
  name: string;
  site_id: number | null;
  shift_start: string;
  shift_end: string;
  active: boolean;
  online: boolean;
};
type Preview = {
  is_appointment: boolean;
  patient?: string | null;
  site?: string | null;
  site_text?: string;
  date?: string | null;
  hour?: string | null;
};

const SAMPLE = `Muy bien, le envío los datos de su cita:
Paciente: Camila Sánchez
Fecha: 1-8
Hora: 3pm a 4pm
Sede: SJM
Dirección: Av. Miguel Iglesias 625`;

const field = "rounded-lg border border-line px-3 py-1.5 text-sm outline-none focus:border-primary";

/** Admin: the branches (and how each is written in the appointment message), where each advisor
 *  works and their hours, and a tester for the appointment message. */
export function SitesSettings() {
  const [sites, setSites] = useState<Site[]>([]);
  const [staff, setStaff] = useState<Advisor[]>([]);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [sample, setSample] = useState(SAMPLE);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [newName, setNewName] = useState("");

  const load = useCallback(async () => {
    const [a, b] = await Promise.all([
      apiClient.get<{ items: Site[] }>("/crm/sites"),
      apiClient.get<{ items: Advisor[] }>("/crm/sites/staff"),
    ]);
    setSites(a.data.items);
    setStaff(b.data.items);
  }, []);
  useEffect(() => {
    void load().catch((e) => setError(problem(e)));
  }, [load]);

  const run = async (label: string, work: () => Promise<unknown>) => {
    setError("");
    setSaved("");
    try {
      await work();
      setSaved(label);
      await load();
    } catch (e) {
      setError(problem(e));
    }
  };
  const editSite = (id: number, patch: Partial<Site>) =>
    setSites((all) => all.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  const editAdvisor = (id: string, patch: Partial<Advisor>) =>
    setStaff((all) => all.map((s) => (s.user_id === id ? { ...s, ...patch } : s)));

  return (
    <section className="mt-4 rounded-3xl border border-line bg-white p-6">
      <h2 className="font-bold">Sedes y asesores</h2>
      <p className="mt-2 text-sm leading-6 text-muted">
        Cuando la Central de Citas confirma una cita, el paciente entra solo al embudo de su sede y
        pasa al asesor cuyo horario cubre la hora de la cita. Si en un horario se cruzan varios, va
        primero quien esté conectado y tenga menos pacientes abiertos. Si nadie cubre esa hora,
        queda libre para los asesores de la sede.
      </p>
      {error && (
        <p role="alert" className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="mt-3 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800">
          {saved}
        </p>
      )}

      <h3 className="mt-6 text-sm font-bold">Sedes</h3>
      <p className="text-xs text-muted">
        «Cómo se escribe» son los nombres con que la Central pone la sede en el mensaje, separados
        por coma.
      </p>
      <ul className="mt-3 space-y-2">
        {sites.map((site) => (
          <li
            key={site.id}
            className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-3"
          >
            <input
              aria-label={`Nombre de la sede ${site.name}`}
              value={site.name}
              maxLength={60}
              onChange={(e) => editSite(site.id, { name: e.target.value })}
              className={`${field} w-40 font-semibold`}
            />
            <input
              aria-label={`Cómo se escribe ${site.name}`}
              value={site.aliases.join(", ")}
              placeholder="SJM, San Juan de Miraflores"
              onChange={(e) => editSite(site.id, { aliases: e.target.value.split(",") })}
              className={`${field} min-w-48 flex-1`}
            />
            <label className="flex items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={site.active}
                onChange={(e) => editSite(site.id, { active: e.target.checked })}
              />{" "}
              Activa
            </label>
            <button
              type="button"
              className="rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-white"
              onClick={() =>
                void run(`Sede «${site.name}» guardada.`, () =>
                  apiClient.patch(`/crm/sites/${site.id}`, {
                    name: site.name,
                    aliases: site.aliases,
                    active: site.active,
                  }),
                )
              }
            >
              Guardar
            </button>
          </li>
        ))}
      </ul>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (newName.trim())
            void run(`Sede «${newName.trim()}» creada.`, async () => {
              await apiClient.post("/crm/sites", { name: newName.trim(), aliases: [] });
              setNewName("");
            });
        }}
      >
        <input
          aria-label="Nombre de la nueva sede"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Nueva sede"
          maxLength={60}
          className={`${field} w-48`}
        />
        <button className="rounded-lg border border-line px-3 py-1.5 text-xs font-bold text-primary">
          Agregar sede
        </button>
      </form>

      <h3 className="mt-8 text-sm font-bold">Asesores y horarios</h3>
      <p className="text-xs text-muted">
        Aparecen quienes ya iniciaron sesión con el rol <code>asesor</code> en Clerk. El horario es
        de Lima y se repite todos los días.
      </p>
      <ul className="mt-3 space-y-2">
        {staff.map((person) => (
          <li
            key={person.user_id}
            className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-3"
          >
            <span
              className={`size-2.5 rounded-full ${person.online ? "bg-emerald-500" : "bg-slate-300"}`}
              title={person.online ? "Conectado" : "Desconectado"}
            />
            <span className="w-40 truncate text-sm font-semibold">{person.name}</span>
            <select
              aria-label={`Sede de ${person.name}`}
              value={person.site_id ?? ""}
              className={field}
              onChange={(e) =>
                editAdvisor(person.user_id, { site_id: Number(e.target.value) || null })
              }
            >
              <option value="">Sin sede</option>
              {sites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <input
              aria-label={`Entrada de ${person.name}`}
              type="time"
              value={person.shift_start}
              className={field}
              onChange={(e) => editAdvisor(person.user_id, { shift_start: e.target.value })}
            />
            <span className="text-xs text-muted">a</span>
            <input
              aria-label={`Salida de ${person.name}`}
              type="time"
              value={person.shift_end}
              className={field}
              onChange={(e) => editAdvisor(person.user_id, { shift_end: e.target.value })}
            />
            <label className="flex items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={person.active}
                onChange={(e) => editAdvisor(person.user_id, { active: e.target.checked })}
              />{" "}
              Recibe pacientes
            </label>
            <button
              type="button"
              disabled={!person.site_id}
              className="rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-white disabled:opacity-40"
              onClick={() =>
                void run(`${person.name} guardado.`, () =>
                  apiClient.put(`/crm/sites/staff/${person.user_id}`, {
                    site_id: person.site_id,
                    shift_start: person.shift_start,
                    shift_end: person.shift_end,
                    active: person.active,
                  }),
                )
              }
            >
              Guardar
            </button>
          </li>
        ))}
        {!staff.length && (
          <li className="rounded-xl border border-dashed border-line p-4 text-sm text-muted">
            Todavía no hay asesores. Asigna el rol <code>asesor</code> en Clerk; aparecen cuando
            inician sesión.
          </li>
        )}
      </ul>

      <h3 className="mt-8 text-sm font-bold">Probar el mensaje de cita</h3>
      <p className="text-xs text-muted">
        Pega un mensaje de la Central para ver cómo lo entiende el sistema, sin mover a nadie.
      </p>
      <textarea
        aria-label="Mensaje de cita de prueba"
        rows={6}
        value={sample}
        onChange={(e) => setSample(e.target.value)}
        className={`${field} mt-2 w-full font-mono text-xs`}
      />
      <button
        type="button"
        className="mt-2 rounded-lg border border-line px-3 py-1.5 text-xs font-bold text-primary"
        onClick={() => {
          setError("");
          void apiClient
            .post<Preview>("/crm/automation/preview", { text: sample })
            .then((r) => setPreview(r.data))
            .catch((e) => setError(problem(e)));
        }}
      >
        Probar
      </button>
      {preview && (
        <p
          className={`mt-3 rounded-xl p-3 text-sm ${preview.is_appointment ? "bg-emerald-50 text-emerald-900" : "bg-amber-50 text-amber-900"}`}
        >
          {preview.is_appointment
            ? `Se entiende como cita · paciente ${preview.patient ?? "—"} · sede ${preview.site ?? `«${preview.site_text}» no reconocida`} · fecha ${preview.date ?? "no entendida"} · hora ${preview.hour ?? "no entendida"}`
            : "No se reconoce como confirmación de cita: faltan Paciente/Fecha/Hora/Sede."}
        </p>
      )}
    </section>
  );
}
