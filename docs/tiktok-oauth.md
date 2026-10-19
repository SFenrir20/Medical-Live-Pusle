# TikTok API for Business: URL de autorización

La app implementa el flujo **Marketing API / advertiser authorization** del formulario
"Create New App". No es Login Kit, Business Messaging API ni un proveedor de estadísticas LIVE.
Guardar una autorización no empieza a consultar datos ni cambia el monitor existente.

## Registro y despliegue

Advertiser redirect URL (exacta, sin barra final):

```text
https://livepulse.reporte.help/api/integrations/tiktok/callback
```

La ruta debe desplegarse con estos cambios. Abrirla sin parámetros devuelve una página pública
que permite ir a Social Pulse; no requiere una sesión de Clerk ni simula una autorización.
El proxy nginx conserva `/api`. El dominio de Dokploy debe apuntar a `web`, puerto interno 80.

Variables del servicio **api** (en Environment de Dokploy al usar `infra/compose.yaml`):

```dotenv
TIKTOK_APP_ID=<App ID del portal TikTok for Business>
TIKTOK_APP_SECRET=<Secret del portal TikTok for Business>
TIKTOK_REDIRECT_URI=https://livepulse.reporte.help/api/integrations/tiktok/callback
TIKTOK_TOKEN_ENCRYPTION_KEY=<clave Fernet>
```

Generar la clave una sola vez, en un entorno con `cryptography` instalado:

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Guardar esa clave estable en los secretos del despliegue y respaldarla separadamente de la BD.
Cambiarla sin migrar las credenciales cifradas impide leer las autorizaciones anteriores.
No colocar secretos en variables `VITE_*`, capturas, Git ni el navegador.

La migración `0012` agrega dos tablas; depende de la migración local existente `0011`.
El arranque del contenedor API ejecuta `alembic upgrade head` como ya hacía antes.
Desplegar API y web. Esta implementación local no despliega ni cambia Environment del VPS.

## Uso

1. Entrar a Social Pulse con rol gerente, jefe_marketing, supervisor o admin.
2. En vista marketing, pulsar **Conectar TikTok**, o abrir `/integraciones/tiktok`.
3. Pulsar **Autorizar en TikTok** y autorizar desde ese mismo navegador.
4. TikTok vuelve al callback con `auth_code` y `state`. El backend valida el intento,
   canjea el código, cifra el token en PostgreSQL y vuelve a una página con resultado fijo.

La cookie de enlace al navegador es Secure, HttpOnly, SameSite=Lax y dura diez minutos.
Usar HTTPS y el frontend/API bajo el mismo origen (el despliegue nginx predeterminado).
No iniciar con un enlace manual del portal: carece del intento y la cookie generados por Social Pulse.
Un callback vencido, repetido o sin cookie no canjea credenciales. En caso de fallo, iniciar de nuevo.
No se aceptan `code` de Login Kit ni callbacks de productos con otro protocolo.

## Datos y seguridad

- `tiktok_oauth_attempts`: hashes del state y del identificador de navegador, usuario iniciador,
  app, URL y expiración. Se consumen atómicamente; los vencidos se limpian al iniciar otra autorización.
- `tiktok_oauth_connections`: token cifrado con Fernet, cuentas publicitarias, scopes concedidos,
  usuario y fecha. El endpoint de estado nunca devuelve el token, el secreto ni el código.
- El estado muestra autorizaciones guardadas, no una comprobación remota de que sigan vigentes.
- Nginx no registra accesos a la ruta callback y Uvicorn elimina su query del access log.
  Si Traefik, Cloudflare o un APM registran URLs completas, excluir/redactar también la query
  de esta ruta en esos servicios; el código local no controla sus registros.
- Los DM, LIVE y reportes requieren permisos y conectores adicionales. `dm_capture_connected`
  no se modifica por completar esta autorización.

## Verificación

Las pruebas usan una base SQLite temporal y respuestas de TikTok simuladas: autorización,
roles, cookie, expiración, repetición, cancelación, fallo remoto y cifrado. No sustituyen
la prueba real en el VPS con la aplicación de TikTok aprobada y sus credenciales.

Referencias oficiales:
- [Autorización de anunciantes](https://business-api.tiktok.com/gateway/docs/index?doc_id=1738373141733378)
- [Autenticación y productos](https://business-api.tiktok.com/gateway/docs/index?doc_id=1766037914914818)
