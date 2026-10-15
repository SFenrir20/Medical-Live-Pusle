# Medical Social Pulse

Único frontend web del proyecto, construido con React, Vite, TypeScript y Tailwind CSS.
Incluye paneles de Marketing y atención de contactos, con acceso mediante Clerk.
El backend decide los roles y permisos; el navegador no asigna privilegios.

## Desarrollo

Copiar `.env.example` a `.env.local` y configurar `VITE_CLERK_PUBLISHABLE_KEY`
y `VITE_API_URL=http://localhost:8000/api`.

```sh
pnpm install --frozen-lockfile
pnpm dev
pnpm build
```

Vite usa el puerto 8443 por defecto. El backend debe autorizar ese origen en Clerk y CORS.
`pnpm build` valida TypeScript y genera `dist`. La sesión la gestiona el SDK de Clerk.

## Docker

El servicio `web` de `../../infra/compose.yaml` construye esta carpeta y sirve en el puerto
interno 80. Usa `/api` mediante Nginx. La clave pública es un argumento de compilación:
si cambia, reconstruir. Los secretos de integración pertenecen exclusivamente al backend.

Ver `../../docs/social-live-api.md` para permisos, datos conectados y límites de captura.
