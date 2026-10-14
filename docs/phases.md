# Fases de implementación de LivePulse

Estado de trabajo; `implementado` no sustituye una prueba con TikTok/Leadsales reales.

| Fase | Entrega | Validación para cierre |
|---|---|---|
| 1. Captura | LIVE por cuenta/room, reconexión, bloqueo de monitor duplicado, eventos deduplicados, fin tras consultas offline y período de gracia | Pruebas PostgreSQL + dos LIVE reales, caída de red y reinicio |
| 2. Conciliación | Eventos y tramos asignados por cuenta e intervalo de turno; períodos sin responsable explícitos | Relevo, límites exactos y entradas tardías |
| 3. Métricas/contactos | Comentarios, likes, compartidos, regalos, seguidores observados, muestras de audiencia, interés por reglas, teléfonos, OCR revisado | Comparación con muestras reales; sin equiparar audiencia observada a espectadores únicos |
| 4. Integraciones/permisos | Roles asignados tras registro, CSV Leadsales y puente de estadísticas para Medical 360 | Configurar administrador inicial y secreto del puente; prueba de importación en Leadsales |
| 5. Operación | Estado del monitor y cola, migraciones, respaldo/restauración documentados, pruebas Docker | HTTPS, Clerk producción, respaldos programados y restauración en entorno aislado |
| 6. Móvil | Perfiles Expo para APK, Android e iOS | Credenciales de firma/cuentas de tiendas y pruebas físicas |

## Límites explícitos

- La hora de inicio es la primera observación del monitor; no se inventa el tiempo anterior a la conexión. Un cambio de sala puede cerrar una transmisión anterior con fin no confirmado.
- La desconexión no confirma un fin. Se requieren respuestas offline, separadas por el tiempo de gracia. Los errores intermedios reinician ese período.
- IDs del proveedor son la deduplicación preferida. Sin ID se usa la huella del mensaje: mensajes idénticos sin timestamp/ID pueden ser indistinguibles.
- `observed_users` son participantes identificados recibidos, no todos los espectadores. El promedio de audiencia es promedio de muestras, no promedio ponderado por tiempo.
- El interés se clasifica con reglas en español y debe revisarse. No interpreta diagnósticos ni equivale a una intención confirmada de compra.
- Mensajes directos, espectadores únicos totales, ventas y conversión real no tienen fuente conectada: se muestran como no disponibles.
- Exportar CSV no demuestra importación en Leadsales ni envío de mensajes. Nunca se inicia una conversación automáticamente.
- Eventos anteriores sin `broadcast_id` permanecen visibles como no vinculados; no se asignan a una transmisión inventada.

## Registro y roles

Los usuarios de Clerk entran a LivePulse para aparecer en la lista administrativa. Por defecto son `tiktoker`.
Configurar `ADMIN_USER_IDS=["user_ID_DEL_ADMIN"]` en el servidor tras registrar al administrador inicial.
Ese administrador asigna `marketing`, `care` (Atención al Cliente), `admin` o `tiktoker` desde la app.
Marketing ve métricas agregadas; Atención al Cliente ve los contactos. Solo un administrador gestiona roles.

## Leadsales

CSV con las columnas de la guía del centro de ayuda: Area code, Phone, Name, Value, Email, Tags, Company, Assignee.
Se exportan contactos marcados `ready`, sin conflictos de identidad pendientes. Los teléfonos son únicos en LivePulse.
Importar en Directorio → Import Leads y comprobar la plantilla de la cuenta antes de usarlo con datos reales.
Referencia: https://iozssqbrp.gleap.help/en/articles/5666227-how-to-import-my-contacts-into-leadsales
