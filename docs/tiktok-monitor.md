# Monitor y procesamiento TikTok

El perfil Compose `live` inicia un monitor por cuenta y el worker. El arranque depende de la API saludable, que aplica Alembic `0003`.

- Un bloqueo PostgreSQL por cuenta evita dos monitores del mismo despliegue capturando en paralelo.
- `(account_id, room_id)` identifica un LIVE; reconectar conserva el registro y su primera hora observada.
- Una respuesta offline inicia el período de gracia. Solo una nueva respuesta offline después de ese período confirma el fin; un error reinicia la comprobación.
- Cambiar de sala cierra la anterior como fin no confirmado. Nunca se presenta su hora como una hora exacta emitida por TikTok.
- Cada evento queda vinculado al LIVE. Se prioriza `common.msg_id` para deduplicar y `common.create_time` para su hora, cuando existen.
- El worker bloquea lotes con `SKIP LOCKED`, crea hechos de métricas/contactos y marca el evento procesado dentro de la misma transacción. Reintentar no suma otra vez.
- Los regalos en racha se suman al finalizar la racha. Diamantes no equivalen a dinero ni a ingresos de la clínica.
- La relación con turnos se consulta por cuenta y hora del evento; los intervalos incluyen el inicio y excluyen el fin. Una entrada tardía no se atribuye retroactivamente.
- Marketing muestra señal de vida de monitores y worker, eventos pendientes y falta de datos.

```sh
docker compose -f infra/compose.yaml --profile live up -d --build
docker compose -f infra/compose.yaml logs -f monitor worker
```

Validar con LIVE reales: ambas cuentas simultáneas, corte de red, siguiente transmisión, reinicio de proceso, mensajes repetidos y un relevo de TikToker. La API externa puede cambiar y no se garantiza recuperar eventos ocurridos durante una interrupción.

Eventos antiguos sin sala identificable permanecen sin vincular. No se incluyen en métricas de un LIVE inventado.
Ver `phases.md` y `operations.md` para criterios de aceptación, configuración y pendientes externos.
