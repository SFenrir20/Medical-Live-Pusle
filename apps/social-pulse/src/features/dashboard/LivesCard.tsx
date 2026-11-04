import { useEffect, useState } from "react";
import { Eye, Phone, Radio } from "lucide-react";
import type { LiveApi } from "@/features/workspace/api";
import { duration } from "@/features/chats/format";

/** "Transmisiones simultáneas": every account on air right now, monitored on its own. */
export function LivesCard({ lives, className = "" }: { lives: LiveApi[]; className?: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const live = lives.filter((l) => l.status === "live");
  return (
    <section
      className={`overflow-hidden rounded-[24px] bg-deep text-white ${className}`}
      aria-label="Transmisiones simultáneas"
    >
      <div className="flex flex-wrap items-center gap-4 border-b border-white/10 p-5">
        <span className="relative grid size-12 place-items-center rounded-2xl bg-white/10 text-cyan-300">
          <Radio size={22} />
          <span
            className={`absolute -right-1 -top-1 size-3 rounded-full ${live.length ? "animate-pulse bg-red-500" : "bg-slate-500"}`}
          />
        </span>
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-cyan-300">
            Transmisiones simultáneas
          </p>
          <p className="mt-0.5 text-lg font-bold">
            {live.length === 0
              ? "Ninguna cuenta en vivo ahora"
              : live.length === 1
                ? "1 cuenta en vivo ahora"
                : `${live.length} cuentas en vivo ahora`}
          </p>
        </div>
        <span className="ml-auto rounded-full bg-white/10 px-4 py-2 text-xs font-semibold text-slate-200">
          Monitoreo independiente por cuenta
        </span>
      </div>
      {live.length > 0 ? (
        <div
          className="grid divide-y divide-white/10 md:divide-x md:divide-y-0"
          style={{ gridTemplateColumns: `repeat(${Math.min(live.length, 3)}, minmax(0, 1fr))` }}
        >
          {live.map((l, index) => {
            const tone = [
              "text-cyan-300 bg-cyan-300",
              "text-emerald-300 bg-emerald-300",
              "text-violet-300 bg-violet-300",
            ][index % 3];
            const [text, dot] = tone.split(" ");
            return (
              <article key={l.id} className="p-5">
                <div className="flex items-center justify-between">
                  <span
                    className={`inline-flex items-center gap-2 text-[11px] font-bold tracking-wider ${text}`}
                  >
                    <span className={`size-2 animate-pulse rounded-full ${dot}`} /> EN VIVO
                  </span>
                  <span className="font-mono text-sm text-cyan-100">
                    {duration((now - new Date(l.started_at).getTime()) / 1000)}
                  </span>
                </div>
                <div className="mt-4 flex items-center gap-3">
                  <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-white text-ink">
                    <svg viewBox="0 0 24 24" className="size-5 fill-current" aria-hidden>
                      <path d="M19.6 6.8a5.4 5.4 0 0 1-3.3-1.7 5.4 5.4 0 0 1-1.3-3.1h-3.4v13.2a2.9 2.9 0 1 1-2-2.8V9a6.3 6.3 0 1 0 5.4 6.2V9.4a8.7 8.7 0 0 0 4.9 1.6V7.6a5.4 5.4 0 0 1-.3-.8z" />
                    </svg>
                  </span>
                  <div className="min-w-0">
                    <strong className="block truncate text-base">
                      @{(l.account ?? "").replace(/^@/, "")}
                    </strong>
                    <span className="block truncate text-xs text-slate-400">
                      Transmitiendo con {l.tiktoker ?? "responsable sin asignar"}
                    </span>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2 text-xs font-semibold">
                  <span className="inline-flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2">
                    <Eye size={14} className="text-cyan-300" />
                    {l.metrics.current_viewers ?? "—"} en línea
                  </span>
                  <span className="inline-flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2">
                    <Phone size={14} className="text-amber-300" />
                    {l.metrics.phones_captured} teléfonos
                  </span>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="p-6 text-sm text-slate-400">
          Cuando una cuenta salga en vivo aparecerá aquí con su tiempo, su audiencia y los teléfonos
          captados.
        </p>
      )}
    </section>
  );
}
