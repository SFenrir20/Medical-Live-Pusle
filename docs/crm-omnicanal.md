# CRM omnicanal: Chats, CRM y transmisiones simultáneas

Pantallas nuevas sobre el espejo de WhatsApp (`docs/whatsapp-mirror-v1.md`) y el chat/automatización
(`docs/automatizacion-ia-masivos.md`). Todo lo que aparece funciona contra el backend; lo que no puede
funcionar todavía está marcado así en pantalla.

## Qué hay

**Chats (`/whatsapp`)** — bandeja de cuatro columnas:
- Lista con búsqueda de contactos **y del texto de los mensajes**, y las vistas siempre visibles *Todos*,
  *Míos*, *No leídos*, *Sin responder*, *Sin asignar* y *Archivados* con su contador. Cada fila muestra el
  último mensaje (con icono: 🎤 voz, 📷 foto, 🎬 video, 📎 documento), la etapa, quién lo atiende y, si la
  persona escribió y nadie contestó, cuánto lleva esperando (en rojo desde 1 h). Abrir un número nuevo.
- Sin conversación abierta, el centro muestra el resumen del trabajo (sin responder, no leídos, sin asignar,
  míos) y quién espera respuesta. El estado de WhatsApp es una insignia con detalle desplegable.
- Conversación estilo WhatsApp: separadores de día, ✓ enviado / ✓✓ entregado / ✓✓ azul leído, reloj en cola,
  aviso si el envío quedó sin confirmar. Etapa, resultado, marcar como no leído, archivar y buscar dentro del
  chat. Audios y notas de voz con reproductor (velocidad 1x/1,5x/2x), videos, documentos descargables,
  stickers e imágenes con ampliación; línea «Mensajes no leídos». Envío de texto e imágenes (hasta 8 MB). Mensajes pregrabados (botón ⚡ o escribir `/atajo`), emojis y **programar el envío** (reloj).
- Ficha del contacto: etapa CRM, responsable (el supervisor reasigna; la asesora «toma» los libres),
  etiquetas, consentimiento de WhatsApp, notas internas, mensajes programados y la evidencia por LIVE
  (primer envío posterior a cada captura).
- Panel de **TikTok LIVE**: los teléfonos que dejó tu audiencia, a un clic de su conversación.
- Estado de la conexión, QR (solo supervisor/admin) y las alertas de sincronización del espejo.

**CRM (`/crm`)** — tarjetas (contactos, conversaciones, listos para WhatsApp, campañas, automatizaciones) y
pestañas *Contactos* (base de pacientes con etapa editable, consentimiento y «Abrir chat»), *Campañas*
(las difusiones) y *Automatizaciones* (MedicalBot = flujos y agente de IA; Mensajes pregrabados; MedicalClic).

**Transmisiones simultáneas** — tarjeta en Resumen (marketing) y en Pulso (supervisor): cada cuenta en vivo
con su tiempo, la audiencia en línea (última muestra) y los teléfonos captados.

## Reglas que se respetan (no se cambiaron)

- Una persona ve sus conversaciones y las libres; **debe tomar el contacto antes de editarlo o escribirle**.
  Jefatura y gerencia solo revisan. Supervisor/admin ven todo y reasignan.
- **Una sola etapa por contacto:** si el número viene de un LIVE, la etapa es el estado del contacto (nuevo,
  contactado, *cita agendada* = calificado, descartado), con su auditoría; solo un número que escribió por
  WhatsApp sin pasar por un LIVE guarda la etapa en la conversación.
- Los mensajes programados salen **por la misma cola de envío** que uno escrito a mano (mismos estados y
  confirmaciones) y solo si la asesora sigue siendo la dueña del contacto; si no, se cancelan.
- Consentimiento: «autorizado» no se puede marcar si la persona pidió no recibir mensajes; «revocar» la agrega
  a la lista de bajas. Las campañas, por defecto, solo llegan a quien autorizó.

## Lo que NO funciona todavía (y por qué)

- **Enviar audios, videos y documentos desde el CRM:** no existe todavía; solo se reciben y se ven. Los
  archivos de una sola visualización permanecen en el teléfono.
- **Mensajes antiguos con «[Audio: consultar en el teléfono]»:** el worker pide al conector, una vez por
  minuto y por tandas, que vuelva a adjuntar el archivo (hasta 45 días atrás). Solo funciona si el conector
  aún conserva el mensaje original y WhatsApp todavía entrega el archivo; si no, queda marcado como no
  disponible y no se vuelve a pedir.
- **Bots y campañas sobre el WhatsApp real:** siguen desconectados (se prueban en el simulador). El botón
  «Activar automatización» de la ficha está deshabilitado a propósito.
- **MedicalClic (botones y menús dentro del mensaje):** requiere la API oficial; el espejo no puede enviarlos.
- **Instagram y mensajes directos de TikTok** en la misma bandeja: no hay integración. Solo existe WhatsApp.
- La hora de «en línea» es la última muestra de audiencia, no un conteo exacto.

## API

`/api/crm`: `GET /conversations` (scope, q, offset; con contadores), `GET|PATCH /conversations/{id}`
(etapa, resultado, etiquetas, archivado), `POST /conversations/{id}/unread|assign|notes|scheduled`,
`PUT /conversations/{id}/consent`, `DELETE /notes/{id}`, `DELETE /scheduled/{id}`,
`GET|POST|PUT|DELETE /quick-replies` (crear/editar: `crm:manage`), `GET /contacts`, `GET /summary`.
El envío, el estado y el QR siguen en `/api/whatsapp`. `current_viewers` se agregó a las métricas de cada LIVE.

## Despliegue

Migración `0016` (se aplica sola al arrancar la API; depende de `0015`). Reconstruir `api`, `wa-worker` y
`web`: los mensajes programados los envía **`wa-worker`**, así que debe estar en marcha. Sin variables nuevas.
Nuevo permiso `crm:manage` (supervisor y admin) para crear los mensajes pregrabados.


## Imágenes y sesiones (migración 0017)

Reconstruir y desplegar `api`, `worker`, `wa-worker`, `wa-gateway` y el frontend `web` juntos.
La API aplica la migración 0017 al arrancar. No hay nuevas variables de entorno.
Conservar el volumen del gateway y `WA_SESSION_KEY`: allí se guardan cifradas las imágenes.
El proxy del frontend admite peticiones de 10 MB; cualquier proxy adicional debe permitir al menos
ese tamaño para subir imágenes de hasta 8 MB. Cada imagen exige los permisos de su conversación;
no se publican enlaces abiertos. Una imagen temporalmente no disponible se puede reintentar.
No hay importación completa del historial antiguo de WhatsApp ni garantía de recuperar archivos vencidos.
Los mensajes programados siguen siendo de texto.

La sesión de trabajo de la asesora es independiente del inicio de sesión de Clerk:
- Verde: pestaña visible y actividad de ratón/teclado/toque/desplazamiento en los últimos 5 minutos.
- Amarillo: pestaña oculta, 5 minutos sin actividad o pausa manual. No recibe contactos nuevos.
  La actividad antes del límite devuelve el verde, salvo que haya una pausa manual.
- Tras 15 minutos continuos en amarillo pasa a rojo y se cierra la sesión de trabajo.
  También pasa a rojo al desconectarse manualmente o perder los latidos del servidor.
- Rojo: mover el mouse, recargar o los latidos de otra pestaña no reactivan la sesión;
  debe pulsar **Conectarme**. Se abre una sesión nueva. Se mantiene la redistribución existente
  de contactos pendientes y se conservan los contactos ya trabajados.
- Se muestra el tiempo de la sesión actual; supervisión conserva los acumulados conectado/activo.
  Se mide actividad de la aplicación, no si la persona mira físicamente la pantalla.
Los cambios se reflejan con la cadencia de latidos (20 s). La pestaña activa prevalece sobre otras
pestañas ocultas del mismo navegador. El servidor conserva el bloqueo de reconexión.


## Navegación y diseño de la bandeja

- Navegación común: Pulso, Bandeja (`/bandeja`), Contactos (`/contactos`) y Ajustes (`/ajustes`).
- TOOLS (`/tools`) sustituye a la página CRM. Solo los perfiles con vista marketing y
  permiso `automation:read` pueden abrirlo; el agente tampoco puede entrar mediante el enlace directo.
  Los enlaces antiguos `/whatsapp` y `/crm` siguen funcionando como alias.
- La bandeja muestra conversaciones, mensajes, ficha de contacto y TikTok LIVE en cuatro columnas
  desde 1100 px. En tamaños menores la ficha y los LIVE se abren con botones, sin perder funciones.
- Pulso del agente consulta `/api/crm/active-lives`: solo transmisiones activas, responsable,
  última muestra de audiencia y cantidad de teléfonos. No otorga acceso a reportes históricos.
  Marketing conserva sus permisos de reportes. Ambas vistas usan la misma tarjeta de LIVE.
- Los canales e indicadores reflejan datos conectados: no se muestran Instagram o DM de TikTok ficticios.

## Audios, videos, documentos y stickers (migración 0018)

Reconstruir y desplegar **juntos** `wa-gateway`, `wa-worker`, `api` y `web`: el conector y el worker deben
actualizarse a la vez (el evento trae ahora el tipo de archivo, su duración, nombre y tamaño). La migración
0018 se aplica sola al arrancar la API y marca las imágenes existentes como tales. Sin variables nuevas.

- Notas de voz, audios y stickers se descargan al llegar; videos y documentos, al abrirlos. Todo se guarda
  cifrado en el volumen del conector (límites: audio 16 MB, video y documento 24 MB, sticker 1 MB).
- `GET /api/whatsapp/messages/{id}/media` exige los mismos permisos que la conversación, comprueba que el
  archivo pertenece a ese contacto y a un tipo permitido, admite `Range` (para reproducir y saltar en
  audio y video) y entrega los documentos solo como descarga con el nombre saneado.
- Algunos navegadores (Safari) no reproducen notas de voz OGG/Opus: el reproductor ofrece descargarlas.
- La bandeja descarga como máximo 3 archivos a la vez y reutiliza los ya vistos; la lista y las
  conversaciones solo se vuelven a dibujar si algo cambió, y el estado de WhatsApp se consulta aparte.

## Embudos (migración 0020)

Pantalla **Embudos** (`/embudos`, en el menú principal): un tablero Kanban con una columna por etapa y una
tarjeta por conversación (avatar, último mensaje con su icono, no leídos, responsable, tiempo sin responder
y valor). Cada columna muestra su cantidad de chats y su valor total; carga de a 30 con «Ver más».

- **Varios embudos.** El selector del encabezado cambia de embudo; supervisor y admin (`crm:manage`) crean
  uno con «Agregar embudo» (plantillas TikTok LIVE a cita, WhatsApp a paciente, Reactivación o en blanco).
- **«Contactos» es el embudo de siempre**: sus columnas son el estado del contacto (Nuevo, Contactado, Cita
  agendada, Descartado). Mover una tarjeta ahí cambia ese estado, igual que hacerlo desde la bandeja: sigue
  habiendo una sola etapa por contacto, con su auditoría. No se edita.
- **Los demás embudos son independientes**: un chat entra solo si alguien lo agrega («Agregar chats») y
  puede estar en varios a la vez, cada uno con su etapa.
- **Mover** = arrastrar la tarjeta, o su menú ⋮ → «Mover a» (sirve con teclado y pantalla táctil). **Valor**
  = clic en «+ Valor» (soles).
- **Quién puede qué:** ve las tarjetas de las conversaciones que ya puede ver; mover, agregar o poner valor
  exige que el chat sea suyo (o ser supervisor); jefatura y gerencia solo miran. Crear, renombrar, archivar
  y editar etapas es `crm:manage`.
- **Configuración** (constructor): nombre, etapas (orden, color, descripción), y por etapa cuántos entraron
  y qué porcentaje de la anterior. Una etapa con chats no se puede eliminar hasta moverlos. Las cifras salen
  del registro de movimientos (`crm_pipeline_events`), que **empieza al activar esta función**: no incluye lo
  anterior, y los cambios de estado hechos desde el flujo de contactos fuera del CRM no se registran.
- **Todavía no:** automatizaciones al entrar a una etapa (asignar, enviar mensaje, activar flujo) y filtros
  avanzados; el arrastre no funciona con el dedo (usa «Mover a»).

API: `GET|POST /api/crm/pipelines`, `GET /templates`, `PATCH /{id}`, `PUT /{id}/stages`, `GET /{id}/board`,
`GET /{id}/stages/{stage}/cards`, `PUT|DELETE /{id}/cards/{conversation}`, `GET /{id}/metrics`,
`GET /by-conversation/{id}`. Despliegue: reconstruir `api` y `web`; la migración 0020 se aplica sola.
