import { useEffect, useRef, useState } from "react";
import { Download, FileText, Loader2, Mic, Music, Pause, Play, RotateCw } from "lucide-react";
import type { Message } from "./api";
import { ChatImage } from "./ChatImage";
import { bytes, clip } from "./format";
import { saveAs, useMedia, useNearScreen } from "./useMedia";

type Media = NonNullable<Message["media"]>;

// Only one audio plays at a time, as in WhatsApp.
let playing: HTMLAudioElement | null = null;

const RATES = [1, 1.5, 2];

function AudioPlayer({ id, media, out }: { id: number; media: Media; out: boolean }) {
  const { near, ref } = useNearScreen();
  const file = useMedia(id, near);
  const audio = useRef<HTMLAudioElement>(null);
  const [on, setOn] = useState(false);
  const [time, setTime] = useState(0);
  const [length, setLength] = useState(media.seconds ?? 0);
  const [rate, setRate] = useState(1);
  const [broken, setBroken] = useState(false);
  const voice = media.kind === "voice";

  useEffect(
    () => () => {
      if (playing === audio.current) playing = null;
    },
    [],
  );

  const toggle = () => {
    const el = audio.current;
    if (!el) return;
    if (el.paused) {
      if (playing && playing !== el) playing.pause();
      playing = el;
      el.playbackRate = rate;
      void el.play().catch(() => setBroken(true));
    } else el.pause();
  };
  const cycle = () => {
    const next = RATES[(RATES.indexOf(rate) + 1) % RATES.length];
    setRate(next);
    if (audio.current) audio.current.playbackRate = next;
  };

  if (file.status === "error" || broken)
    return (
      <div ref={ref} className="w-60 space-y-1 text-xs text-amber-800">
        <p>
          {broken
            ? "Tu navegador no puede reproducir este audio."
            : "No se pudo recuperar el audio. Puede haber vencido en WhatsApp."}
        </p>
        <span className="flex gap-3">
          <button
            type="button"
            onClick={() => (setBroken(false), file.retry())}
            className="underline"
          >
            Reintentar
          </button>
          {broken && file.url && (
            <a href={file.url} download="audio" className="underline">
              Descargar
            </a>
          )}
        </span>
      </div>
    );

  const shown = on || time > 0 ? time : length;
  return (
    <div ref={ref} className="flex w-64 items-center gap-2.5 py-0.5 sm:w-72">
      <button
        type="button"
        onClick={toggle}
        disabled={file.status !== "ready"}
        aria-label={on ? "Pausar" : "Reproducir"}
        className={`grid size-10 shrink-0 place-items-center rounded-full text-white disabled:opacity-60 ${out ? "bg-[#00a884]" : "bg-[#667781]"}`}
      >
        {file.status === "loading" || file.status === "idle" ? (
          <Loader2 size={18} className="animate-spin" />
        ) : on ? (
          <Pause size={18} fill="currentColor" />
        ) : (
          <Play size={18} fill="currentColor" className="translate-x-px" />
        )}
      </button>
      <div className="min-w-0 flex-1">
        <input
          type="range"
          aria-label="Posición del audio"
          min={0}
          max={length || 1}
          step={0.1}
          value={Math.min(time, length || 1)}
          disabled={file.status !== "ready" || !length}
          onChange={(e) => {
            const value = Number(e.target.value);
            setTime(value);
            if (audio.current) audio.current.currentTime = value;
          }}
          className="block h-1.5 w-full cursor-pointer accent-[#00a884] disabled:cursor-default"
        />
        <div className="mt-1 flex items-center justify-between text-[11px] text-[#667781]">
          <span className="tabular-nums">{clip(shown) || "0:00"}</span>
          {on || rate !== 1 ? (
            <button
              type="button"
              onClick={cycle}
              className="rounded-full bg-black/10 px-1.5 font-semibold text-[#3b4a54]"
              aria-label="Velocidad"
            >
              {rate}x
            </button>
          ) : voice ? (
            <Mic size={13} aria-label="Mensaje de voz" />
          ) : (
            <Music size={13} aria-label="Audio" />
          )}
        </div>
      </div>
      <audio
        ref={audio}
        src={file.url || undefined}
        preload="metadata"
        onPlay={() => setOn(true)}
        onPause={() => setOn(false)}
        onEnded={() => {
          setOn(false);
          setTime(0);
        }}
        onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration;
          if (Number.isFinite(d) && d > 0) setLength(d);
        }}
        onError={() => file.url && setBroken(true)}
      />
    </div>
  );
}

function VideoTile({ id, media }: { id: number; media: Media }) {
  const [wanted, setWanted] = useState(false);
  const file = useMedia(id, wanted);
  if (file.status === "ready")
    return (
      <video
        src={file.url}
        controls
        autoPlay
        playsInline
        className="max-h-80 max-w-full rounded-md bg-black"
      />
    );
  return (
    <button
      type="button"
      onClick={() => (file.status === "error" ? file.retry() : setWanted(true))}
      className="relative grid h-40 w-64 place-items-center rounded-md bg-slate-800 text-white sm:w-72"
      aria-label="Reproducir video"
    >
      <span className="grid size-12 place-items-center rounded-full bg-black/50">
        {file.status === "loading" ? (
          <Loader2 className="animate-spin" />
        ) : file.status === "error" ? (
          <RotateCw size={20} />
        ) : (
          <Play fill="currentColor" className="translate-x-0.5" />
        )}
      </span>
      <span className="absolute bottom-1.5 left-2 text-[11px]">
        {file.status === "error"
          ? "No se pudo cargar. Toca para reintentar"
          : [clip(media.seconds), bytes(media.size)].filter(Boolean).join(" · ")}
      </span>
    </button>
  );
}

function DocumentCard({ id, media, out }: { id: number; media: Media; out: boolean }) {
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");
  const name = media.name || "documento";
  return (
    <div
      className={`flex w-64 items-center gap-3 rounded-lg p-2.5 sm:w-72 ${out ? "bg-[#c9f1c2]" : "bg-[#f3f4f6]"}`}
    >
      <span className="grid size-10 shrink-0 place-items-center rounded-md bg-white text-[#667781]">
        <FileText size={20} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-semibold" title={name}>
          {name}
        </span>
        <span className="block text-[11px] text-[#667781]">
          {state === "error" ? "No se pudo descargar. Reintenta" : bytes(media.size) || "Documento"}
        </span>
      </span>
      <button
        type="button"
        disabled={state === "busy"}
        onClick={() => {
          setState("busy");
          saveAs(id, name).then(
            () => setState("idle"),
            () => setState("error"),
          );
        }}
        aria-label={`Descargar ${name}`}
        className="grid size-9 shrink-0 place-items-center rounded-full border border-[#667781]/40 text-[#3b4a54] hover:bg-white disabled:opacity-50"
      >
        {state === "busy" ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
      </button>
    </div>
  );
}

function Sticker({ id }: { id: number }) {
  const { near, ref } = useNearScreen();
  const file = useMedia(id, near);
  return (
    <div ref={ref} className="size-36">
      {file.status === "ready" ? (
        <img src={file.url} alt="Sticker" className="size-full object-contain" />
      ) : file.status === "error" ? (
        <button type="button" onClick={file.retry} className="p-2 text-xs text-amber-800 underline">
          Sticker no disponible. Reintentar
        </button>
      ) : (
        <div className="size-full animate-pulse rounded-xl bg-black/5" />
      )}
    </div>
  );
}

/** The attachment of a message, by kind. */
export function MessageMedia({ message }: { message: Message }) {
  const media = message.media;
  if (!media) return null;
  const out = message.direction === "out";
  switch (media.kind) {
    case "image":
      return <ChatImage messageId={message.id} />;
    case "voice":
    case "audio":
      return <AudioPlayer id={message.id} media={media} out={out} />;
    case "video":
      return <VideoTile id={message.id} media={media} />;
    case "document":
      return <DocumentCard id={message.id} media={media} out={out} />;
    case "sticker":
      return <Sticker id={message.id} />;
  }
}
