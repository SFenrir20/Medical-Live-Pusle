import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { chatApi, problem } from "./api";

export function HistoryRecovery({ id, connected }: { id: number; connected: boolean }) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const allowed = user?.permissions.some((p) => p === "wa:manage" || p === "wa:send");
  if (!allowed) return null;

  const recover = async (restart: boolean) => {
    setBusy(true);
    try {
      const result = await chatApi.recoverHistory(id, restart);
      setNotice(
        result.state === "waiting"
          ? "Ya hay una solicitud reciente. Espera un minuto antes de pedir otro lote."
          : result.state === "requested"
            ? "Solicitud enviada: hasta 50 mensajes anteriores. Aparecerán con su fecha original si WhatsApp los entrega. Puedes continuar con otro lote después de un minuto."
            : "No se pudo confirmar la solicitud. Espera un minuto antes de reintentar; la respuesta aún puede llegar.",
      );
    } catch (error) {
      setNotice(problem(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="w-full rounded-xl bg-primary-soft p-3 text-xs">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={busy || !connected}
          onClick={() => void recover(false)}
          className="font-semibold text-primary disabled:opacity-50"
        >
          {busy ? "Solicitando…" : "Recuperar historial"}
        </button>
        <button
          type="button"
          disabled={busy || !connected}
          onClick={() => void recover(true)}
          className="text-muted underline disabled:opacity-50"
        >
          Buscar de nuevo desde recientes
        </button>
      </div>
      <p className="mt-2 text-muted">
        Pide mensajes anteriores al teléfono vinculado, sin cerrar la sesión. Cada solicitud
        continúa desde el lote recibido anteriormente. WhatsApp puede entregar solo una parte del
        historial.
      </p>
      {notice && (
        <p role="status" className="mt-2 text-ink">
          {notice}
        </p>
      )}
    </div>
  );
}
