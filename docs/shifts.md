# Turnos de LivePulse

## Reglas

- Cada cuenta de TikTok permite un turno abierto. Dos cuentas pueden tener turnos en paralelo.
- La usuaria elige una cuenta y pulsa MARCAR ENTRADA. La hora proviene de PostgreSQL, en UTC; la app la muestra en hora de Lima.
- Seleccionar cuenta, iniciar/cerrar sesión o cerrar la web no inicia ni termina un turno.
- Al volver a elegir una cuenta, la app recupera el turno del servidor. Actualiza el estado cada 30 segundos y al volver a la pantalla.
- MARCAR SALIDA requiere confirmar y solo puede cerrar el turno propio que se está mostrando.
- Si hay otra usuaria en la cuenta, RELEVAR Y MARCAR ENTRADA muestra una confirmación. Cierra el turno anterior con motivo `handover`, guarda quién lo cerró y abre el nuevo a la misma hora, en una transacción.
- Si el turno cambió desde que se mostró la pantalla, devuelve 409 y hay que revisar el estado actualizado antes de confirmar de nuevo.
- El historial muestra únicamente los turnos del usuario autenticado, con entrada, salida, duración y motivo de cierre. No se inventa una salida si aún no existe.
- Los turnos y el monitoreo de TikTok son independientes: marcar entrada no inicia un LIVE ni activa el monitor. No se ha implementado la conciliación entre ambos.

## Persistencia y concurrencia

Migración Alembic `0002`: tabla `shifts`, índice único parcial por cuenta para turnos abiertos y restricciones de fechas/cierre.
Bloqueo transaccional por cuenta para evitar dos entradas simultáneas, incluyendo una cuenta sin turnos previos.
`Idempotency-Key` obligatoria en las marcaciones: un reintento devuelve el resultado de la misma operación, sin duplicarla. Se vincula al usuario y al contenido de la petición; reutilizarla para otra operación produce 409.
Los registros de idempotencia se conservan; no hay limpieza automática todavía.

## Despliegue y comprobación

La imagen API aplica `python -m alembic upgrade head` antes de arrancar Uvicorn. Si falla la migración, no inicia la API. Esto asume una única instancia API como en el Compose actual; para múltiples réplicas usar una tarea de migración previa y única.

En Dokploy, desplegar la última versión de `developer` reconstruyendo API y web. No basta con reiniciar imágenes anteriores. En la terminal del contenedor API, `python -m alembic current` debe mostrar `0002 (head)`.

Prueba manual con dos usuarias:

1. Ana elige medical, marca entrada y recarga. Al elegir medical nuevamente ve su turno abierto.
2. Bea abre medical-2 y marca entrada. El turno de Ana continúa abierto.
3. Bea elige medical y confirma el relevo. El historial de Ana muestra cierre por relevo.
4. Ana intenta salir desde una pantalla antigua: no puede cerrar el turno de Bea.
5. Bea marca salida; el historial conserva la hora y la duración.

## Pruebas automatizadas

- Backend: autorización, persistencia, reintentos, dos cuentas, entradas/relevos simultáneos, salida atrasada, historial privado y paginación.
- App: selección, marcación explícita, confirmaciones, recuperación al remontar, reintento con la misma clave e historial.
- CI en main/developer/deploy: PostgreSQL real en esquemas de prueba aislados, migraciones desde base vacía, `alembic check`, lint, tipos, exportación web y Docker.

Pendientes ajenos a esta entrega: captura estable de LIVE, conciliación turnos/LIVE, estadísticas, CRM y dashboard Medical 360. Este cambio no los declara listos para producción.
