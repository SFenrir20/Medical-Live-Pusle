# Medical LivePulse

Plataforma para gestión de turnos y métricas de transmisiones en vivo.

## Estado real

Prototipo Expo + FastAPI con diseño de Lovable adaptado a componentes nativos. No incluye login real,
persistencia de turnos, migraciones funcionales, captura TikTok, métricas ni integración CRM.
La app tiene acceso de demostración (`andrea@livepulse.com` / `123456`), recuperación
sin envío de correo y selección de `@medical.cirugias` o `@medical.cirugias2`.
Recordar sesión guarda solamente un marcador de demostración, nunca la contraseña.
Los usuarios reales de LivePulse serán independientes de Medical 360.
Los endpoints de turnos no confirman operaciones sin persistencia: sin token responden 401;
con token responden 503 hasta implementar autenticación. Con identidad válida inyectada en
pruebas responden 501 hasta implementar persistencia, o 403 para cuentas no autorizadas.

## Ejecutar en Windows (PowerShell)

Desde la raíz del proyecto, para la API:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m uvicorn livepulse.entrypoints.api:app --host 127.0.0.1 --port 8000
```

Documentación de la API: http://127.0.0.1:8000/docs. `/health` solo comprueba el
proceso HTTP; no demuestra conexión a PostgreSQL ni captura TikTok.

En otra terminal, desde la raíz:

```powershell
cd apps/mobile
npm ci
npm run web
```

Para un teléfono físico, `localhost` apunta al teléfono. Configurar
`EXPO_PUBLIC_API_URL` en `apps/mobile/.env` con la dirección de la API accesible
desde el dispositivo. Reiniciar Expo después de cambiarla. La autenticación, CORS
para el cliente web y la persistencia deben implementarse antes de conectar el recorrido completo.

## Verificar

Backend: `python -m ruff check src tests` y `python -m pytest -q`, usando el entorno virtual.
App: `npm run lint`, `npm run typecheck`, `npm test -- --ci --runInBand`,
`npm run build:web` y `npx expo install --check`.

## Docker local

`docker compose -f infra/compose.yaml up --build -d --wait` inicia PostgreSQL, API y web.
Abrir http://localhost:8080. Las rutas web admiten recarga directa; `/api/` pasa a FastAPI.
`python infra/smoke.py` verifica HTTP, rutas y rechazo de entradas sin autenticación.
Las credenciales de Compose son exclusivamente de desarrollo local.
Monitor y worker están excluidos del arranque normal mediante un perfil porque son esqueletos.
No hay migraciones de tablas de negocio implementadas todavía.

## CI y artefactos Docker

GitHub Actions ejecuta `backend`, `mobile` y, si ambos pasan, `docker` en cada PR o push a main.
Incluye pruebas con PostgreSQL real, 5 pruebas de la app, lint, tipos, exportación web,
construcción de las 4 imágenes y arranque/pruebas HTTP de web/API/PostgreSQL.
Monitor/worker se construyen pero no se activan: aún son esqueletos.

En main se guardan los artefactos `livepulse-web` y `livepulse-docker-images`.
El segundo contiene `livepulse-images.tar.gz` (retención: 7 días). Después de descargarlo:

```powershell
docker load -i livepulse-images.tar.gz
docker compose -f infra/compose.yaml up -d --wait --no-build
```

PostgreSQL se descarga de su imagen oficial. Estos artefactos no son APK/IPA.
Este flujo valida y empaqueta; no despliega en un servidor de producción ni publica en tiendas.

## Pendientes antes de publicar

- Actualizar Expo SDK 51 y su conjunto de dependencias: la auditoría detectó vulnerabilidades
  que no se resuelven con `npm audit fix` sin cambios mayores.
- Implementar autenticación, autorización y turnos persistentes por cuenta.
- Probar PostgreSQL, concurrencia, Android/iOS y captura real de TikTok.
- La prueba Maestro actual verifica la navegación demo; no valida relevos reales.

## Estructura

- `apps/mobile`: aplicación móvil
- `backend`: API y servicios
- `infra`: infraestructura
- `e2e`: pruebas de recorrido
- `docs`: documentación
