# Acceso con Clerk

LivePulse usa usuarios independientes de Medical 360. Clerk administra identidad,
registro, verificación de correo, recuperación y sesiones. FastAPI verifica JWT
RS256 mediante las claves públicas JWKS de la instancia. No requiere Secret Key
ni un segundo backend propio. Nunca se debe poner una Secret Key en EXPO_PUBLIC_*.

## Configuración local

1. En Clerk, habilitar correo/contraseña y verificación de correo para registro.
   El formulario web respeta los métodos configurados en esa instancia.
2. Copiar `apps/mobile/.env.example` a `apps/mobile/.env.local` y poner la
   Publishable Key. Configurar `EXPO_PUBLIC_API_URL=http://localhost:8000`.
3. Crear `backend/.env` con:

```dotenv
CLERK_ISSUER=https://your-instance.clerk.accounts.dev
CLERK_AUTHORIZED_PARTIES=["http://localhost:8081","http://localhost:8080"]
CORS_ORIGINS=["http://localhost:8081","http://localhost:8080"]
LIVEPULSE_USER_ACCOUNTS={}
```

Usar exactamente el Frontend API URL de la misma instancia de la clave pública.
Los orígenes deben coincidir con el puerto y dominio reales de la web. En producción,
reemplazar localhost por los dominios HTTPS permitidos y usar una instancia de producción.

4. Desde `backend`: `.venv\Scripts\python -m uvicorn livepulse.entrypoints.api:app --reload`.
5. Desde `apps/mobile`: `npm ci`, luego `npm run web -- --port 8081`.

Los archivos .env locales están ignorados por Git. El build web incorpora la clave
pública y la URL de API: cambiar estas variables requiere recompilar.

## Aprobación y permisos

Un usuario autenticado sin asignación recibe `/v1/me` con `status=pending` y
`accounts=[]`; no puede consultar ni marcar turnos. Por ahora el operador asigna
usuarios desde la configuración del servidor, usando el ID `user_...` que muestra Clerk:

```dotenv
LIVEPULSE_USER_ACCOUNTS={"user_ID_REAL":["medical","medical-2"]}
```

Reiniciar la API tras cambiarlo. Una lista vacía revoca el acceso operativo.
No usar email como ID ni confiar en roles/cuentas enviados por el cliente o en
metadatos editables por usuarios. El panel de aprobación y la persistencia de
usuarios/permisos en PostgreSQL quedan pendientes para el módulo de identidad.

El cierre de sesión termina el acceso en Clerk; no equivale a marcar salida de
jornada. El backend verifica tokens de corta duración; una revocación de sesión
puede tardar hasta que venza el token ya emitido. Los permisos locales se consultan
en cada petición. No hay una sesión autenticada de demostración.

## Android y iPhone

El SDK usa SecureStore para la sesión nativa y `useHostedAuth` para el portal.
Activar Native API en Clerk y registrar los identificadores de `app.json`
(`com.medical.livepulse`) antes del build de producción. Confirmar esos
identificadores definitivos antes de publicar en tiendas. El plugin de Clerk
configura el retorno del portal a la app; cambios requieren recompilar el binario.
La URL de API de un teléfono debe ser accesible desde el teléfono, no localhost.
La exportación de JavaScript no sustituye una prueba real de APK/IPA.

## Docker y CI

Crear `.env` en la raíz a partir de `.env.example` y ejecutar desde esa raíz:

```powershell
docker compose --env-file .env -f infra/compose.yaml up --build -d
```

Web: http://localhost:8080. En Docker la app usa `/api` por el proxy de Nginx.
La clave pública se pasa como build argument; el issuer y los permisos como
variables del contenedor API. No se copia ningún .env a las imágenes.

CI valida las rutas sin credenciales reales: pruebas con JWT firmados con claves
RSA efímeras y mocks solo en tests de UI. Los artefactos de CI sin clave configurada
muestran "Acceso no configurado"; para habilitar Clerk hay que construir con la
clave de la instancia. CI no crea usuarios ni envía correos reales.

## Alcance

Integrado: Clerk, protección de pantallas, Bearer token, `/v1/me`, permisos por cuenta.
Pendiente: persistencia de jornadas, monitor TikTok, métricas y panel de aprobación.
Las rutas de jornadas autorizadas siguen devolviendo 501, nunca un registro ficticio.

Referencias: https://clerk.com/docs/expo/getting-started/quickstart
https://clerk.com/docs/guides/sessions/manual-jwt-verification
