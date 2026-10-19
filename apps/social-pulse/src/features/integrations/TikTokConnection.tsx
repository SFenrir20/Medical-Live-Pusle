import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import apiClient from "@/services/api";

type Status = {
  configured: boolean;
  connections: { id: string; authorized_at: string; advertiser_ids: string[] }[];
};

const RESULTS: Record<string, string> = {
  connected:
    "Autorización guardada. La captura de DM y las consultas de estadísticas requieren sus propias integraciones.",
  invalid: "El enlace venció o no corresponde a este navegador. Inicia la conexión otra vez.",
  denied: "La autorización fue cancelada. Puedes volver a intentarlo.",
  configuration: "Falta configurar la conexión con TikTok en el servidor.",
  exchange_failed: "No pudimos completar la autorización con TikTok. Inicia la conexión otra vez.",
};

export function TikTokConnection() {
  const { user } = useAuth();
  const allowed = ["admin", "gerente", "jefe_marketing", "supervisor"].includes(user?.role ?? "");
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const outcome = new URLSearchParams(window.location.search).get("resultado") ?? "";

  useEffect(() => {
    if (!allowed) return;
    let active = true;
    apiClient
      .get<Status>("/integrations/tiktok/status")
      .then(({ data }) => {
        if (active) setStatus(data);
      })
      .catch(() => {
        if (active)
          setError("No se pudo consultar la conexión. Recarga la página para intentarlo otra vez.");
      });
    return () => {
      active = false;
    };
  }, [allowed]);

  async function connect() {
    setBusy(true);
    setError("");
    try {
      const { data } = await apiClient.post<{ authorization_url: string }>(
        "/integrations/tiktok/authorize",
      );
      const target = new URL(data.authorization_url);
      if (
        target.origin !== "https://business-api.tiktok.com" ||
        target.pathname !== "/portal/auth"
      ) {
        throw new Error("Unexpected authorization URL");
      }
      window.location.assign(target.href);
    } catch {
      setError("No se pudo iniciar la conexión. Comprueba la configuración e inténtalo otra vez.");
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-canvas p-6">
      <section className="mx-auto max-w-2xl rounded-3xl border border-line bg-white p-8">
        <a href="/" className="text-sm font-semibold text-primary">
          ← Volver a Social Pulse
        </a>
        <h1 className="mt-6 text-2xl font-bold">Conectar TikTok for Business</h1>
        {!allowed ? (
          <p className="mt-4 text-muted">Tu rol no permite gestionar esta conexión.</p>
        ) : (
          <>
            <p className="mt-3 text-sm leading-6 text-muted">
              Autoriza las cuentas publicitarias de tu empresa para preparar su integración con
              Social Pulse. Esta conexión no activa los mensajes directos ni cambia la captura
              actual de los LIVE.
            </p>
            {RESULTS[outcome] && (
              <p role="status" className="mt-5 rounded-xl bg-sky-50 p-4 text-sm">
                {RESULTS[outcome]}
              </p>
            )}
            {error && (
              <p role="alert" className="mt-4 text-sm text-red-700">
                {error}
              </p>
            )}
            {!status && !error && <p className="mt-4 text-sm text-muted">Consultando conexión…</p>}
            {status && (
              <>
                {!status.configured && (
                  <p className="mt-4 text-sm text-muted">
                    El administrador debe configurar las credenciales de TikTok antes de conectar
                    una cuenta.
                  </p>
                )}
                <button
                  type="button"
                  className="primary-button mt-5 disabled:opacity-50"
                  disabled={!status.configured || busy}
                  onClick={() => void connect()}
                >
                  {busy ? "Abriendo TikTok…" : "Autorizar en TikTok"}
                </button>
                <h2 className="mt-8 font-bold">Autorizaciones guardadas</h2>
                {status.connections.length === 0 ? (
                  <p className="mt-2 text-sm text-muted">
                    Todavía no hay autorizaciones guardadas.
                  </p>
                ) : (
                  <ul className="mt-3 space-y-3">
                    {status.connections.map((connection) => (
                      <li key={connection.id} className="rounded-xl border border-line p-4 text-sm">
                        <p>
                          {new Date(connection.authorized_at).toLocaleString("es-PE", {
                            timeZone: "America/Lima",
                          })}{" "}
                          (Lima)
                        </p>
                        <p className="mt-1 text-muted">
                          Cuentas publicitarias:{" "}
                          {connection.advertiser_ids.join(", ") || "Sin cuentas informadas"}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-4 text-xs text-muted">
                  Una autorización guardada puede ser revocada posteriormente en TikTok.
                </p>
              </>
            )}
          </>
        )}
      </section>
    </main>
  );
}
