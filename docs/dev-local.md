# Desarrollo local

Notas para entorno de desarrollo. No usar en producciÃ³n.

## API

Desde la raÃ­z del repo, en `backend/`: crear entorno virtual, instalar
dependencias de desarrollo y arrancar Uvicorn. La documentaciÃ³n
interactiva queda en `/docs` y `/health` solo comprueba el proceso HTTP.

## App

Desde la raÃ­z del repo, en `apps/mobile/`: instalar dependencias con
`npm ci`. Arranque web con el script correspondiente. Para dispositivo
fÃ­sico, configurar la URL pÃºblica de la API y reiniciar Expo.

## Verificar

- Backend: lint y pruebas con el entorno virtual.
- App: lint, tipos, pruebas, exportaciÃ³n web y chequeo de dependencias Expo.

## Docker

Compose levanta PostgreSQL, API y web. El script de smoke verifica HTTP,
rutas y rechazo de entradas sin autenticaciÃ³n. Las credenciales de
Compose son solo de desarrollo local. Monitor y worker estÃ¡n fuera del
arranque normal (perfil pendiente) porque aÃºn son esqueletos. Sin
migraciones de negocio implementadas todavÃ­a.

## CI

GitHub Actions ejecuta `backend`, `mobile` y `docker` segÃºn el evento.
Guarda artefactos de la web y de imÃ¡genes Docker en `main`. Esos
artefactos no son APK/IPA y no despliegan a producciÃ³n ni a tiendas.

## Pendientes antes de publicar

- Configurar Clerk siguiendo `docs/clerk.md` y probar el acceso real.
- Implementar autenticaciÃ³n, autorizaciÃ³n y turnos persistentes por cuenta.
- Probar concurrencia, Android/iOS y captura real de TikTok.
