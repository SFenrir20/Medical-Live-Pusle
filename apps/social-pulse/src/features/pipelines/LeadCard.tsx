import { memo, useEffect, useRef, useState } from "react";
import { MoreVertical, User } from "lucide-react";
import { Avatar, Preview } from "@/features/chats/ConversationList";
import { ago, nice, shortTime, WAIT_LONG_MINUTES, waitedMinutes } from "@/features/chats/format";
import { type Card, type FunnelStage, money } from "./api";

/** One conversation as a card of the board. Memoised: the board refreshes every few seconds. */
export const LeadCard = memo(function LeadCard({
  card,
  stageId,
  stages,
  isDefault,
  onMove,
  onValue,
  onRemove,
  onOpen,
  dragging,
  onDragStart,
  onDragEnd,
}: {
  card: Card;
  /** The column this card is in. */
  stageId: number;
  stages: FunnelStage[];
  isDefault: boolean;
  onMove: (card: Card, stageId: number) => void;
  onValue: (card: Card, cents: number) => void;
  onRemove: (card: Card) => void;
  onOpen: (card: Card) => void;
  dragging: boolean;
  onDragStart: (card: Card) => void;
  onDragEnd: () => void;
}) {
  const [menu, setMenu] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setMenu(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu]);

  const unread = card.unread > 0;
  const late = card.waiting && waitedMinutes(card.last?.at) >= WAIT_LONG_MINUTES;
  const saveValue = () => {
    setEditing(false);
    const cents = Math.round(Number(draft.replace(",", ".")) * 100);
    if (Number.isFinite(cents) && cents >= 0 && cents !== card.value_cents) onValue(card, cents);
  };
  return (
    <div
      ref={box}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData("text/plain", String(card.id));
        event.dataTransfer.effectAllowed = "move";
        onDragStart(card);
      }}
      onDragEnd={onDragEnd}
      className={`relative cursor-grab rounded-xl border bg-white p-3 text-left shadow-sm transition hover:shadow-md active:cursor-grabbing ${
        dragging ? "opacity-40" : ""
      } ${unread ? "border-primary/40" : "border-line"}`}
    >
      <div className="flex items-start gap-2.5">
        <button
          type="button"
          onClick={() => onOpen(card)}
          className="flex min-w-0 flex-1 items-start gap-2.5 text-left"
          aria-label={`Abrir la conversación con ${card.name || nice(card.phone)}`}
        >
          <Avatar name={card.name} phone={card.phone} size="size-10" />
          <span className="min-w-0 flex-1">
            <span className="flex items-baseline justify-between gap-2">
              <span
                className={`truncate text-sm text-[#111b21] ${unread ? "font-bold" : "font-semibold"}`}
              >
                {card.name || nice(card.phone)}
              </span>
              <span className="shrink-0 text-[11px] text-muted">
                {shortTime(card.last_message_at)}
              </span>
            </span>
            <span className="mt-0.5 block text-xs text-[#667781]">
              <Preview c={card} />
            </span>
          </span>
        </button>
        <div className="relative">
          <button
            type="button"
            aria-label="Opciones de la tarjeta"
            aria-expanded={menu}
            onClick={() => setMenu((v) => !v)}
            className="rounded-md p-1 text-muted hover:bg-slate-100"
          >
            <MoreVertical size={15} />
          </button>
          {menu && (
            <div className="absolute right-0 top-full z-20 mt-1 w-52 rounded-xl border border-line bg-white p-1 text-sm shadow-xl">
              <p className="px-3 py-1 text-[11px] font-bold uppercase tracking-wide text-muted">
                Mover a
              </p>
              {stages.map((stage) => (
                <button
                  key={stage.id}
                  type="button"
                  disabled={stage.id === stageId}
                  onClick={() => {
                    setMenu(false);
                    onMove(card, stage.id);
                  }}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-left hover:bg-slate-50 disabled:opacity-40"
                >
                  <span className="size-2.5 rounded-full" style={{ background: stage.color }} />
                  {stage.name}
                </button>
              ))}
              {!isDefault && (
                <button
                  type="button"
                  onClick={() => {
                    setMenu(false);
                    onRemove(card);
                  }}
                  className="mt-1 w-full rounded-lg border-t border-line px-3 py-1.5 text-left text-red-700 hover:bg-red-50"
                >
                  Quitar de este embudo
                </button>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
        <span className="flex items-center gap-1 truncate text-muted">
          <User size={12} />
          {card.is_mine ? "Tuyo" : card.advisor_name || "Sin asignar"}
        </span>
        {card.waiting && (
          <span
            className={`rounded-full px-2 py-0.5 font-semibold ${late ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700"}`}
          >
            Sin responder · {ago(card.last?.at)}
          </span>
        )}
        {unread && (
          <span className="ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-[#25d366] px-1.5 font-bold text-white">
            {card.unread > 99 ? "99+" : card.unread}
          </span>
        )}
        {editing ? (
          <input
            autoFocus
            inputMode="decimal"
            aria-label="Valor de la oportunidad en soles"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={saveValue}
            onKeyDown={(e) => {
              if (e.key === "Enter") saveValue();
              if (e.key === "Escape") setEditing(false);
            }}
            className="w-24 rounded-md border border-primary px-2 py-0.5 text-right outline-none"
          />
        ) : (
          <button
            type="button"
            title="Valor de la oportunidad"
            onClick={() => {
              setDraft(card.value_cents ? String(card.value_cents / 100) : "");
              setEditing(true);
            }}
            className={`rounded-full px-2 py-0.5 font-semibold ${card.value_cents ? "bg-emerald-50 text-emerald-700" : "text-muted hover:bg-slate-100"} ${unread || card.waiting ? "" : "ml-auto"}`}
          >
            {card.value_cents ? money(card.value_cents) : "+ Valor"}
          </button>
        )}
      </div>
    </div>
  );
});
