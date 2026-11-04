# CRM omnicanal: Chats, CRM y transmisiones simultáneas

Pantallas nuevas sobre el espejo de WhatsApp (`docs/whatsapp-mirror-v1.md`) y el chat/automatización
(`docs/automatizacion-ia-masivos.md`). Todo lo que aparece funciona contra el backend; lo que no puede
funcionar todavía está marcado así en pantalla.

## Qué hay

**Chats (`/whatsapp`)** — bandeja de cuatro columnas:
- Lista con búsqueda de contactos **y del texto de los mensajes**, y las vistas *Todos*, *Asignados a mí*,
  *No leídos* y *Archivados* con su contador. Cada fila muestra el último mensaje, la etapa, si viene de un
  LIVE y quién lo atiende. Abrir un número nuevo desde la lista.
- Conversación estilo WhatsApp: separadores de día, ✓ enviado / ✓✓ entregado / ✓✓ azul leído, reloj en cola,
  aviso si el envío quedó sin confirmar. Etapa, resultado, marcar como no leído, archivar y buscar dentro del
  chat. Mensajes pregrabados (botón ⚡ o escribir `/atajo`), emojis y **programar el envío** (reloj).
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

- **Fotos, audios y documentos:** la V1 del espejo no los descarga ni los envía, así que no hay mensajes con
  imagen. La conversación muestra el tipo del adjunto.
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
`social`: los mensajes programados los envía **`wa-worker`**, así que debe estar en marcha. Sin variables nuevas.
Nuevo permiso `crm:manage` (supervisor y admin) para crear los mensajes pregrabados.
