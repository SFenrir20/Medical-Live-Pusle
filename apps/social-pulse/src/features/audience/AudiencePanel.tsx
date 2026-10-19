import { useCallback, useEffect, useState } from "react";
import { Gem, Heart, MessageCircle, Phone, Share2, Timer, UserCheck } from "lucide-react";
import { errorMessage, LiveApi } from "@/features/workspace/api";
import { AudienceSort, AudienceTop, fetchAudienceTop } from "./api";

const SORTS: { key: AudienceSort; label: string; accumulatedOnly?: boolean }[] = [
  { key: "diamonds", label: "Regalos" },
  { key: "comments", label: "Comentarios" },
  { key: "likes", label: "Likes" },
  { key: "shares", label: "Compartidos" },
  { key: "presence", label: "Tiempo visible" },
  { key: "lives", label: "Lives en que aparece", accumulatedOnly: true },
];

const limaDay = (iso: string) =>
  new Date(iso).toLocaleString("es-PE", {
    timeZone: "America/Lima",
    day: "2-digit",
    month: "2-digit",
    hour: "numeric",
    minute: "2-digit",
  });

function duration(seconds: number) {
  if (seconds < 60) return "—";
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

const number = (value: number) => value.toLocaleString("es-PE");

/** Fans of the channel: who comments, gives gifts or stays around. Managers only (supervisor,
 *  marketing head, manager): the API refuses everyone else. Phones are never shown here. */
export function AudiencePanel({ lives }: { lives: LiveApi[] }) {
  const [scope, setScope] = useState<string>("period");
  const [sort, setSort] = useState<AudienceSort>("diamonds");
  const [data, setData] = useState<AudienceTop | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const accumulated = scope === "period";
  const selected = lives.find((live) => live.id === scope);
  const liveNow = selected?.status === "live";

  const load = useCallback(async () => {
    try {
      // "Lives en que aparece" only makes sense across lives.
      const chosen = accumulated || sort !== "lives" ? sort : "diamonds";
      setData(
        await fetchAudienceTop(
          accumulated ? { sort: chosen, days: 30 } : { sort: chosen, liveId: scope },
        ),
      );
      setError("");
    } catch (err) {
      setError(errorMessage(err, "No se pudo cargar la audiencia."));
    } finally {
      setLoading(false);
    }
  }, [scope, sort, accumulated]);

  useEffect(() => {
    setLoading(true);
    void load();
    // Refresh only what can still change: the accumulated view and a LIVE on air.
    if (!accumulated && !liveNow) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 30000);
    return () => window.clearInterval(timer);
  }, [load, accumulated, liveNow]);

  return (
    <section className="mt-6">
      <h2 className="text-xl font-bold">Audiencia destacada</h2>
      <p className="mt-1 max-w-3xl text-sm text-muted">
        Quiénes comentan, regalan o se quedan más en los LIVES. Se guarda por{" "}
        {data?.retention_days ?? 30} días. El tiempo visible es una estimación: TikTok no avisa
        cuándo sale cada persona y quien mira en silencio no aparece.
      </p>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <select
          value={scope}
          onChange={(event) => setScope(event.target.value)}
          className="rounded-xl border border-line bg-white px-3 py-2 text-sm"
          aria-label="Periodo o transmisión"
        >
          <option value="period">Acumulado · últimos 30 días</option>
          {lives.map((live) => (
            <option key={live.id} value={live.id}>
              {limaDay(live.started_at)} · {live.account ? `@${live.account}` : live.id}
              {live.title ? ` · ${live.title}` : ""}
              {live.status === "live" ? " (en vivo)" : ""}
            </option>
          ))}
        </select>
        <div className="flex flex-wrap gap-2">
          {SORTS.filter((item) => accumulated || !item.accumulatedOnly).map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setSort(item.key)}
              className={`rounded-xl px-3 py-2 text-xs font-semibold ${
                sort === item.key
                  ? "bg-primary-soft text-primary"
                  : "border border-line bg-white text-muted hover:bg-slate-50"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </p>
      )}
      {loading && <p className="mt-4 text-sm text-muted">Cargando…</p>}
      {!loading && data && !data.items.length && (
        <p className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-muted">
          Todavía no hay actividad de audiencia registrada
          {accumulated ? " en este periodo" : " para esta transmisión"}.
        </p>
      )}

      {data && data.items.length > 0 && (
        <div className="mt-4 overflow-x-auto rounded-2xl border border-line bg-white">
          <p className="border-b border-line px-4 py-3 text-xs text-muted">
            Mostrando las {data.items.length} primeras de {number(data.members)} personas con
            actividad.
          </p>
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-3">#</th>
                <th className="px-2 py-3">Usuario</th>
                <th className="px-2 py-3">
                  <Gem size={13} className="mr-1 inline" />
                  Regalos
                </th>
                <th className="px-2 py-3">
                  <MessageCircle size={13} className="mr-1 inline" />
                  Comentarios
                </th>
                <th className="px-2 py-3">
                  <Heart size={13} className="mr-1 inline" />
                  Likes
                </th>
                <th className="px-2 py-3">
                  <Share2 size={13} className="mr-1 inline" />
                  Compart.
                </th>
                <th className="px-2 py-3">
                  <Timer size={13} className="mr-1 inline" />
                  Visible
                </th>
                {accumulated && <th className="px-2 py-3">Lives</th>}
                <th className="px-2 py-3" />
              </tr>
            </thead>
            <tbody>
              {data.items.map((fan, index) => (
                <tr key={fan.user_key} className="border-t border-line">
                  <td className="px-4 py-3 font-bold text-muted">{index + 1}</td>
                  <td className="px-2 py-3">
                    <span className="block font-semibold">{fan.name ?? fan.user}</span>
                    <span className="text-xs text-muted">@{fan.user}</span>
                  </td>
                  <td className="px-2 py-3">
                    {fan.diamonds ? (
                      <>
                        <strong>{number(fan.diamonds)}</strong>
                        <span className="text-xs text-muted"> 💎 · {fan.gifts} regalos</span>
                      </>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td className="px-2 py-3">{number(fan.comments)}</td>
                  <td className="px-2 py-3">{number(fan.likes)}</td>
                  <td className="px-2 py-3">{number(fan.shares)}</td>
                  <td className="px-2 py-3">{duration(fan.presence_seconds)}</td>
                  {accumulated && <td className="px-2 py-3">{fan.lives}</td>}
                  <td className="px-2 py-3">
                    <span className="flex flex-wrap gap-1">
                      {fan.followed && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-bold text-emerald-700">
                          <UserCheck size={11} /> Siguió
                        </span>
                      )}
                      {fan.left_contact && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2 py-1 text-[10px] font-bold text-sky-700">
                          <Phone size={11} /> Dejó contacto
                        </span>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
