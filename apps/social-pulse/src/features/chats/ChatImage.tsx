import { useEffect, useRef, useState } from "react";
import { useMedia, useNearScreen } from "./useMedia";

/** A photo of a message: loads when it comes near the screen, opens large on click. */
export function ChatImage({ messageId }: { messageId: number }) {
  const { near, ref } = useNearScreen();
  const media = useMedia(messageId, near);
  const dialog = useRef<HTMLDialogElement>(null);
  return (
    <div ref={ref} className="min-h-24 min-w-44">
      {media.status === "ready" ? (
        <>
          <button
            type="button"
            onClick={() => dialog.current?.showModal()}
            aria-label="Abrir imagen"
            className="block"
          >
            <img
              src={media.url}
              alt="Imagen del mensaje"
              className="max-h-80 max-w-full rounded-md object-contain"
            />
          </button>
          <dialog
            ref={dialog}
            className="m-auto max-h-[95vh] max-w-[95vw] rounded-xl p-3 backdrop:bg-black/70"
          >
            <button
              type="button"
              className="mb-2 block text-primary"
              onClick={() => dialog.current?.close()}
            >
              Cerrar imagen
            </button>
            <img
              src={media.url}
              alt="Imagen ampliada"
              className="max-h-[80vh] max-w-full object-contain"
            />
          </dialog>
        </>
      ) : media.status === "error" ? (
        <div className="p-3 text-xs text-amber-800">
          No se pudo recuperar la imagen. Puede haber vencido en WhatsApp.
          <button type="button" onClick={media.retry} className="ml-2 underline">
            Reintentar
          </button>
        </div>
      ) : (
        <div className="grid h-28 w-44 animate-pulse place-items-center rounded-md bg-black/5 text-xs text-muted">
          Cargando imagen…
        </div>
      )}
    </div>
  );
}

export function ImagePreview({ file }: { file: File }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    const value = URL.createObjectURL(file);
    setUrl(value);
    return () => URL.revokeObjectURL(value);
  }, [file]);
  return (
    <img
      src={url || undefined}
      alt="Imagen seleccionada para enviar"
      className="max-h-36 rounded-lg object-contain"
    />
  );
}
