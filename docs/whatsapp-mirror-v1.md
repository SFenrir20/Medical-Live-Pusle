# WhatsApp mirror V1 — operación

Implementación local: conector Node/Baileys, worker persistente, API con permisos Clerk y pantalla
chats de **Embudos**. **La prueba real requiere desplegar y vincular el teléfono; las pruebas automáticas
usan un transporte simulado y no demuestran conectividad con una cuenta real.**

## Alcance actual

- Un número empresarial vinculado por QR, detectado automáticamente y guardado en la primera
  vinculación. No hace falta colocar el teléfono en variables de entorno.
- Recepción de mensajes individuales desde la vinculación y envío de texto e imágenes por asesoras.
- Mensajes de texto enviados desde el celular u otro dispositivo también aparecen, sin inventar
  qué persona los escribió. Grupos, estados y canales quedan fuera de la bandeja.
- Imágenes normales JPG/PNG/WebP: recepción, ampliación y envío de hasta 8 MB. Se guardan cifradas
  en el volumen del conector. Ver `crm-omnicanal.md`, migración 0017.
- Audios, notas de voz, videos, documentos y stickers: se reciben y se ven en la bandeja (reproductor,
  video, tarjeta de descarga). El conector detecta el tipo real por los bytes, nunca por lo que declara
  el remitente, y el API lo vuelve a validar. Enviar audio, video o documentos desde el CRM aún no existe
  (solo texto e imágenes). Los archivos de una sola visualización siguen en el teléfono.
  Ver `crm-omnicanal.md`, migración 0018.
- Se importa el historial individual que WhatsApp entrega al conector, con fechas originales y
  deduplicación por mensaje. También se pueden solicitar lotes anteriores por chat sin desvincular.
  No es una copia de seguridad ni una garantía de recuperar todo un período sin conexión.
- Contacto común por número E.164, incluso si WhatsApp llegó antes de la captura TikTok. Las
  apariciones en distintas cuentas/LIVE permanecen separadas dentro del historial del contacto.
- Roles: ventas ve sus conversaciones y las libres; debe tomar un contacto antes de enviar.
  Gerencia/jefatura revisan todas, sin enviar. Supervisor/admin revisan todas y gestionan el QR;
  para enviar también deben ser propietarios del contacto (reasignación desde el CRM).
- Los bots, agentes LLM y difusiones existentes permanecen desconectados del transporte real.
  No se necesitan credenciales de WhatsApp Cloud API ni permisos de TikTok/Meta para este conector.

No es una integración oficial de Meta. Una actualización de WhatsApp puede interrumpirla;
el código no garantiza ausencia de restricciones de cuenta.

## Configuración en el VPS / Dokploy

En las variables del proyecto Compose, conservar los valores existentes y agregar:

```dotenv
COMPOSE_PROFILES=live,whatsapp
WA_GATEWAY_URL=http://wa-gateway:3001
WA_GATEWAY_TOKEN=<secreto aleatorio de al menos 32 caracteres>
WA_SESSION_KEY=<64 caracteres hexadecimales>
```

`WA_EXPECTED_PHONE` es opcional: se puede omitir o dejar vacío. Si se configura, restringe la
vinculación a ese número E.164. Sin esa variable, se detecta la cuenta al escanear el QR y se
conserva en el volumen para futuras conexiones.

Generar **dos valores diferentes**, ejecutando dos veces este comando localmente en el servidor:

```sh
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Guardar los secretos únicamente en la configuración del servidor; no en Git ni variables VITE.
`WA_GATEWAY_TOKEN` debe coincidir en API, gateway y worker. `WA_SESSION_KEY` debe permanecer estable:
el conector rechaza un volumen cifrado con otra clave. Respaldar la clave separada del volumen.

Construir/desplegar el Compose actualizado. La API ejecuta Alembic hasta `0015`; depende de las
migraciones previas `0013` (presencia) y `0014` (chat/automatización). No desplegar solo el frontend.
Si se usa la CLI en lugar de Dokploy (desde la raíz del repositorio, con `.env` configurado):

```sh
docker compose --env-file .env -f infra/compose.yaml --profile live --profile whatsapp up -d --build
```

El dominio sigue apuntando a `web:80`. **No publicar el puerto 3001**. El volumen `wa-session`
conserva la sesión, eventos pendientes y claves de idempotencia entre recreaciones del contenedor.
Mantener una sola instancia de `wa-gateway` y de `wa-worker` por sesión. No escalar estos servicios.

Al arrancar, el gateway recupera automáticamente las credenciales guardadas, incluida la identidad
`creds.me.id` de una vinculación por QR (Baileys puede mantener `registered=false` en ese caso).
No es necesario pulsar el botón tras cada reinicio si la sesión sigue siendo válida. Un volumen
nuevo o una sesión revocada por WhatsApp requieren vinculación; esta comprobación no evita el QR.
Para aplicar la corrección de recuperación hay que reconstruir `wa-gateway`, conservando el volumen
y la misma `WA_SESSION_KEY`; reiniciar una imagen antigua no incorpora el cambio.

## Vinculación y verificación real

1. Ingresar a Social Pulse con rol supervisor/admin; abrir **Ajustes → Conexión de WhatsApp**.
2. Pulsar **Vincular / reconectar**. En el teléfono empresarial que quieres vincular: WhatsApp →
   Dispositivos vinculados → Vincular dispositivo → escanear el QR.
3. Comprobar **Conectado**, el número detectado y que no aparezca una alerta de sincronización
   atrasada. Después de esta primera vinculación, intentar vincular otro número provoca cierre
   de esa sesión, sin importar sus conversaciones al CRM.
4. Desde un teléfono de prueba autorizado, enviar texto al número vinculado. Debe aparecer
   una conversación; tomarla con una asesora y responder desde Social Pulse.
5. Verificar el texto en el teléfono receptor y las confirmaciones disponibles en Social Pulse.
   Repetir escribiendo desde el celular empresarial: aparecerá «Desde teléfono u otro dispositivo».
6. Capturar ese mismo número en un LIVE de prueba: abrir **Abrir WhatsApp** junto al teléfono y
   verificar las apariciones, cuenta, responsable y tiempo hasta el primer envío posterior.
7. Reiniciar el gateway: debe recuperar la sesión sin QR. Cortar y restaurar la conexión durante
   un envío: revisar su estado antes de redactar otro; no debe duplicarse automáticamente.
8. Probar otra asesora: no debe acceder al contacto ya asignado. Comprobar acceso de revisión
   de jefatura y ausencia del QR para roles sin administración de WhatsApp.

Estos pasos requieren el teléfono y el VPS; no se ejecutaron desde el entorno de desarrollo.

## Estados y evidencia

| Estado | Qué acredita |
|---|---|
| En cola | El servidor aceptó la solicitud de la asesora. Aún no salió por WhatsApp. |
| Confirmando envío | Se inició el intento; se consulta el mismo identificador si hay timeout. |
| Enviado | El transporte confirmó la presentación del mensaje o llegó su eco. No prueba entrega. |
| Entregado | Se observó la confirmación de entrega de WhatsApp. |
| Leído | Se recibió una confirmación de lectura; puede no estar disponible. |
| Envío sin confirmar | Hubo un resultado ambiguo. No se reenvía automáticamente. Revisar el teléfono. |
| No enviado | Se canceló antes de transmitir, por ejemplo porque cambió la asesora asignada. |

Cada envío tiene un UUID estable. Gateway y backend conservan la identidad durante reintentos.
Los eventos se confirman al gateway **después** de guardar en PostgreSQL. Las confirmaciones
pueden llegar antes del mensaje; se conservan y se aplican después, sin retroceder de leído a enviado.

Al confirmarse un envío real de la asesora propietaria, un contacto `new` pasa a `contacted`,
con la fecha de envío y auditoría `whatsapp_sent`. Un mensaje en cola o fallido no lo cambia.
Un envío escrito en el teléfono no se atribuye a una asesora ni cambia automáticamente su estado.
El estado CRM también puede haberse marcado manualmente: **validar el mensaje y sus confirmaciones**,
no solamente la etiqueta «contactado». «Leído» tampoco equivale a respuesta ni cita confirmada.

Las horas se guardan en UTC y se muestran en Lima. Cuando WhatsApp proporciona una fecha de
entrega/lectura, se conserva; si solo da un cambio de estado, se registra cuándo fue observado.
Por ello no se promete precisión exacta del instante de lectura tras una desconexión.

Para cada captura LIVE se muestra el **primer envío posterior a esa captura**. No se usan mensajes
anteriores para afirmar que el nuevo LIVE fue atendido. Esta correlación temporal no demuestra
que el mensaje se refería a ese LIVE; si hubo dos apariciones antes de responder, el mismo envío
puede ser posterior a ambas. Las apariciones se muestran por separado, sin contar como nuevo un
teléfono ya existente.

## Diagnóstico y recuperación

### Recuperación automática y estado de salud

El conector verifica cada 10 segundos si el intento de conexión lleva más de 60 segundos
o si el transporte de una sesión conectada se cerró sin procesarse su aviso. En esos casos
retira el socket anterior y reintenta con espera progresiva y variación aleatoria, hasta
60 segundos entre intentos. Una bandeja sin mensajes no se considera una conexión caída:
Baileys conserva sus propios heartbeats del protocolo. No se borran credenciales por un timeout.
Una sesión revocada o reemplazada sigue requiriendo una vinculación explícita.

- `/health`: comprueba que HTTP responde (liveness); incluye `connected`, sin datos personales.
  Docker usa esta ruta. Que esté sano no significa que WhatsApp esté vinculado.
- `/ready`: devuelve 200 solo con estado `connected`; devuelve 503 durante desconexión o QR.
  Es una señal de disponibilidad del transporte, no acredita importación en PostgreSQL.
- `/status`: requiere el secreto interno. Añade `connected_at`, `retry_at`,
  `reconnect_attempt`, `last_disconnect_code`, `recovery_reason` y `pending_events`.
  El API agrega `sync_at` y `sync_ok` usando el heartbeat del worker; la pantalla distingue
  la conexión de la sincronización y muestra eventos pendientes cuando esta se retrasa.

El cliente interno espera hasta 55 segundos por `/send` (el intento del conector está limitado
a 45 segundos). Los demás accesos conservan el timeout de 20 segundos. El worker deja de
iniciar envíos adicionales cuando su tanda consume 15 segundos, para volver a importar
mensajes entrantes; un envío ya iniciado puede durar su presupuesto completo. Una caída HTTP
sigue consultando el mismo UUID y un resultado ambiguo nunca se reenvía automáticamente.

Al recibir SIGTERM/SIGINT el conector cancela reconexiones y cierra el transporte sin cerrar
sesión en WhatsApp. Espera hasta 8 segundos por trabajo en curso; los intentos ambiguos quedan
persistidos para reconciliación. Conservar el volumen y la clave al recrear el contenedor.

La bandeja consulta de nuevo al recuperar internet, enfocar la ventana o volver a una pestaña
visible. No solapa consultas del mismo ciclo y cancela las del contexto anterior al cambiar
filtros o conversación. Las respuestas antiguas no reemplazan la lista del filtro actual.
La reconexión por sí sola no garantiza recuperar todos los mensajes de una desconexión. La
recuperación de historial se describe abajo; requiere prueba real con el número vinculado.

- `Conector no disponible`: comprobar variables y servicio `wa-gateway`.
- Conectado pero sincronización atrasada: comprobar `wa-worker`, migración y acceso a PostgreSQL.
- `Requiere nueva vinculación`: pulsar vincular y escanear de nuevo. El historial en PostgreSQL
  permanece; solo se renueva la autenticación del dispositivo.
- Pendientes de identificar: WhatsApp envió un identificador LID sin teléfono. Se guardan cifrados
  y se reintentan cuando llega la correspondencia. No se interpreta un LID numérico como teléfono.
- Mensajes o confirmaciones pendientes de revisión: un evento tiene datos inválidos o una
  identidad contradictoria. Se conserva completo y cifrado en `quarantined_events`, sin marcarlo
  como importado. Los eventos posteriores siguen procesándose. El contador en pantalla permanece
  visible aunque el worker vuelva a sincronizar correctamente.
- Para desvincular, usar **Dispositivos vinculados** en el teléfono y cerrar el dispositivo de
  Social Pulse. El conector detectará el cierre. No borrar el volumen para resolver un timeout:
  contiene las claves que evitan duplicados.
- El número detectado queda asociado al volumen, aunque `WA_EXPECTED_PHONE` siga vacío.
  Quitar la variable no desvincula una cuenta ya guardada. V1 no admite cambiar de cuenta
  conservando el mismo canal; requiere una migración explícita de datos y sesión.

Ejemplo de inspección, adaptando nombres de proyecto si se usa Dokploy:

```sh
docker compose --env-file .env -f infra/compose.yaml --profile whatsapp logs --tail 100 wa-gateway wa-worker
```

### Recuperación de un bucle `WhatsApp sync will retry (ValueError)`

Ese registro antiguo solo da la clase de error. No identifica qué dato falló. Un evento rechazado
podía quedarse al inicio de la cola e impedir las siguientes importaciones; reiniciar repetía el
mismo intento. La corrección incorpora validación con motivos seguros y preservación del evento
en una cola de revisión, sin eliminar su contenido ni asociarlo a otro contacto.

Desplegar **gateway y worker actualizados juntos**, además del frontend para mostrar el contador.
No se necesita otra migración PostgreSQL: el gateway crea su tabla de revisión automáticamente
en el volumen existente. Conservar ese volumen y sus claves. Si el gateway aún es antiguo y no
acepta guardar el evento para revisión, el worker se detiene sin confirmarlo ni eliminarlo.

Los logs nuevos indican `sequence` y `reason`, por ejemplo `invalid_timestamp`, `invalid_phone`,
`receipt_phone_mismatch` u `outgoing_conversation_mismatch`. No incluyen teléfonos, cuerpos ni
credenciales. Una caída de PostgreSQL o de la red sigue siendo reintentable; no se trata como un
evento inválido ni se elimina de la cola.

Para consultar los primeros 100 eventos pendientes de revisión (solo secuencias y motivos),
desde el VPS, adaptando el nombre del contenedor si cambió:

```sh
sudo docker exec medical-livepulse-deploy-vxzqh4-wa-worker-1 python -c "import asyncio; from livepulse.modules.whatsapp.gateway import call; print(asyncio.run(call('/events/rejected')))"
```

Después de corregir la causa, un administrador puede reponer una secuencia concreta en la cola.
Sustituir `123` por una secuencia de la consulta anterior; no ejecutar un reintento masivo a ciegas:

```sh
sudo docker exec medical-livepulse-deploy-vxzqh4-wa-worker-1 python -c "import asyncio; from livepulse.modules.whatsapp.gateway import call; print(asyncio.run(call('/events/retry', {'sequences': [123]})))"
```

La reposición conserva el UUID original para impedir duplicados. Si el dato sigue siendo inválido,
volverá a quedar guardado para revisión. No borrar la cola ni el volumen para quitar el aviso.

Las credenciales Signal, eventos pendientes y registros de envío del gateway se cifran por valor
con AES-256-GCM. El volumen SQLite no se cifra como dispositivo completo. Los mensajes del CRM
se guardan en PostgreSQL, bajo la misma protección y respaldos que el resto del CRM. Esta V1 no
purga chats automáticamente; la retención de comentarios TikTok no borra mensajes WhatsApp.

## Recuperar mensajes anteriores (migración 0022)

Desplegar API/worker con la migración `0022`, `wa-gateway` y `web`. Conservar `wa-session` y
`WA_SESSION_KEY`. El gateway acepta `messaging-history.set` y solicita historial en la configuración
de Baileys; WhatsApp decide qué lotes ofrece y puede no volver a enviar historial tras una reconexión.

Para una cuenta ya vinculada, abrir un chat desde **Embudos**, desplegar el menú de tres puntos y
pulsar **Recuperar historial**. Se pide al teléfono hasta 50 mensajes anteriores por solicitud:

- La primera petición parte del mensaje de WhatsApp más reciente guardado para ese chat, para
  buscar huecos antes de los mensajes nuevos. Se necesita al menos uno como referencia.
- Las siguientes peticiones continúan desde el mensaje más antiguo recibido en los lotes solicitados.
  El cursor se guarda cifrado y sobrevive a reinicios. Hay una espera mínima de 60 segundos por chat.
- **Buscar de nuevo desde recientes** reinicia ese cursor para buscar un hueco más reciente.
- Una solicitud aceptada no significa importación terminada. Mantener el teléfono disponible;
  si no llega un lote, no se anuncia el historial como completo ni se inventan mensajes.
- La respuesta se procesa por la misma cola persistente y el worker. Se evitan duplicados, se
  conservan las fechas originales y se pagina por fecha/id, no por orden de llegada al servidor.
- Los mensajes importados no incrementan los no leídos ni ejecutan reglas de citas, reasignaciones
  o marcas de contactado; la marca persistente también protege frente a recibos y reenvíos posteriores.
- Los adjuntos históricos se intentan descargar al abrirlos. Pueden haber caducado en WhatsApp.
  Grupos/estados/canales y contenido de una sola visualización no se incorporan como adjuntos normales.
- Solo usuarios con acceso al chat y permiso `wa:send` o `wa:manage` pueden solicitar los lotes.

En Ajustes, **Última comprobación del servicio** es el heartbeat del worker, no prueba de historial
completo. **Último lote de historial recibido** indica recepción en el gateway; aún puede quedar
trabajo pendiente de importar en PostgreSQL.

## Comprobaciones de desarrollo

```sh
cd services/wa-gateway
npm ci --ignore-scripts
npm test
```

```sh
cd backend
python -m pytest tests/social_live/test_whatsapp.py -q
```

```sh
cd apps/social-pulse
pnpm build
```

Pruebas: cifrado/reinicio, clave incorrecta, LID, cuenta equivocada, envío idempotente/ambiguo,
deduplicación, permisos/asignación, eventos fuera de orden, correlación por LIVE y QR restringido.
