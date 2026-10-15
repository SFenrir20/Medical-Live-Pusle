# Integración Medical Social Live ↔ Medical 360

```
TikTok Live → Medical Social Live → API → PostgreSQL → API → Medical 360
```

Ningún frontend habla con el otro. Social Live **escribe**, Medical 360 **lee**. Las rutas
nuevas conviven con las anteriores (`/v1/...`), que no cambian.

## Autenticación y permisos

Cabecera `Authorization: Bearer <token>`. Tokens por variable de entorno; si está vacío, esa
credencial queda deshabilitada.

| Variable | Permiso |
|---|---|
| `SOCIAL_LIVE_TOKEN` | `ingest`: crear lives, eventos y teléfonos, y actualizar el contacto |
| `MEDICAL360_TOKEN` | `read`: consultar estadísticas |
| `MEDICAL360_EXPORT_TOKEN` | `read` + `export`: además descargar comentarios |
| `COMMENTS_RETENTION_DAYS` | días de retención de comentarios (por defecto 30) |

401 sin token o inválido; 403 si el token no tiene el permiso. Usar secretos largos y
aleatorios, guardados solo en servidores. **Un token de servicio no debe ir dentro de un
frontend de navegador**: el frontend de Social Live debe autenticar personas (login) contra
el backend, o hablar con un servidor suyo que guarde el token.

## Personas y roles (Clerk)

Medical Social Pulse inicia sesión con Clerk y manda su JWT en `Authorization: Bearer`.
El backend lo verifica (JWKS) y busca el **rol guardado en el servidor**; no confía en el
navegador ni en metadatos de Clerk.

| Rol | Pantalla | Permisos |
|---|---|---|
| `agente_ventas` | solo su perfil | sin acceso a estadísticas de marketing |
| `gerente` | marketing | leer y exportar |
| `jefe_marketing` | pantalla del jefe de marketing | leer y exportar |
| `supervisor` | ambas | leer, exportar y estado del monitor |

`admin` (variable `ADMIN_USER_IDS`) es el dueño técnico: asigna roles. Quien entra por primera
vez queda como `agente_ventas`. La matriz está en `modules/identity/roles.py`.

- `GET /api/auth/me` → `{ id, role, screens, permissions, can_manage_roles }`
- `GET /api/auth/users` / `PUT /api/auth/users/{id}/role` → solo admin

Las rutas de consulta `/api/marketing/tiktok/*` aceptan un token de servicio (servidor de
Medical 360) o una persona con el permiso. Las rutas de ingestión `/api/social-live/*` solo
aceptan el token de servicio: ninguna persona puede escribir eventos.

## Ingestión (Medical Social Live) — `/api/social-live`

| Método y ruta | Uso |
|---|---|
| `POST /accounts` | crear o actualizar cuenta TikTok (`id`, `name`, `username`, `type`, `active`) |
| `POST /tiktokers` | crear o actualizar TikToker (`id`, `name`, `active`) |
| `POST /lives` | crear live (`live_id` opcional, `tiktoker_id`, `account_id`, `started_at`, `status`) |
| `POST /lives/{id}/events` | un evento o `{"events": [...]}` (hasta 500) |
| `POST /lives/{id}/comments` | atajo de un comentario |
| `POST /lives/{id}/phones` | registrar teléfono (detectado o manual) |
| `PATCH /phones/{phoneId}` | `status`, `advisor_id`, `contacted_at` |
| `PATCH /lives/{id}/finish` | cierra el live y consolida métricas |

Evento:

```json
{ "event_type": "comment", "username": "usuario123",
  "text": "quiero información 987654321", "timestamp": "2026-10-15T19:23:10",
  "event_id": "opcional-para-reintentos" }
```

`event_type`: `comment`, `like`, `view`, `viewer`, `interested`, `follow`, `donation`, `share`,
`direct_message`, `phone_detected`, `phone_manual`.

- `like`, `view`, `share`, `follow`, `donation`: `value` suma esa cantidad (por defecto 1).
- `viewer`: `value` es el total de espectadores únicos conocido; se conserva el **máximo**.
- `comment`: requiere `username` y `text`. El servidor detecta teléfonos (también los
  disfrazados como `985//857#968`) y el interés, y crea los teléfonos capturados.
- `phone_detected`/`phone_manual`: llevan `phone` (o `text`) y `username`.
- **`event_id` hace idempotentes los reintentos.** Sin él, reenviar un contador lo suma de nuevo.
- `timestamp` sin zona horaria se interpreta como hora de Lima. No se aceptan fechas futuras
  (más de 5 minutos). Un live terminado acepta eventos hasta 5 minutos después de su fin.
- Un mismo teléfono en un mismo live es un solo lead.

Estados del teléfono: `new`, `contacted`, `qualified`, `discarded`. Al pasar a
`contacted`/`qualified` se fija `contacted_at` (una sola vez);
`contact_time_seconds = contacted_at − captured_at`.

## Consulta (Medical 360) — `/api/marketing/tiktok`

Filtros comunes: `date_from`, `date_to` (fecha `YYYY-MM-DD`, o ISO; sin zona = Lima; `date_to`
incluye el día completo), `tiktoker_id`, `account_id`. Las horas se devuelven en UTC y en Lima.

| Ruta | Devuelve |
|---|---|
| `GET /overview` | lives, views, comments, likes, shares, followers, interested, donations, phones, `leads_per_hour` |
| `GET /lives` | lista paginada (`status`, `limit`, `offset`) |
| `GET /lives/{id}` | detalle: métricas, resumen de teléfonos, `comments_available` |
| `GET /lives/{id}/metrics` | métricas consolidadas |
| `GET /lives/{id}/comments` | comentarios paginados |
| `GET /lives/{id}/phones` | teléfonos con `contact_time_seconds` |
| `GET /lives/{id}/comments/export` | XLSX en memoria (requiere `export`) |
| `GET /ranking?sort_by=` | TikTokers por `phones`, `leads_per_hour`, `views`, `interested`, `conversion` |
| `GET /accounts/performance` | comparación entre cuentas |
| `GET /hourly-performance?granularity=` | `hour_of_day` (con mejor y peor hora), `day`, `week`, `month` |
| `GET /contact-performance` | promedio, mediana, mínimo, máximo, % por tramo y sin contactar |

### Exportación y retención

El XLSX se arma en memoria y no se guarda. Columnas: fecha, hora, usuario TikTok, comentario,
teléfono detectado, live, TikToker, cuenta. El texto se escribe como cadena literal, nunca como
fórmula.

Cada día el worker elimina `live_comments` (y las claves de reintento) con más de
`COMMENTS_RETENTION_DAYS`. **No** elimina lives, `live_metrics`, `captured_phones` ni rankings.
Si se pide el detalle de un live ya purgado: HTTP **410** con

```json
{ "detail": { "code": "COMMENTS_RETENTION_EXPIRED",
  "message": "Los comentarios detallados de este Live ya no están disponibles. Las métricas históricas permanecen disponibles." } }
```

## Definiciones que conviene validar

- **conversion** = teléfonos en estado `qualified` ÷ teléfonos capturados.
- **leads_per_hour** = teléfonos ÷ horas en vivo (mínimo 1 minuto de duración).
- **interested_viewers**: un usuario cuenta una vez por live al comentar con interés.
- **Porcentajes de contacto**: sobre los teléfonos ya contactados.
- **Peor hora**: solo entre horas en las que hubo algún live.
- `unique_viewers` del resumen suma el máximo de cada live; un mismo usuario en dos lives
  cuenta dos veces.
- Las métricas del overview/ranking se filtran por la fecha de inicio del live; las de hora y
  contacto, por la fecha de captura del teléfono.

## Pendiente

- El monitor de TikTok actual (`raw_events`/`event_facts`) aún escribe en su propio modelo.
  Falta un adaptador que lo publique en estas tablas (o que Social Live use esta API).
- Login de usuarios de Social Live (`/auth/login` de su maqueta) y CORS para su origen.
