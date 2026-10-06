# Medical LivePulse

Aplicación Expo para web, Android e iOS, con autenticación Clerk y API FastAPI.

Implementado: selección de cuenta TikTok, entrada/salida, relevo e historial propio en PostgreSQL.
En desarrollo: monitoreo TikTok, conciliación, métricas e integración con Medical 360.

## Estructura

- `apps/mobile`: aplicación web y móvil.
- `backend`: API, Alembic y servicios.
- `infra`: Docker Compose y verificación del despliegue.
- `docs`: configuración y reglas.

Ver `docs/shifts.md` para el flujo de jornadas y `docs/dokploy-local.md` para desplegar en el servidor de pruebas.
