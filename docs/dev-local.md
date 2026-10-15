# Desarrollo local de Social Pulse

## Backend

Desde `backend`, con Python 3.11 o superior y PostgreSQL disponible:

```sh
python -m venv .venv
# Activar .venv según el sistema operativo.
python -m pip install -e ".[dev]"
python -m alembic upgrade head
python -m uvicorn livepulse.entrypoints.api:app --reload
```

Configurar `backend/.env` con `DATABASE_URL`, `CLERK_ISSUER`,
`CLERK_AUTHORIZED_PARTIES=["http://localhost:8443"]` y
`CORS_ORIGINS=["http://localhost:8443"]`. Los arrays son JSON válido.

## Frontend

Copiar `apps/social-pulse/.env.example` a `.env.local` en esa misma carpeta y
configurar la clave pública Clerk y `VITE_API_URL=http://localhost:8000/api`.
Desde `apps/social-pulse`:

```sh
pnpm install --frozen-lockfile
pnpm dev
```

Vite usa el puerto 8443 por defecto (o `PORT`). Ajustar los orígenes del backend
si se cambia. El frontend es web React/Vite; no necesita herramientas móviles.

## Validación

En `backend`: `python -m ruff check src tests` y `python -m pytest -q`.
Las pruebas PostgreSQL requieren `DATABASE_URL` hacia una base de pruebas.
En `apps/social-pulse`: `pnpm build` valida TypeScript y compila la web.
Con el stack Docker iniciado: `python infra/smoke.py` desde la raíz.
