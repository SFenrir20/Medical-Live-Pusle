# Verificación local — 2026-09-22

## Alcance

Carpeta revisada: raíz del repo.
Es un esqueleto Expo y FastAPI, no la exportación del diseño mostrado en Lovable.

## Verificado

- Instalación npm y entorno virtual Python con dependencias de desarrollo.
- API arrancada con Uvicorn; `/health` y `/openapi.json` responden por HTTP.
- 9 pruebas de backend: salud HTTP, ausencia de credenciales, rechazo de token arbitrario,
  cuentas no autorizadas y endpoints sin persistencia que no confirman operaciones.
- Ruff, ESLint y comprobación TypeScript.
- 2 pruebas de componentes: error de API y bloqueo de envíos mientras hay una solicitud pendiente.
- Exportación web y navegación real inicio -> selección de cuenta -> estado de error.
- Dependencias alineadas con las versiones esperadas por Expo SDK 51.

## Correcciones

- Añadidas dependencias web y de navegación faltantes, configuración ESLint y Babel.
- Los turnos simulados ya no devuelven éxito; los tokens arbitrarios no identifican a un usuario.
- Acceso a cuentas controlado también en consulta y salida; respuestas 403 en lugar de errores internos.
- Docker copia el código antes de instalar el paquete y no intenta copiar migraciones inexistentes.
- Compose utiliza el hostname `db`, espera su healthcheck y arranca sin exigir un `.env` inexistente.
- Monitor y worker, aún sin implementación, quedan fuera del arranque normal.
- CI incorpora construcción web y validación/construcción de configuración Docker.
- La prueba Maestro ya no acepta estados `sending` o `confirmed` como equivalentes a un error.

## Límites y pendientes

- Sin Docker local: imágenes y Compose revisados, no ejecutados. No se probó PostgreSQL.
- No se ejecutaron Android, iOS, Maestro ni los workflows remotos de GitHub.
- No existe login, guardado de turnos, relevo real, migraciones de negocio ni captura TikTok.
- El cliente no envía credenciales en check-in. Se requiere implementar autenticación y CORS.
- La generación de Idempotency-Key actual no conserva la clave entre reintentos;
  esa regla y la protección contra concurrencia necesitan implementación persistente y pruebas.
- No hay diseño Lovable, extracción de teléfonos, clasificación de interés, CRM ni Medical 360 conectados.
- Auditoría npm inicial: 45 vulnerabilidades (1 crítica, 13 altas, 30 moderadas, 1 baja).
  `npm audit fix` sin cambios mayores no las resolvió. No implica que todas sean explotables
  desde la app; hay dependencias de herramientas. Actualizar el SDK y volver a auditar antes de publicar.
- Jest pasa con avisos de animaciones fuera de `act`; pytest pasa con avisos de deprecación de dependencias.
- Entorno local: Node 24 y Python 3.14. CI está configurado para Node 20 y Python 3.11;
  su ejecución remota sigue pendiente.

## Siguiente entrega funcional

Actualizar la base Expo, incorporar el diseño y completar identidad y turnos en PostgreSQL
con transacciones y unicidad por cuenta. Después validar el proveedor TikTok con dos cuentas.
