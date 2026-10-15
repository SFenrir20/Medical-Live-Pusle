# Verificación de Social Pulse

## CI

1. Backend: Ruff, pytest con PostgreSQL aislado, migraciones desde cero y `alembic check`.
2. Web: instalación pnpm con lockfile, TypeScript y compilación Vite.
3. Docker: validación Compose, construcción de imágenes, arranque API/base/web,
   smoke HTTP, autenticación requerida y comprobación de tablas activas.

## Regresiones cubiertas

- Rutas de asistencia retiradas (404).
- Responsable explícita del LIVE y categoría «Sin asignar»; sin dependencia de asistencia.
- Deduplícación de contactos entre cuentas/LIVE, paginación y filtros de atención.
- Captura y publicación hacia el modelo de Social Pulse y el puente Medical 360.
- Retención de comentarios preservando deduplicación e interesados.

Las pruebas que necesitan PostgreSQL se omiten si `DATABASE_URL` no está definida.
La compilación local no valida Docker ni reemplaza una prueba real de TikTok, Clerk y despliegue.
