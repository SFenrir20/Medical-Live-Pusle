# Operación y despliegue

## Servidor de pruebas

1. Desplegar `developer` con las variables Clerk actuales y las imágenes reconstruidas. API aplica Alembic `0003` antes de iniciar.
2. Registrar un administrador en Clerk, obtener su ID y configurar `ADMIN_USER_IDS=["user_..."]`; reiniciar API. Entrar a Panel del equipo para asignar los roles de las personas que hayan abierto ese panel.
3. Habilitar perfil Compose `live` en Dokploy para arrancar **monitor y worker**. No requiere que una TikToker tenga abierto el navegador.
4. Comprobar `/v1/monitor/status` desde Marketing. Las cuentas sin señal reciente requieren revisar logs; no se debe interpretar ausencia de datos como cero espectadores.
5. Probar LIVE de ambas cuentas, corte de red, reinicio del monitor, relevo y exportación de contactos. Las pruebas simuladas del CI no sustituyen esta comprobación.

## Medical 360

En LivePulse: `MEDICAL360_TOKEN=<secreto aleatorio largo>`.
En servidor de Medical 360: `LIVEPULSE_API_URL=<URL interna de API sin /v1>` y `LIVEPULSE_MEDICAL360_TOKEN=<mismo secreto>`.
Si se usa la web de LivePulse como proxy, la URL termina en `/api`.
Se modificó el repositorio `reportes_streamlit`: su backend protege el puente con los permisos de Marketing existentes, y solo su servidor envía el secreto. Nunca usar VITE_* ni EXPO_PUBLIC_* para ese secreto.
El puente solo permite consultar métricas agregadas; no entrega teléfonos, comentarios ni datos de pacientes.

## Respaldo y recuperación

Desde la raíz del despliegue (con acceso a Docker):

```sh
python infra/scripts/backup.py --output /ruta/protegida/backups
python infra/scripts/restore_check.py /ruta/protegida/backups/ARCHIVO.dump --database livepulse_restore_prueba
```

La restauración crea una base NUEVA cuyo nombre empieza con `livepulse_restore_`; falla si ya existe. Nunca restaura encima de la base operativa.
La base restaurada se conserva para inspección. Programar la copia y su retención en el servidor, guardar una copia fuera del VPS y probar la recuperación. Estos pasos no se ejecutaron contra tu servidor.

## Antes de VPS

- Dominio HTTPS, orígenes de Clerk exactos, instancia Clerk de producción y URL API pública HTTPS para móviles.
- Cambiar credenciales PostgreSQL de ejemplo. El Compose actual es de pruebas; no publicar PostgreSQL en Internet.
- Configurar alertas del proveedor/Dokploy para servicios caídos y vigilar estado del monitor/cola.
- Limitar acceso a contactos por rol; definir retención de comentarios/teléfonos y revisar la política de datos del negocio.
- Probar respaldo/restauración, reinicio completo y rendimiento con el volumen esperado.

## Builds móviles

Se incluye `apps/mobile/eas.json`: `preview` genera APK, `production` genera distribución Android/iOS, `ios-simulator` permite prueba en simulador.
Configurar el proyecto EAS, `EXPO_PUBLIC_API_URL` HTTPS y clave pública Clerk. Activar Native API de Clerk y registrar los identificadores de `app.json`.
Desde `apps/mobile`: `npx eas-cli build --platform android --profile preview` o `npx eas-cli build --platform ios --profile production`.
Las cuentas Expo/Apple, firmas, dispositivos y publicación en tiendas requieren configuración del propietario. No se generaron APK/IPA ni se publicaron aplicaciones con este cambio.
