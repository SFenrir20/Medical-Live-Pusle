# Contrato API de Social Pulse

El contrato de ingestión, reportes, contactos y permisos se documenta en
[social-live-api.md](social-live-api.md).

- `GET /health`: salud del servicio (público).
- `GET /api/auth/me`: perfil y permisos de Social Pulse, requiere sesión Clerk.
- `/api/social-live/*`: ingestión autenticada de LIVE y eventos.
- `/api/marketing/tiktok/*`: reportes autorizados.
- `/api/inbox`, `/api/leads/*`, `/api/team`: atención y equipo con permisos por rol.
- `/v1/integrations/medical360/*`: compatibilidad del puente de Medical 360.

Nginx publica `/api/health` hacia `/health`; mantiene `/api` para las rutas nuevas y
traduce `/api/v1/*` a `/v1/*` para las integraciones existentes.
Las antiguas rutas `/v1/shifts/*` y la atribución por asistencia devuelven 404.
