import { useEffect, useRef, useState } from "react";
import { chatApi } from "./api";

export function ChatImage({ messageId }: { messageId: number }) {
  const root = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [url, setUrl] = useState("");
  const [failed, setFailed] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    if (root.current) observer.observe(root.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!visible) return;
    let cancelled = false,
      objectUrl = "";
    setFailed(false);
    void chatApi
      .image(messageId)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [messageId, visible, attempt]);
  return (
    <div ref={root} className="min-h-24 min-w-40">
      {url ? (
        <>
          <button
            type="button"
            onClick={() => dialog.current?.showModal()}
            aria-label="Abrir imagen"
          >
            <img
              src={url}
              alt="Imagen del mensaje"
              className="max-h-80 max-w-full rounded-lg object-contain"
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
              src={url}
              alt="Imagen ampliada"
              className="max-h-[80vh] max-w-full object-contain"
            />
          </dialog>
        </>
      ) : failed ? (
        <div className="p-3 text-xs text-amber-800">
          No se pudo recuperar la imagen. Puede haber vencido en WhatsApp.
          <button type="button" onClick={() => setAttempt((a) => a + 1)} className="ml-2 underline">
            Reintentar
          </button>
        </div>
      ) : (
        <span className="text-xs text-muted">Cargando imagen…</span>
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
