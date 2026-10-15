# Medical Social Pulse

Aplicación web para monitorear comentarios de transmisiones en vivo y mensajes sociales de
TikTok e Instagram. Construida con React, Vite, TypeScript y Tailwind CSS.

## Desarrollo

El servidor de desarrollo de Figma Make se inicia automáticamente. Fuera de Figma Make:

```bash
pnpm install
pnpm dev
```

## Acceso

El inicio de sesión lo gestiona **Clerk** (usuario o correo, Google, recuperación de contraseña).
El **rol** lo asigna el backend (`GET /api/auth/me`); el navegador nunca decide permisos.

| Rol | Pantalla |
|---|---|
| `agente_ventas` | Solo su perfil (vista de agente) |
| `gerente` | Marketing |
| `jefe_marketing` | Pantalla del jefe de marketing |
| `supervisor` | Ambas, con selector de vista |

Una persona que entra por primera vez queda como `agente_ventas`. El administrador técnico
(`ADMIN_USER_IDS` del backend) asigna los demás roles con `PUT /api/auth/users/{id}/role`.

## Variables de entorno

Copia `.env.example` a `.env.local`:

```env
VITE_CLERK_PUBLISHABLE_KEY=pk_test_xxxxx   # solo la clave publicable
VITE_API_URL=http://localhost:8000/api
```

La instancia de Clerk debe tener los mismos `CLERK_ISSUER` y `CLERK_AUTHORIZED_PARTIES`
(origen de esta web) configurados en el backend. Para que solo entren personas autorizadas,
desactiva el registro abierto en Clerk o usa invitaciones.

## Comandos

```bash
pnpm dev          # Servidor Vite
pnpm build        # Typecheck y build de producción
pnpm format       # Formatea src/
pnpm format:check # Verifica el formato de src/
```

## Sesión

La sesión web se persiste en `localStorage`. Al cerrar sesión se eliminan el token y el usuario
guardados.
