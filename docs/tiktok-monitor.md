# Monitor TikTok

Adaptado del script manual (`scraper_tiktok.py`, TikTokLive 7.0.0, solo
comentarios a CSV) al servicio `backend/.../entrypoints/monitor.py`.

## Cambios

- Un monitor por cuenta (`medical`, `medical-2`) con reconexión propia y
  backoff (2s → 60s). Una caída no detiene la otra cuenta.
- Eventos: comment, gift, like, share, join, live_end.
- Todo evento lleva `account_id` + `event_id` único. Reprocesar es no-op
  (UNIQUE en `raw_events`, `MemorySink`/`PostgresSink`).
- Desconexión != fin: `DisconnectEvent` solo reintenta. `LiveEndEvent`
  abre gracia de 120s y solo cierra si el re-chequeo confirma offline.

## Validación manual (LIVE real)

Desde `backend/` con el venv:

```powershell
.\.venv\Scripts\python.exe -m livepulse.entrypoints.monitor -a medical -t 120 -o debug_medical.csv
```

Compara conteo vs pantalla TikTok. Esto valida al proveedor, no la
lógica (la lógica se prueba con eventos simulados en CI).

## Pendiente

- Migración Alembic de `broadcasts`/`raw_events` (modelos listos).
- Worker: conciliación LIVE↔turno y métricas sobre eventos procesados.
- Activar `monitor`/`worker` en Compose (quitar perfil) tras la migración.
