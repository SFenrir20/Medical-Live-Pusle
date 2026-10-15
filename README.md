# Medical Social Pulse

Aplicación web React/Vite con Clerk, API FastAPI, PostgreSQL y captura de LIVE de TikTok.
Incluye panel de Marketing, atención de contactos y puente con Medical 360.

## Estructura

- `apps/social-pulse`: único frontend web.
- `backend`: API, captura, procesamiento, contactos, permisos y migraciones Alembic.
- `infra/compose.yaml`: servicios `web`, `api`, `db`; perfil `live` con `monitor` y `worker`.
- `docs`: configuración, contrato de API y operación.

## Ejecutar con Docker

Copiar `.env.example` a `.env` y configurar Clerk antes de construir:

```sh
docker compose --env-file .env -f infra/compose.yaml up --build -d
```

Web: `http://localhost:8080`. Para capturar TikTok, añadir `--profile live` antes de `up`.
En Dokploy el dominio apunta al servicio **web**, puerto interno **80**.
`VITE_CLERK_PUBLISHABLE_KEY` es un argumento de compilación; cambiarlo requiere reconstruir.

Ver [desarrollo local](docs/dev-local.md), [Clerk](docs/clerk.md),
[API](docs/social-live-api.md) y [operación](docs/operations.md).

## Transición

Se retiraron la aplicación Expo, la selección para marcar asistencia y las rutas de entrada,
salida, relevo e historial. No se generan APK/IPA. El frontend Social Pulse se sirve como `web`;
se eliminó el servicio duplicado `social`.

Las migraciones publicadas y las tablas históricas de asistencia se conservan para actualizar
bases existentes sin pérdida de datos. Su metadata está aislada en `shared/retired_models.py`,
solo para Alembic; la aplicación ya no las consulta ni escribe.
Los reportes usan la TikToker asignada explícitamente al LIVE o «Sin asignar».
