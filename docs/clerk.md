# Acceso con Clerk

Social Pulse tiene usuarios independientes de Medical 360. Clerk gestiona registro y sesión;
FastAPI valida los JWT con las claves públicas de la misma instancia.
Los roles y permisos se validan en el servidor en cada petición.

## Configuración

- Frontend: `VITE_CLERK_PUBLISHABLE_KEY`, únicamente la Publishable Key.
- Backend: `CLERK_ISSUER`, `CLERK_AUTHORIZED_PARTIES` como array JSON de orígenes exactos.
- `CORS_ORIGINS`: necesario si la web y la API están en orígenes distintos durante desarrollo.
- `ADMIN_USER_IDS=["user_..."]`: administradores iniciales de Social Pulse.

Usar la misma instancia Clerk para la clave pública y el issuer. En producción, configurar
los orígenes HTTPS reales. Los secretos de integraciones se guardan solo en el backend;
nunca en variables `VITE_*`.

En Docker la web usa `/api` por Nginx. En desarrollo consultar `dev-local.md`.
Cambiar una variable `VITE_*` requiere reconstruir la web. Reiniciar la API tras cambiar
sus variables de entorno. No se necesita una Secret Key para verificar los JWT.

## Permisos

`GET /api/auth/me` devuelve el perfil, rol y permisos de Social Pulse.
La matriz vigente está en `social-live-api.md`. El registro no concede administración.
La identidad de Clerk no asigna cuentas TikTok ni registra asistencia.
