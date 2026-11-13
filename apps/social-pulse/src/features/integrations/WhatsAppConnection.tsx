import { useEffect, useState } from "react";
import { chatApi, problem, type WaStatus } from "@/features/chats/api";
import { fullDate } from "@/features/chats/format";
import { pollVisible } from "@/features/chats/polling";

const STATES: Record<string, string> = {
  connected: "Conectado",
  connecting: "Conectando…",
  disconnected: "Desconectado",
  qr: "Pendiente de escanear el QR",
  relink_required: "Requiere nueva vinculación",
  wrong_number: "La cuenta no coincide con el número vinculado",
  unavailable: "Conector no disponible",
};

/** Mounted only for users allowed to manage the shared WhatsApp connection. */
export function WhatsAppConnection() {
  const [status, setStatus] = useState<WaStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [readError, setReadError] = useState("");
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    if (busy) return;
    return pollVisible(
      async (signal) => {
        const next = await chatApi.status(signal);
        if (signal.aborted) return;
        setStatus(next);
        setReadError("");
      },
      3000,
      (error) => {
        setStatus(null); // Do not leave an expired QR or a stale connected badge on screen.
        setReadError(problem(error, "No se pudo consultar WhatsApp. Reintentando…"));
      },
    );
  }, [busy]);

  const connect = async () => {
    setBusy(true);
    setActionError("");
    try {
      setStatus(await chatApi.connect());
    } catch (error) {
      setActionError(problem(error, "No se pudo iniciar la vinculación. Inténtalo otra vez."));
    } finally {
      setBusy(false);
    }
  };
  const canConnect =
    status && ["disconnected", "relink_required", "wrong_number"].includes(status.state);

  return (
    <section className="mt-4 rounded-3xl border border-line bg-white p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-bold">Conexión de WhatsApp</h2>
        <p
          role="status"
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            status?.state === "connected"
              ? "bg-emerald-50 text-emerald-700"
              : "bg-amber-50 text-amber-800"
          }`}
        >
          {status
            ? STATES[status.state] || "Estado desconocido"
            : readError
              ? "Sin información actual"
              : "Consultando…"}
        </p>
      </div>
      <p className="mt-3 text-sm text-muted">
        Vincula el WhatsApp que utiliza el equipo. Esta conexión es independiente de la sesión de
        cada asesor.
      </p>
      {status?.phone && <p className="mt-2 text-sm">Número vinculado: {status.phone}</p>}
      {status?.state === "disconnected" && status.retry_at && (
        <p className="mt-3 text-sm text-muted">
          Reconexión automática prevista: {fullDate(status.retry_at)}.
        </p>
      )}
      {status?.state === "connected" && status.sync_ok === false && (
        <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
          WhatsApp está conectado, pero la sincronización está atrasada. Es necesario revisar el
          servicio de sincronización del servidor.
        </p>
      )}
      {status?.sync_at && (
        <p className="mt-2 text-xs text-muted">Última sincronización: {fullDate(status.sync_at)}</p>
      )}
      {status?.state === "unavailable" && (
        <p className="mt-3 text-sm text-amber-800">
          El servidor no puede acceder al conector de WhatsApp. Revisa su configuración y
          disponibilidad.
        </p>
      )}
      {(readError || actionError) && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {actionError || readError}
        </p>
      )}
      {(canConnect || busy) && (
        <button
          type="button"
          disabled={busy}
          onClick={() => void connect()}
          className="mt-4 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {busy ? "Iniciando…" : "Vincular / reconectar"}
        </button>
      )}
      {status?.state === "qr" && status.qr && (
        <div className="mt-4 flex flex-wrap items-center gap-5">
          <img src={status.qr} width={220} height={220} alt="QR de vinculación de WhatsApp" />
          <div className="max-w-sm text-sm">
            <p>En tu teléfono: WhatsApp → Dispositivos vinculados → Vincular un dispositivo.</p>
            <p className="mt-2 text-muted">
              El QR se actualiza automáticamente. Solo supervisores y administradores pueden
              gestionarlo.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
