# Medical LivePulse

Aplicación Expo para web, Android e iOS, con autenticación Clerk y API FastAPI.

Implementado: selección de cuenta TikTok, entrada/salida, relevo e historial propio en PostgreSQL.
Código implementado: monitoreo persistente, conciliación por horario, métricas, contactos/OCR web, roles y puente Medical 360. Requiere validar captura e importación con servicios reales.

Ver `docs/phases.md` para fases y límites; `docs/operations.md` para desplegar y configurar las integraciones.

## Estructura

- `apps/mobile`: aplicación web y móvil.
- `backend`: API, Alembic y servicios.
- `infra`: Docker Compose y verificación del despliegue.
- `docs`: configuración y reglas.

Ver `docs/shifts.md` para el flujo de jornadas y `docs/dokploy-local.md` para desplegar en el servidor de pruebas.
