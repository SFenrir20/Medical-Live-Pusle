# Espejo de WhatsApp Business en Social Pulse — diseño e implementación

Estado: **diseño de referencia**. La primera implementación y sus límites reales están en
[`whatsapp-mirror-v1.md`](whatsapp-mirror-v1.md). Las funciones descritas abajo que no figuren en
esa guía siguen siendo propuestas. La vinculación y prueba con teléfono real están pendientes.
Prototipo visual (datos inventados):
[`docs/design/whatsapp-mirror.html`](design/whatsapp-mirror.html), con tres pestañas: vincular,
conversaciones y embudo.

## Qué es

Un **espejo** del WhatsApp Business de la clínica, como WhatsApp Web: el teléfono se vincula
como «dispositivo vinculado» escaneando un QR. Las conversaciones aparecen en Social Pulse y el
equipo responde desde ahí, **con texto libre, sin plantillas ni ventana de 24 horas**. No se usa
la API oficial de Meta. Lo que se escribe desde el teléfono también se ve aquí, y viceversa.

Lo que lo distingue de un simple visor de chats: cada conversación se **enlaza con el contacto
que ya existe** (el de TikTok LIVE): origen, apariciones, etapa y asesor. Y cuando el asesor
escribe el primer mensaje, el contacto pasa solo a «contactado», con su hora y su nombre reales.

## Riesgos de este método (conviene decidirlo con los ojos abiertos)

- **No es oficial.** WhatsApp no respalda clientes no oficiales para uso comercial automatizado.
  El riesgo real es que **restrinjan o bloqueen el número**. Las señales que más lo provocan:
  escribir a muchas personas que no te han escrito, envíos masivos o idénticos, y cuentas nuevas.
- **Puede romperse.** Estas conexiones dependen de librerías de la comunidad. Cuando WhatsApp
  cambia su protocolo, el espejo puede dejar de funcionar hasta que se actualice la librería.
- **La sesión es una llave.** Quien tenga los archivos de sesión controla ese WhatsApp. Se
  protege como una contraseña (ver Seguridad).
- **Datos de salud** de pacientes (Ley 29733): política de privacidad, retención y registro de
  accesos. Revisar con quien lleve lo legal.

Por eso el diseño trae protecciones obligatorias, no opcionales (abajo). Si el número es
crítico para la clínica, usa uno que puedas permitirte perder o un número secundario.

## Arquitectura

```
Teléfono (WhatsApp Business)  ⇄  wa-gateway (Node + Baileys)  ⇄  API (FastAPI)  ⇄  Navegador
        QR para vincular          sesión en volumen cifrado        PostgreSQL       Social Pulse
```

- **`wa-gateway`**: contenedor aparte, solo en la red interna (sin puerto público). Mantiene la
  sesión con WhatsApp, entrega mensajes entrantes a la API (HTTP + secreto compartido) y recibe
  órdenes de envío. Una sola instancia por número: dos instancias con la misma sesión se pisan.
- **API**: guarda conversaciones y mensajes, aplica permisos, enlaza con `phone_registry`, y
  emite el QR a la pantalla por SSE o sondeo, solo para el rol que gestiona la conexión.
- **Frontend**: nunca habla con el gateway.
- El gateway se escribe detrás de una **interfaz mínima** (estado/QR, recibir, enviar, cerrar
  sesión) para poder cambiar de librería sin tocar el resto.

Opciones para el gateway (verificar licencia y limitaciones vigentes de cada una):

| | Qué es | A favor | En contra |
|---|---|---|---|
| **Servicio propio con Baileys** (recomendado) | ~pocas centenas de líneas, solo lo que necesitamos | Control total, sin funciones de sobra | Hay que mantenerlo |
| Evolution API | Servidor listo con REST y webhooks | Más rápido de arrancar | Mucha superficie que no usamos |
| WAHA | Otro servidor listo | Igual | Parte de las funciones suele ser de pago |

## Cómo se vincula (inicio de sesión)

1. Pantalla «Vincular WhatsApp» (solo roles con `wa:manage`).
2. El gateway genera un QR (se renueva cada ~60 s) que la API muestra en pantalla.
3. En el teléfono: WhatsApp Business → Ajustes → Dispositivos vinculados → Vincular un
   dispositivo → escanear.
4. El gateway recibe la sesión y la guarda en un volumen **cifrado**; empieza a llegar el
   historial reciente (cuánto envía WhatsApp lo decide él) y los mensajes en vivo.
5. La pantalla muestra estado, última conexión del teléfono, chats nuevos de hoy, y permite
   desvincular. Si la sesión se cierra, se pide volver a escanear y se avisa al equipo.

El teléfono debe seguir conectado de vez en cuando; si pasa mucho tiempo sin conexión, WhatsApp
cierra los dispositivos vinculados.

## Cómo se ven las conversaciones

Tres columnas (ver el prototipo):

- **Izquierda:** búsqueda y filtros (Todos, Míos, Sin asignar, No leídos, por origen) con avatar,
  último mensaje, hora, no leídos, origen y etapa.
- **Centro:** burbujas estilo WhatsApp (✓✓, adjuntos, fotos, notas de voz, documentos), eventos
  de sistema («capturado desde el LIVE TT-24», «cambió la etapa»), marca «escrito desde el
  teléfono» para el espejo, respuestas rápidas con `/` y caja de mensaje.
- **Derecha:** ficha del paciente: origen del LIVE, etapa, etiquetas, nota interna (no sale al
  paciente), actividad y «Agendar consulta».
- **Embudo** (kanban por etapa): Nuevo → Interesada → Cotización enviada → Cita agendada →
  Atendida.

Como todos escriben desde **un solo número**, la app registra internamente qué asesor envió cada
mensaje (el paciente solo ve el número de la clínica). Opcional: firmar con el nombre del asesor.

## Protecciones contra bloqueo (parte del producto)

- Solo mensajes escritos por una persona desde la app; **sin envíos masivos, difusión ni bots**.
- **Tope diario de chats nuevos** (configurable, p. ej. 20) y contador visible. Responder a quien
  ya escribió no cuenta.
- Cola de envío con pausa mínima entre mensajes e indicador «escribiendo…» natural.
- Contactar a los leads del LIVE **en tandas**, no todos de golpe.
- Respetar bajas: quien pide no recibir mensajes se marca y no se vuelve a escribir.
- Alertas: sesión caída, teléfono sin conexión por horas, fallos de envío repetidos.

## Modelo de datos (propuesto)

Alembic/PostgreSQL, mismo estilo del resto:

- `wa_sessions`: número, estado, última conexión, fecha de vinculación y quién vinculó.
  (Las credenciales de la sesión **no** van en texto plano.)
- `wa_conversations`: `registry_id` → `phone_registry` (contacto único por E.164), asesor, etapa,
  etiquetas, `unread`, último mensaje.
- `wa_messages`: conversación, id del mensaje de WhatsApp **único** (idempotencia), dirección,
  `from_phone` (escrito desde el teléfono), tipo, texto, media, estado (enviado/entregado/leído/
  fallido), asesor que lo envió, fecha.
- `wa_notes` y `wa_events` (etapa, asignación, lectura) para historial y auditoría.

Si escribe alguien que no está en `phone_registry`, se crea el contacto con origen `whatsapp`
(hay que ampliar las fuentes permitidas; propuesta: **no** mezclarlos con la métrica de captura
de LIVES).

## Backend y permisos

- `POST /api/whatsapp/gateway/events` (solo el gateway, secreto + red interna): mensajes,
  estados y cambios de sesión. Idempotente por id de mensaje.
- `GET /api/whatsapp/conversations`, `GET …/{id}/messages`, `POST …/{id}/messages` (texto o
  adjunto, con cola y topes), `PATCH …/{id}` (etapa, etiquetas, asesor, nota), `POST …/{id}/read`.
- `GET /api/whatsapp/session` y `…/session/qr` (SSE), `DELETE …/session` (desvincular).
- Permisos nuevos en `identity/roles.py`: `wa:read` (propios y sin asignar), `wa:send`,
  `wa:read_all`, `wa:manage`. Agentes: lo suyo; supervisor: todo y gestiona la conexión; jefe de
  marketing y gerente: **por decidir** (propuesta: solo embudo y métricas, sin leer mensajes).
- Integración: el primer mensaje saliente a un contacto del registro lo marca «contactado»
  (asesor y hora reales; auditoría `whatsapp`).
- Adjuntos: el gateway los descarga y se guardan en almacenamiento propio.

## Seguridad

- El gateway sin puerto público; comunicación con la API por red interna y secreto.
- Volumen de sesión cifrado, con respaldo propio y acceso restringido; la sesión equivale a la
  cuenta de WhatsApp completa.
- Lectura de conversaciones auditada; sin exportación masiva de chats para agentes.
- Retención configurable (propuesta a decidir; más larga que los 30 días de los comentarios).

## Fases (estimado grueso)

1. **Gateway + vinculación por QR + recibir y ver conversaciones (solo lectura):** 1–2 semanas.
2. **Enviar texto y adjuntos, estados ✓✓, cola y topes anti-bloqueo:** ~1 semana.
3. **Integración con el CRM** (contacto del LIVE, etapa, etiquetas, asignación, «contactado»
   automático, notas): ~1 semana.
4. **Embudo, alertas de sesión y reportes** (tiempo de primera respuesta): ~1 semana.

Estas cifras no incluyen el tiempo de pruebas con un número real; conviene empezar con un
número secundario y pasar al principal cuando esté estable.

## Decisiones abiertas

1. ¿Número secundario para las pruebas? (recomendado) ¿Y cuál será el definitivo?
2. ¿Gateway propio con Baileys (recomendado) o uno ya hecho?
3. ¿Qué ve el jefe de marketing y el gerente: solo embudo y métricas, o también mensajes?
4. ¿Tope diario de chats nuevos? (propuesta inicial: 20) ¿Se firma con el nombre del asesor?
5. Retención de las conversaciones.
