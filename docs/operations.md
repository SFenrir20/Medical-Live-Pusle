# Operación y despliegue

## Servidor de pruebas

1. Desplegar `developer` con las variables Clerk actuales y las imágenes reconstruidas. API aplica Alembic hasta `head` antes de iniciar.
2. Personalizar el token de sesión en Clerk (`{"metadata": "{{user.public_metadata}}"}`) y asignar a cada persona su rol en **Public metadata** (`{"livepulse": {"role": "..."}}`); ver `docs/clerk.md`. `ADMIN_USER_IDS=["user_..."]` queda solo como acceso de emergencia.
3. Habilitar perfil Compose `live` en Dokploy para arrancar **monitor y worker**. No requiere que una TikToker tenga abierto el navegador.
4. Comprobar `/v1/monitor/status` desde Marketing. Las cuentas sin señal reciente requieren revisar logs; no se debe interpretar ausencia de datos como cero espectadores.
5. Probar LIVE de ambas cuentas, corte de red, reinicio del monitor y exportación de contactos. Las pruebas simuladas del CI no sustituyen esta comprobación.

## Medical 360

Consume la API unificada (`/api/marketing/tiktok/*`) con `Authorization: Bearer`; ver
`docs/social-live-api.md`.

En Social Pulse: `MEDICAL360_TOKEN=<secreto aleatorio largo>` (y `MEDICAL360_EXPORT_TOKEN` si se
exportan comentarios). En el servidor de Medical 360: `LIVEPULSE_API_URL=<origen de la API>` y
`LIVEPULSE_MEDICAL360_TOKEN=<el mismo secreto>`. Nunca usar `VITE_*` para ese
secreto. Las rutas anteriores `/v1/integrations/medical360/*` siguen respondiendo, pero están
**obsoletas**: son adaptadores del mismo modelo y se retirarán.

## Respaldo y recuperación

Desde la raíz del despliegue (con acceso a Docker):

```sh
python infra/scripts/backup.py --output /ruta/protegida/backups
python infra/scripts/restore_check.py /ruta/protegida/backups/ARCHIVO.dump --database livepulse_restore_prueba
```

La restauración crea una base NUEVA cuyo nombre empieza con `livepulse_restore_`; falla si ya existe. Nunca restaura encima de la base operativa.
La base restaurada se conserva para inspección. Programar la copia y su retención en el servidor, guardar una copia fuera del VPS y probar la recuperación. Estos pasos no se ejecutaron contra tu servidor.

## Antes de VPS

- Dominio HTTPS, orígenes de Clerk exactos, instancia Clerk de producción y URL pública HTTPS.
- Cambiar credenciales PostgreSQL de ejemplo. El Compose actual es de pruebas; no publicar PostgreSQL en Internet.
- Configurar alertas del proveedor/Dokploy para servicios caídos y vigilar estado del monitor/cola.
- Limitar acceso a contactos por rol; definir retención de comentarios/teléfonos y revisar la política de datos del negocio.
- Probar respaldo/restauración, reinicio completo y rendimiento con el volumen esperado.

## Sustituir la web anterior

1. Configurar `VITE_CLERK_PUBLISHABLE_KEY` en Dokploy y reconstruir la imagen.
2. El dominio debe apuntar al servicio `web`, puerto interno `80`.
3. Conservar `WEB_BIND` y `WEB_PORT` del despliegue actual. `SOCIAL_PORT`/`SOCIAL_BIND`
   ya no se utilizan; el servicio duplicado `social` fue retirado.
4. Redesplegar la nueva versión. Si queda un contenedor antiguo `social`, retirarlo
   con la opción de eliminar huérfanos del mismo proyecto Compose (`--remove-orphans`).
   No borrar el volumen `pgdata` ni usar `down -v` en una base con datos.
5. Comprobar `/api/health`, iniciar sesión y abrir los paneles de Social Pulse.

Las tablas de asistencia histórica se preservan únicamente para compatibilidad con Alembic.
Los nombres internos del paquete Python, base de datos e imágenes de backend permanecen
compatibles con el despliegue existente.
