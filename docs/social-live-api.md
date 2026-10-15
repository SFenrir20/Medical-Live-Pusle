# Medical Social Pulse ↔ Medical 360: flujo de datos único

```
TikTok ─► monitor ─► raw_events ─► worker (publicación) ─► lives / live_metrics /
                     (registro de        │                   phone_registry / captured_phones
                      eventos)           └── idempotente      │
                                           (published_at)     ▼
                      Medical Social Pulse ◄── API ──► PostgreSQL ◄── API ──► Medical 360
```

Ningún frontend habla con otro. Todo pasa por la API.

## Fuente de datos principal

| Capa | Tablas | Quién escribe |
|---|---|---|
| Registro de eventos (verdad cruda) | `raw_events` (+ `broadcasts`, estado del monitor) | monitor |
| Modelo de lectura (lo que consumen las pantallas) | `lives`, `live_metrics`, `live_comments` (temporal), `phone_registry` (contacto único), `captured_phones` (apariciones), `contact_audit` | worker y API |
| Turnos | `shifts` (independiente del LIVE) | app de marcación |

El worker pliega cada evento de `raw_events` en el modelo de lectura **una sola vez**: la marca
`raw_events.published_at` es permanente (sobrevive a la limpieza). El historial anterior se
convierte en el primer ciclo del worker sin duplicar nada. El modelo analítico anterior
(`event_facts`, `leads`, `/v1/analytics`, `/v1/contacts`) queda como **legado** para la app móvil
antigua: se alimenta del mismo registro de eventos, pero ya no es la fuente de estados de
contacto. `/v1/integrations/medical360/{monitor,inbox}` ahora son adaptadores del modelo único.

## Autenticación

Cabecera `Authorization: Bearer <token>`.

| Quién | Credencial | Alcance |
|---|---|---|
| Captura (servidor de Social Live) | `SOCIAL_LIVE_TOKEN` | `ingest`: crear lives, eventos, teléfonos |
| Medical 360 (servidor) | `MEDICAL360_TOKEN` | `read` + `contacts:read_all` |
| Medical 360, exportación | `MEDICAL360_EXPORT_TOKEN` | además `export` |
| Personas (Clerk) | JWT de sesión; rol guardado en el servidor | ver tabla de roles |

Los tokens de servicio **nunca** van al navegador. Ninguna persona puede escribir eventos
(`ingest`). Un token vacío queda deshabilitado.

## Roles y permisos de atención

| Rol | Pantalla | Estadísticas | Contactos |
|---|---|---|---|
| `agente_ventas` | su perfil | — | ve los libres y los suyos; tomar, liberar, cambiar estado de los suyos |
| `gerente`, `jefe_marketing` | marketing | leer y exportar | solo conteos (no ve teléfonos) |
| `supervisor` | ambas | leer y exportar | ve todos; asigna a cualquiera; historial |
| `admin` (`ADMIN_USER_IDS`) | ambas | todo | todo + gestión de roles |

Permisos: `contacts:read`, `contacts:claim`, `contacts:update`, `contacts:read_all`,
`contacts:assign_any` (más `read`, `export`, `roles:manage`). Matriz en
`modules/identity/roles.py`. Se validan en el servidor.

Atención (`/api`): `GET /inbox`, `PATCH /leads/{id}` (`action: claim|release|assign`,
`status`, `expected_status`, `expect_unassigned`), `GET /leads/summary`, `GET /team`,
`GET /leads/{id}/history`, `GET /auth/me`, `PUT /auth/me/profile`.

- Tomar un contacto es una actualización condicionada: si dos asesores lo intentan a la vez,
  uno recibe `409`. Cambiar el estado de un contacto libre lo toma.
- La fecha del **primer contacto** (`contacted_at`) se guarda una sola vez y no cambia al
  reabrir el estado.
- Cada cambio queda en `contact_audit` (quién, qué, antes, después, cuándo).
- Un contacto de otra persona no aparece para un agente (`404`).

## Contacto único y primera captura

- Un teléfono (E.164) es **un contacto** en `phone_registry`, creado en su **primera captura**
  en cualquier cuenta y cualquier LIVE. La unicidad la garantiza la base de datos (inserciones
  simultáneas: una gana, la otra es una aparición posterior).
- Las apariciones posteriores se guardan en `captured_phones` (`is_new = false`).
- Si llega tarde un evento con hora **anterior**, pasa a ser la primera captura y la anterior
  se degrada.
- Reportes por día, semana, mes, hora, cuenta y TikToker usan la **fecha de primera captura**
  en calendario de Lima (un contacto a las 23:50 de Lima cuenta en ese día).

## Transmisión, turnos y atribución

Un live **no pertenece a una persona**: transmisión (`lives`), turnos (`shifts`) y atribución
(por intervalo `[inicio, fin)`) son independientes. Sin evidencia de turno: **«Sin asignar»**
(`lives.tiktoker_id` es opcional y solo declara un tramo sin turno). `GET /lives/{id}` incluye
`intervals` y `tiktokers`. Los contadores a nivel de live se reparten por tiempo de turno solo
cuando se filtra por persona; los teléfonos se atribuyen por la hora de su primera captura.

## Ingestión — `/api/social-live` (token `ingest`)

`POST /accounts`, `POST /tiktokers`, `POST /lives`, `POST /lives/{id}/events` (uno o
`{"events": [...]}` hasta 500), `POST /lives/{id}/comments`, `POST /lives/{id}/phones`,
`PATCH /phones/{contactId}`, `PATCH /lives/{id}/finish`.

`event_type`: `comment`, `like`, `view`, `viewer`, `unique_viewers`, `interested`, `follow`,
`donation`, `share`, `direct_message`, `phone_detected`, `phone_manual`.

- `viewer`: muestra de espectadores **simultáneos** (alimenta pico y promedio).
- `unique_viewers`: total de espectadores únicos **solo si una fuente real lo reporta**.
- `direct_message`: cuenta lo que el emisor informa; no implica captura de mensajes privados.
- `timestamp` sin zona = hora de Lima. No se aceptan fechas futuras.
- `event_id` hace idempotentes los reintentos.

## Consulta — `/api/marketing/tiktok` (token `read`, o rol)

`overview`, `lives`, `lives/{id}`, `lives/{id}/metrics`, `lives/{id}/comments`,
`lives/{id}/phones`, `lives/{id}/comments/export` (XLSX en memoria, permiso `export`),
`ranking`, `accounts/performance`, `hourly-performance`, `contact-performance`, y para
Medical 360: `monitor`, `inbox` y `numbers` (los dos últimos con `contacts:read_all`).
Filtros: `date_from`, `date_to` (fecha o ISO; sin zona = Lima), `tiktoker_id`, `account_id`.

## Definiciones (cada cifra tiene fuente o es «no disponible»)

| Cifra | Significado |
|---|---|
| `peak_viewers` | mayor audiencia **simultánea** observada |
| `average_viewers` | promedio de las muestras simultáneas; `null` sin muestras |
| `unique_viewers` | `null` = no disponible (no hay fuente) |
| `direct_messages_reported` / `direct_messages_capture` | lo informado / `false` mientras no exista captura de DM |
| `phones` | contactos únicos por fecha de **primera captura** |
| `phone_mentions` | todas las apariciones |
| `conversion` | contactos en `qualified` ÷ contactos capturados |
| `leads_per_hour` | contactos ÷ horas en vivo (mínimo 1 minuto) |
| contacto → tiempo | `contacted_at − first_captured_at`; porcentajes sobre contactados |

## Retención (política explícita)

`COMMENTS_RETENTION_DAYS` (30). Cada día se eliminan `live_comments` vencidos. **No** se tocan
lives, métricas, contactos, auditoría ni rankings.

- Las claves de idempotencia de un live se conservan mientras pueda recibir eventos; solo se
  borran las de lives terminados/cancelados, que ya rechazan eventos (`409`).
- Un evento con `timestamp` anterior a la ventana se **rechaza** (`409 EVENT_TOO_OLD`).
- El historial del monitor se convierte una vez (`published_at`); no se re-suma tras la limpieza.
- Comentarios vencidos: `410 COMMENTS_RETENTION_EXPIRED` (lista y exportación).

## Rutas públicas (proxy)

| Pública | Backend |
|---|---|
| `/api/health` | `/health` |
| `/api/v1/...` | `/v1/...` (app anterior) |
| `/api/auth`, `/api/inbox`, `/api/leads`, `/api/team`, `/api/marketing/...`, `/api/social-live/...` | igual |

Social Pulse (`apps/social-pulse`, puerto `SOCIAL_PORT`) usa el mismo origen: no necesita CORS.
En otro origen (Vite en desarrollo) añadirlo a `CORS_ORIGINS` y `CLERK_AUTHORIZED_PARTIES`.

## Medical 360

`reportes_streamlit/services/livepulse_service.py` consume `/api/marketing/tiktok/*` con Bearer.
`LIVEPULSE_API_URL` = origen de la API (se tolera un `/api` final) y
`LIVEPULSE_MEDICAL360_TOKEN` = `MEDICAL360_TOKEN` del servidor LivePulse. Las cifras ya llegan
calculadas (un número se cuenta una vez, en su primera captura); Medical 360 no las rederiva.

## Migración y conversión de datos (0006)

Conserva los datos: copia antes de eliminar. Convierte `captured_phones` en un contacto por
número (la aparición más antigua es la primera captura; gana el estado más avanzado y el primer
contacto más antiguo), incorpora los contactos del modelo analítico anterior, crea los lives de
las transmisiones, marca como publicados los eventos ya plegados y mueve el antiguo
«unique_viewers» (que era el pico simultáneo) a `peak_viewers`. Es idempotente
(`modules/social_live/backfill.py`).

## Correcciones de integración (0007)

- Los filtros `date_from` y `date_to` son independientes. Una fecha sin hora incluye el día
  completo en Lima; una fecha ISO conserva su hora. Un rango invertido devuelve `422`.
- `/api/inbox` filtra permisos, `scope`, `phone_only` y `exclude_discarded` antes de paginar.
  Acepta `limit` (hasta 200) y `offset`; devuelve `total` y `next_offset`. La interfaz solicita
  el filtro de teléfonos al servidor y permite cargar las páginas siguientes.
- La conversión 0006 combina el historial legado incluso cuando el teléfono ya existe en el
  registro: conserva la primera captura, el primer contacto documentado, el estado más avanzado
  y el asesor ya asignado. No inventa una fecha de atención cuando no hay evidencia.
- La migración 0007 crea `live_interested_users`, con una clave única por transmisión y usuario.
  La limpieza de comentarios no elimina ese registro: un mismo usuario interesado se cuenta una
  vez incluso al reconstruir eventos antiguos en varios lotes o reiniciar el worker.
- La generación SQL sin conexión valida la estructura, pero no sustituye ejecutar las
  migraciones sobre PostgreSQL. La conversión de datos 0006 requiere Alembic en modo conectado.

## Pasos de despliegue

1. Respaldar la base (`python infra/scripts/backup.py`).
2. Variables: `MEDICAL360_TOKEN`, `MEDICAL360_EXPORT_TOKEN`, `SOCIAL_LIVE_TOKEN` (si se usa
   captura externa), `ADMIN_USER_IDS`, `CLERK_ISSUER`, `CLERK_AUTHORIZED_PARTIES` (incluir el
   origen de Social Pulse), `VITE_CLERK_PUBLISHABLE_KEY`, `SOCIAL_PORT`, `CORS_ORIGINS` si aplica.
3. Reconstruir y desplegar `api`, `worker`, `monitor` y `social` (no basta reiniciar). La API
   aplica `alembic upgrade head` al iniciar.
4. `python -m alembic current` debe mostrar `0007 (head)`.
5. Esperar el primer ciclo del worker (convierte el historial) y revisar logs.
6. Comprobar: `/api/health`, `/api/auth/me` sin sesión → `401` (no `404`), y en Marketing que el
   conteo de teléfonos coincide con el registro.
7. En Medical 360: ajustar `LIVEPULSE_API_URL` y token, y redesplegar.

## Fuera de alcance / pendiente

- **Mensajes directos**: no hay integración de lectura; se muestran como «no disponible».
- **Espectadores únicos**: sin fuente.
- **Leadsales**: el CSV del modelo anterior sigue en `/v1/contacts/export/leadsales` (modelo
  legado); no está conectado al registro único ni se ha probado la importación.
- Ajustes de pantalla (notificaciones, canales): locales.
- Historial anterior a la ventana: se convierten métricas y teléfonos, no el texto de comentarios.
