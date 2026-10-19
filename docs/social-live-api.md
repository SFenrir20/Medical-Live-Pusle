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
| Personas (Clerk) | JWT de sesión; el rol viaja firmado en él (Public metadata) | ver tabla de roles |

Los tokens de servicio **nunca** van al navegador. Ninguna persona puede escribir eventos
(`ingest`). Un token vacío queda deshabilitado.

## Roles y permisos de atención

El rol se asigna **en Clerk** (Public metadata `{"livepulse": {"role": "..."}}`, ver `clerk.md`) y
llega firmado en la sesión. Sin rol: sin acceso.

| Rol (código en Clerk) | Pantalla | Estadísticas | Contactos |
|---|---|---|---|
| `agente_ventas` | atención de contactos | — | ve los libres y los suyos; tomar, liberar, cambiar estado de los suyos |
| `gerente`, `jefe_marketing` | marketing y reportes | leer y exportar | solo conteos (no ve teléfonos) |
| `supervisor` | vista agente y marketing | leer y exportar | ve todos; asigna a cualquiera; historial |
| `admin` (`ADMIN_USER_IDS`, emergencia) | ambas | todo | todo |

Permisos: `contacts:read`, `contacts:claim`, `contacts:update`, `contacts:read_all`,
`contacts:assign_any` (más `read`, `export`). Matriz en
`modules/identity/roles.py`. Se validan en el servidor.

Atención (`/api`): `GET /inbox`, `PATCH /leads/{id}` (`action: claim|release|assign`,
`status`, `expected_status`, `expect_unassigned`), `GET /leads/summary`, `GET /team`,
`GET /leads/{id}/history`, `GET /auth/me`, `PUT /auth/me/profile`. Los roles no se asignan por API.

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

## Transmisión y responsable (código en el título)

La TikToker escribe **su código en el título del LIVE** y el sistema lo lee para saber quién
está al aire y poder validar sus métricas.

| TikToker | Nombre usado | ID interno | Código en el título |
|---|---|---|---|
| Ashley | Ash | `TK-A01` | `A1` |
| Maria Luisa | Mari | `TK-M02` | `M2` |
| Lucía | Lu | `TK-L03` | `L3` |
| Briggite | Bri | `TK-B04` | `B4` |
| Fernanda | Fer | `TK-F05` | `F5` |
| Nahit | Nahit | `TK-N06` | `N6` |

Reglas (`modules/social_live/titles.py`):

- El código cuenta solo como **palabra completa** y solo si es de una TikToker conocida
  (`Cirugías A1`, `[m2]`, `L3-LIVE`; no `MA1`, `A12` ni `A1B`). No distingue mayúsculas.
- **Un** código identifica a la responsable. **Ninguno** o **varios distintos** no identifican
  a nadie: el LIVE queda **«Sin asignar»**, nunca se adivina. La API informa el motivo en
  `responsible_note` (`sin_titulo`, `titulo_sin_codigo`, `titulo_con_varios_codigos`).
- El monitor lee el título al conectar y lo revisa cada 5 minutos: si la TikToker lo edita en
  vivo y aparece otro código, se actualiza la responsable. Un título posterior **sin** código
  no borra a la responsable ya identificada.
- Una asignación manual (`PATCH /api/social-live/lives/{id}` con `tiktoker_id`) tiene prioridad
  y el título no la cambia; con `tiktoker_id: null` la decisión vuelve al título.
- Todo se atribuye por LIVE completo (una responsable por transmisión). La asistencia no interviene.

`GET /lives/{id}` y la lista devuelven `title`, `tiktoker` (nombre usado),
`responsible_source` (`title` | `manual`) y `responsible_note`. Los contactos usan la
responsable del LIVE donde se capturaron por primera vez («Responsable del Live»).

Agregar o cambiar una TikToker: `POST /api/social-live/tiktokers`
`{"id": "TK-X07", "name": "Xi", "full_name": "Ximena", "code": "X7"}` (el código es una letra y
uno o dos dígitos y debe ser único; `409` si ya existe).

## Por qué las cifras no coinciden con TikTok Studio

TikTok Studio muestra las analíticas **finales** de TikTok (completas, depuradas, calculadas en sus
servidores). LivePulse cuenta lo que llega por el **chat en vivo** (websocket), que es un flujo
parcial: agrupa mensajes, omite entradas en salas grandes y no trae algunas cifras. Por eso solo
coinciden las que llegan completas.

| Cifra | Cómo la obtenemos | Por qué difiere de Studio |
|---|---|---|
| Me gusta | suma de los mensajes de «me gusta»; además el **total acumulado** que TikTok informa en cada mensaje | Los mensajes se agrupan y algunos no llegan. Se muestra el mayor entre nuestra suma y el total de TikTok (`likes_summed`, `likes_reported_total`) |
| Visualizaciones | conteo de **entradas** (`join`) que llegan por el chat | TikTok no emite una entrada por cada espectador en salas grandes: queda por debajo. Se muestra como «Ingresos observados», no como visualizaciones |
| Visitantes acumulados | `total_user` de TikTok (visitantes hasta el momento) | Es el valor más cercano a «visualizaciones/espectadores únicos» de Studio; se muestra aparte para **calibrar** contra Studio |
| Espectadores únicos | no hay fuente exacta | «No disponible»; Studio es la referencia |
| Pico / promedio simultáneo | muestras de espectadores actuales | Las muestras son irregulares y TikTok calcula por tiempo. El promedio ahora se **pondera por tiempo** (una muestra vale lo que duró, máx. 2 min); el pico es el mayor valor observado y puede diferir unos puntos |
| Seguidores nuevos | eventos de seguir | Studio descuenta quien deja de seguir: ±1–2 |
| Compartidos | eventos de compartir | Coinciden (llegan completos) |
| Mensajes directos | — | No se capturan |
| «Espectadores interesados» | reglas sobre comentarios con intención de compra | **No es** la métrica de TikTok del mismo nombre (clics en formularios/descripción del servicio); son conceptos distintos |

Regla práctica: para informes oficiales usar TikTok Studio; LivePulse es el seguimiento en vivo
y la fuente de comentarios, teléfonos y responsables. Las diferencias de unos pocos puntos en
pico/promedio son normales; las de visualizaciones y me gusta eran estructurales.

## Alertas, recordatorios y descarga de contactos

La **campana** de Social Pulse muestra a cada rol solo lo suyo (lo decide el servidor):

| Rol | Qué recibe en la campana |
|---|---|
| `agente_ventas` | Recordatorios de **sus** chats pendientes: «tienes N chats que llevan más de 10 min (M más de 20)» y contactos sin tomar. **Nunca** ve alertas |
| `supervisor`, `jefe_marketing`, `gerente` | Alertas de números que reaparecen y comentarios «no me contactan» por revisar |

**Cuándo se genera una alerta** (`modules/social_live/alerts.py`, al ingresar cada comentario con
número, según el estado del contacto en ese momento):

- Contacto aún **nuevo** que vuelve a escribir su número: **sin alerta** (solo insiste).
- Contacto ya **marcado como contactado**:
  - mismo LIVE, y pasaron **`ALERT_SAME_LIVE_MINUTES` (10)** desde que se marcó → `same_live`;
    antes de ese plazo, o si escribió antes de que lo marcaran, no hay alerta;
  - otro LIVE de la misma cuenta, después de marcado → `other_live`;
  - LIVE de otra cuenta, después de marcado → `other_account`.
- Una alerta por (contacto, LIVE); si sigue escribiendo suma `repeats`. Una alerta revisada o
  descartada no se reabre.

Una alerta es **un motivo para revisar, no una prueba**. Se resuelve con `Marcar revisada` o
`Falsa alarma` y una nota; queda quién y cuándo.

**Comentarios «no me contactan»**: reglas de texto (`no me contactan`, `nadie me llamó`, `les
escribo y no me contestan`, `sigo esperando`…) marcan el comentario. La lista muestra, junto al
usuario, los números que dejó con ese mismo nombre de TikTok, su estado y el asesor. Los
comentarios se conservan 30 días.

Rutas (`/api`): `GET /notifications`, `GET /alerts?status=`, `PATCH /alerts/{id}`,
`GET /complaints?status=`, `PATCH /complaints/{id}`, y
`GET /marketing/tiktok/contacts/export` (Excel con una fila por contacto: estado, asesor,
primera captura, LIVE, responsable, primer contacto, minutos hasta el contacto, apariciones y
alertas abiertas). Permisos: `alerts:read`, `alerts:review`, `contacts:export` (supervisor,
jefe de marketing, gerente y admin). Cada descarga queda en `export_audit`. Gerente y jefe de
marketing ven teléfonos completos **solo** en estas alertas y en esa descarga.

Variables: `ALERT_SAME_LIVE_MINUTES`, `REMINDER_FIRST_MINUTES`, `REMINDER_SECOND_MINUTES`.

## Audiencia destacada (ranking de fans)

Pestaña «Audiencia» de la vista de marketing: quiénes comentan, regalan o se quedan más.
Permiso `audience:read` (supervisor, jefe de marketing, gerente y admin; **nunca** agentes ni los
tokens de servicio). `GET /api/audience/top?live_id=&days=&sort=&limit=`: con `live_id` es ese
live; sin él, el acumulado de los últimos `days` (máx. 90) de todos los lives, donde `lives > 1`
son fans recurrentes. `sort`: `diamonds` (por defecto), `comments`, `likes`, `shares`,
`presence`, `lives`; los empates se resuelven por diamantes, comentarios y likes.

| Dato | Fuente | Fiabilidad |
|---|---|---|
| comentarios, likes, compartidos, regalos y diamantes | eventos del monitor, por persona | exacto (los tramos intermedios de una racha de regalos no cuentan) |
| siguió | evento de follow | exacto |
| tiempo visible | de la primera a la última vez que la persona aparece en un evento | **estimación**: TikTok no avisa quién sale y quien mira en silencio no genera eventos |
| dejó contacto | su usuario figura en `captured_phones` | solo un sí/no: **el teléfono no se devuelve** |

Se guarda en `audience_members` (una fila por live y usuario; el usuario se normaliza a
minúsculas y sin `@`). Se alimenta en la misma ingestión que las métricas, así que cada evento
cuenta una vez, y se borra con los comentarios (`COMMENTS_RETENTION_DAYS`). La migración `0011`
reconstruye el historial desde `raw_events` para los lives ya ocurridos dentro de esa ventana.

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

`COMMENTS_RETENTION_DAYS` (30). Cada día se eliminan `live_comments` y `audience_members`
vencidos. **No** se tocan lives, métricas, contactos ni auditoría.

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

Social Pulse (`apps/social-pulse`, puerto `WEB_PORT`) usa el mismo origen: no necesita CORS.
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
   origen de Social Pulse), `VITE_CLERK_PUBLISHABLE_KEY`, `WEB_PORT`, `CORS_ORIGINS` si aplica.
3. Reconstruir y desplegar `api`, `worker`, `monitor` y `social` (no basta reiniciar). La API
   aplica `alembic upgrade head` al iniciar.
4. `python -m alembic current` debe mostrar `0011 (head)` (carga a las 6 TikTokers, crea las tablas de alertas, las columnas de totales de audiencia y `audience_members`, que se rellena con el historial de `raw_events`).
5. Esperar el primer ciclo del worker (convierte el historial) y revisar logs. Los LIVE que ya
   estaban al aire reciben su título en ≤5 min tras reiniciar `monitor`; los LIVE anteriores
   (sin título guardado) siguen «Sin asignar» hasta asignarlos con `PATCH` si hace falta.
6. Comprobar: `/api/health`, `/api/auth/me` sin sesión → `401` (no `404`), y en Marketing que el
   conteo de teléfonos coincide con el registro.
7. En Medical 360: ajustar `LIVEPULSE_API_URL` y token, y redesplegar.

## Fuera de alcance / pendiente

- **Mensajes directos**: no hay integración de lectura; se muestran como «no disponible».
- **Espectadores únicos**: sin fuente.
- **Leadsales**: el CSV del modelo anterior sigue en `/v1/contacts/export/leadsales` (modelo
  legado); no está conectado al registro único ni se ha probado la importación.
- Ajustes de pantalla (notificaciones, canales): locales.
- **Lectura del título en TikTok**: depende de que TikTok entregue la información de la sala
  (`room/info`); en directos con restricción de edad no está disponible y el LIVE queda sin
  asignar. No se ha probado contra un LIVE real.
- Historial anterior a la ventana: se convierten métricas y teléfonos, no el texto de comentarios.
