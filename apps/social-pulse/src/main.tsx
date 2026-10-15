import React from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider } from "@clerk/react";
import { esES } from "@clerk/localizations";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import "./index.css";

// Public (publishable) key only. The Secret Key never belongs in this app.
const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;

function MissingConfig() {
  return (
    <main className="grid min-h-screen place-items-center bg-canvas p-6">
      <section className="max-w-md rounded-3xl border border-line bg-white p-8 text-sm text-muted">
        <h1 className="text-lg font-bold text-ink">Falta configurar el acceso</h1>
        <p className="mt-3">
          Define <code>VITE_CLERK_PUBLISHABLE_KEY</code> en <code>.env.local</code> y vuelve a
          iniciar la aplicación.
        </p>
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {publishableKey ? (
      <ClerkProvider publishableKey={publishableKey} localization={esES}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ClerkProvider>
    ) : (
      <MissingConfig />
    )}
  </React.StrictMode>,
);
