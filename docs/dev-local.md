# Desarrollo local

Notas para entorno de desarrollo. No usar en producción.

## API

Desde la raíz del repo, en `backend/`: crear entorno virtual, instalar
dependencias de desarrollo y arrancar Uvicorn. La documentación
interactiva queda en `/docs` y `/health` solo comprueba el proceso HTTP.

## App

Desde la raíz del repo, en `apps/mobile/`: instalar dependencias con
`npm ci`. Arranque web con el script correspondiente. Para dispositivo
físico, configurar la URL pública de la API y reiniciar Expo.

## Verificar

- Backend: lint y pruebas con el entorno virtual.
- App: lint, tipos, pruebas, exportación web y chequeo de dependencias Expo.

## Docker

Compose levanta PostgreSQL, API y web. El script de smoke verifica HTTP,
rutas y rechazo de entradas sin autenticación. Las credenciales de
Compose son solo de desarrollo local. Monitor y worker están fuera del
arranque normal (perfil pendiente) porque aún son esqueletos. Sin
migraciones de negocio implementadas todavía.

## CI

GitHub Actions ejecuta `backend`, `mobile` y `docker` según el evento.
Guarda artefactos de la web y de imágenes Docker en `main`. Esos
artefactos no son APK/IPA y no despliegan a producción ni a tiendas.

## Pendientes antes de publicar

- Actualizar Expo SDK y dependencias.
- Implementar autenticación, autorización y turnos persistentes por cuenta.
- Probar concurrencia, Android/iOS y captura real de TikTok.
