import { Copy, MessageCircle } from "lucide-react";
import type { LiveLead } from "./api";
import { clock, nice } from "./format";

/** TikTok LIVE side of the omnichannel inbox: the numbers your own LIVE audience left, one click
 *  from a WhatsApp conversation. It lists the contacts assigned to you (supervisors: all). */
export function LivePanel({
  leads,
  onOpen,
  opening,
}: {
  leads: LiveLead[];
  onOpen: (phone: string) => void;
  opening: boolean;
}) {
  return (
    <aside className="flex min-h-0 flex-1 flex-col overflow-y-auto border-l border-line bg-white">
      <div className="flex items-center gap-3 border-b border-line p-4">
        <span className="grid size-8 place-items-center rounded-xl bg-slate-900 text-xs font-black text-white">
          TT
        </span>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-primary">
            Bandeja social en vivo
          </p>
          <p className="font-bold">TikTok LIVE</p>
        </div>
      </div>
      <p className="px-4 pt-3 text-xs text-muted">Comentarios con teléfonos detectados.</p>
      <ul className="divide-y divide-line">
        {leads.map((lead) => (
          <li key={lead.id} className="px-4 py-5">
            <p className="flex items-center justify-between text-[11px]">
              <span className="font-bold text-primary">{lead.user ?? "Sin usuario"}</span>
              <span className="text-muted">{clock(lead.enteredAt)}</span>
            </p>
            <p className="mt-1 line-clamp-2 text-xs text-muted">
              {lead.message ?? "Teléfono registrado sin comentario"}
            </p>
            {lead.phone && (
              <div className="mt-2 flex flex-col items-start gap-2">
                <button
                  type="button"
                  onClick={() => void navigator.clipboard.writeText(lead.phone ?? "")}
                  className="flex w-full items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs font-medium text-amber-700"
                  title="Copiar teléfono"
                >
                  <Copy size={12} /> <span>{nice(lead.phone)}</span>
                </button>
                <button
                  type="button"
                  disabled={opening}
                  onClick={() => onOpen(lead.phone as string)}
                  className="flex items-center gap-2 rounded-lg px-1 py-1 text-xs text-primary disabled:opacity-50"
                  title="Abrir chat de WhatsApp"
                  aria-label="Abrir chat de WhatsApp"
                >
                  <MessageCircle size={13} /> Abrir chat
                </button>
              </div>
            )}
          </li>
        ))}
        {!leads.length && (
          <li className="py-6 text-center text-sm text-muted">Aún no hay teléfonos de tus LIVE.</li>
        )}
      </ul>
    </aside>
  );
}
