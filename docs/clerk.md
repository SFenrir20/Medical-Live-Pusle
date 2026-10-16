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

## Roles (se asignan en Clerk)

Clerk es la única fuente de roles. Cada persona tiene en **Public metadata** (solo editable desde
el panel de Clerk o su Backend API; el usuario no puede cambiarlo):

```json
{ "livepulse": { "role": "supervisor" } }
```

| Código | Acceso |
|---|---|
| `agente_ventas` | Atención de contactos (ve los libres y los suyos) |
| `gerente` | Marketing y reportes |
| `jefe_marketing` | Marketing y reportes |
| `supervisor` | Vista agente y Marketing |

Sin rol, o con un código desconocido, la persona entra a Clerk pero **no ve ninguna vista**
(la API responde 403 y la app muestra el motivo). `ADMIN_USER_IDS` queda solo como acceso de
emergencia (equivale a supervisor) por si los metadatos se configuran mal.

### Configurar la instancia (una vez)

1. **Sessions → Customize session token** y guardar:
   ```json
   { "metadata": "{{user.public_metadata}}" }
   ```
   El rol viaja firmado dentro del token: no hace falta consultar a Clerk en cada petición ni
   una Secret Key. (La claim se puede renombrar con `CLERK_ROLES_CLAIM`.)
2. **Users → (persona) → Public metadata** y pegar el JSON de arriba con su código.
3. Para impedir registros no autorizados: Clerk → *User & authentication → Restrictions*
   (desactivar el registro abierto o usar invitaciones).

### Cambios y vigencia

Un cambio de rol se aplica al renovarse la sesión (el token dura ~60 s; la app lo renueva sola).
Para que sea inmediato, la persona puede recargar la página.

### Si aún no personalizaste el token (alternativa)

Definir `CLERK_SECRET_KEY` en el **servidor**: la API leerá `public_metadata` desde la Backend
API de Clerk (con caché de 60 s) cuando el token no traiga la claim. Si Clerk no responde, la API
contesta 503 (reintentar), no deniega en silencio. Nunca poner esta clave en variables `VITE_*`.

### Qué hace el servidor

- `GET /api/auth/me`: rol, vistas y permisos que **el servidor** leyó en la sesión.
- Cada ruta valida el permiso con ese rol; la base de datos no decide accesos. Guarda solo un
  directorio (nombre y último rol visto) para listar asesores a los supervisores.
- Ya no existen rutas para asignar roles (`/api/auth/users`, `/v1/staff/*`): se gestionan en Clerk.
- La matriz de permisos vigente está en `social-live-api.md` y `modules/identity/roles.py`.

La identidad de Clerk no asigna cuentas TikTok ni registra asistencia.
