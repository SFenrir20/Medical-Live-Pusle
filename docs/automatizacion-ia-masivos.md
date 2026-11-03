# Automatizaciones, agente de IA y difusiones — diseño

Estado: **implementado y probado contra el simulador** (backend con pruebas, y pantallas en
Marketing → «Automatización»). **Todavía no hay un WhatsApp real conectado**: el canal del espejo y el
de la API oficial existen como canales configurables, pero enviar por ellos falla con un aviso claro
hasta que se registre su adaptador (`chat/channels.py::register_adapter`). Para el espejo ver
`docs/whatsapp-espejo.md`.

Lo construido: núcleo de chat (canales, conversaciones, mensajes, bajas), políticas por canal,
motor de flujos con lienzo visual, agente de IA con conocimiento y límites, difusiones, auditoría de
las acciones del administrador, y el simulador. El módulo vive en `backend/src/livepulse/modules/chat/`
y `.../automation/`, y en `apps/social-pulse/src/features/automation/`; solo toca el resto del
sistema por contactos y reparto (`social_live`), para poder llevarlo a otro proyecto.

**Quién puede qué (ya aplicado):** solo el rol `admin` (usuarios en `ADMIN_USER_IDS`) crea, activa y
envía; supervisor, jefe de marketing y gerente ven (sin teléfonos ni conversaciones); los agentes no
entran. Variables nuevas: `APP_ENCRYPTION_KEY` (cifra la clave del proveedor de IA) y `BOT_PAUSE_HOURS`.
Migración `0014`. Los flujos, el agente de IA y las difusiones nacen apagados; en el espejo, bots y
difusiones están apagados y limitados a números de prueba hasta que un admin los encienda aceptando
el riesgo.

El texto siguiente es el diseño original.

## Principio de diseño: el motor nunca habla con WhatsApp

Todo lo que se construya (flujos, bot, difusiones) envía mensajes **solo a través de un
adaptador de canal**. Hoy el canal será el espejo por QR; cuando se aprueben las APIs, el canal
oficial. Cambiar de uno a otro es configurar otro adaptador, **no rehacer flujos ni difusiones**.

```
Canales (adaptadores)            Modelo único                Motor (solo jefe de marketing / admin)
 · espejo WhatsApp (QR)   ─┐                                  ├─ Flujos (diagrama tipo n8n)
 · WhatsApp API oficial   ─┼─►  conversaciones y mensajes ─►  ├─ Agente de IA (reglas + conocimiento)
 · simulador (pruebas)    ─┤     (autor: contacto/agente/     └─ Difusiones (segmentos y envío)
 · TikTok / Instagram     ─┘      bot/sistema)
```

Cada canal declara sus **capacidades**, y el motor las respeta:

| Capacidad | Espejo (QR) | API oficial | Simulador |
|---|---|---|---|
| Texto libre en cualquier momento | sí | solo dentro de 24 h | sí |
| Plantillas aprobadas | no aplica | obligatorias fuera de 24 h | sí |
| Envío masivo seguro | **no** | sí, con buena reputación | sí |
| Bot seguro | con topes estrictos | sí | sí |

## El riesgo que condiciona todo (decisión que te toca)

Sobre el espejo por QR, **los bots y los envíos masivos son justo lo que más lleva a que
WhatsApp restrinja o bloquee el número**. Por eso el motor trae políticas por canal, con valores
iniciales seguros que el administrador puede cambiar sabiendo el riesgo:

- **Espejo:** difusiones **apagadas** por defecto; automatizaciones permitidas solo como
  **respuesta a mensajes que la persona escribió**, con tope por hora y pausas entre mensajes;
  nada de iniciar chats en masa; interruptor visible «modo prueba» (el bot responde solo a
  números de la lista de prueba).
- **API oficial:** todo habilitado, con plantillas fuera de la ventana de 24 h, consentimiento
  (opt-in) y baja automática.
- Siempre: lista de **bajas** (si escribe «BAJA» o «no más» no se le vuelve a escribir),
  límites diarios, y un registro de cada mensaje automático.

## Quién puede qué

- `automation:manage`: **jefe de marketing y admin** crean y activan flujos, el agente de IA y
  las difusiones.
- `automation:read`: supervisor y gerente ven flujos, registros y resultados, sin editar.
- Agentes de ventas: no entran al motor. Ven que una conversación la lleva el bot y pueden
  **tomarla** (el bot se detiene). Las conversaciones del bot siguen apareciendo en su bandeja
  cuando se les pasan.
- Enviar una difusión pide confirmación con el número exacto de destinatarios y una prueba
  previa a un número propio.

## Flujos (diagrama)

Lienzo visual (se usaría `@xyflow/react`, que ya usa wacrm) con panel de validación y prueba
antes de activar. Nodos:

- **Disparadores:** mensaje entrante (cualquiera o con palabra clave); contacto nuevo capturado
  de un LIVE; cambió la etapa; sin respuesta tras X minutos; horario programado.
- **Condiciones:** palabra clave, etiqueta, etapa, origen (LIVE/cuenta), horario laboral,
  si ya fue contactado.
- **Acciones:** enviar texto, plantilla o archivo; esperar; etiquetar; cambiar etapa; asignar
  (usa el reparto automático); marcar contactado; avisar al equipo; llamar a un webhook;
  **que responda la IA**; **pasar a una persona**.
- Cada ejecución queda registrada nodo por nodo (qué pasó, qué se envió, por qué se detuvo).
  Una ejecución con espera se guarda y la reanuda el worker.

Ejemplo: contacto nuevo del LIVE → esperar 2 min → enviar saludo → si responde, la IA contesta
dudas básicas → si pide cita, pasar a un agente.

## Agente de IA (el «Medical agent»)

Configuración por el jefe de marketing: instrucciones, tono, **base de conocimiento** (preguntas
frecuentes, precios autorizados, horarios, sedes), y un **playground** para probar antes de
activar. La clave del proveedor de IA va en el servidor (cifrada), nunca en el navegador.

Por ser una clínica, los **límites son obligatorios**:
- Se presenta como asistente virtual; **no da diagnósticos ni indicaciones médicas**.
- Pasa a una persona ante síntomas, urgencias, quejas, o cuando no sabe; tope de respuestas
  seguidas por conversación.
- Solo responde con la información cargada en la base de conocimiento.
- Cada respuesta queda registrada y hay un botón para que un agente tome el chat.
- Tope de gasto y panel de uso.

## Difusiones (4 pasos, como wacrm)

1. **Mensaje o plantilla.** 2. **Audiencia** por filtros (etapa, origen LIVE, fecha, etiqueta;
excluye descartados, bajas y contactados hace poco). 3. **Personalizar** variables (`{{nombre}}`).
4. **Programar y enviar** en tandas con ritmo y tope diario, con envío de prueba, pausa y
reanudar, y seguimiento de entregado/leído/fallido por destinatario.

## Modelo de datos (propuesto)

`chat_channels` (tipo, capacidades, política), `chat_conversations`, `chat_messages` (autor:
contacto/agente/bot/sistema, estado, id externo único), `automation_flows` (grafo en JSON,
versión, activo), `automation_runs` y `automation_steps`, `ai_agents`, `ai_knowledge_docs`,
`broadcasts`, `broadcast_recipients`, `opt_outs`, `message_templates`. Todo en el mismo
PostgreSQL y con la misma auditoría; los roles se siguen definiendo en Clerk.

## Fases (estimación gruesa, en semanas)

1. **Núcleo de chat + adaptadores + simulador + políticas** (topes, ventana de 24 h, bajas): 1–2.
2. **Adaptador del espejo de WhatsApp** (ver `docs/whatsapp-espejo.md`): 2–3.
3. **Motor de automatizaciones:** primero reglas simples con registro, luego el lienzo visual: 2–3.
4. **Agente de IA** (configuración, conocimiento, playground, límites, traspaso, uso): ~2.
5. **Difusiones** (asistente, segmentos, envío en tandas, seguimiento): 1–2.
6. **Adaptador de la API oficial** cuando se apruebe: 1–2, **sin tocar los flujos**.

Las fases 1, 3, 4 y 5 se pueden construir y probar por completo contra el simulador, sin
WhatsApp, y dejan todo listo para enchufar el canal real.

## Decisiones abiertas

1. ¿Esto va en esta versión o en el CRM nuevo con las APIs? (el diseño es el mismo; cambia dónde
   se construye).
2. Política del espejo: ¿difusiones apagadas y bot solo respondiendo a quien escribe (propuesta)?
3. Proveedor de IA y quién pone la clave.
4. Alcance de la primera entrega: ¿núcleo + simulador + reglas simples (propuesta) y luego el
   lienzo, o directamente el lienzo?
5. Consentimiento: texto de aceptación para recibir mensajes (Ley 29733 y reglas de WhatsApp) y
   cómo se registra.
