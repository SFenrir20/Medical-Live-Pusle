# Pruebas en el servidor físico con Dokploy

En Environment de la aplicación Compose, guardar:

```dotenv
WEB_BIND=192.168.1.50
WEB_PORT=8090
CLERK_AUTHORIZED_PARTIES=["http://192.168.1.50:8090"]
```

Conservar la clave pública y el issuer de la instancia de pruebas de Clerk.
Comprobar antes que el puerto esté libre con `sudo ss -tlnp 'sport = :8090'`.
El servicio `web` publica el puerto interno 80. La API escucha internamente en
8000 y no debe recibir el mapeo de la web. Nginx envía `/api` a `api:8000`.

Desplegar la última versión de `developer` para las pruebas locales. En Preview Compose, comprobar que el
servicio web publica `192.168.1.50:8090:80` (o los mismos valores en formato
extendido). Si aparece 8081, revisar variables guardadas y cualquier override
de puertos de Dokploy. No basta con reiniciar el contenedor anterior.

Abrir `http://192.168.1.50:8090` desde la misma red. Comprobar
`http://192.168.1.50:8090/api/health`, que debe devolver `{"ok":true}`.

La imagen API aplica las migraciones antes de iniciar. Desde la terminal del contenedor `api`, verificar que la revisión sea `0003 (head)`; también se pueden aplicar manualmente:

```sh
python -m alembic upgrade head
python -m alembic current
```

Esta configuración es para pruebas LAN. Antes de publicar en un VPS, preparar
el acceso mediante dominio/HTTPS y revisar la configuración de producción.
El monitor de TikTok es opcional (perfil `live`); ver `docs/tiktok-monitor.md`. El worker se inicia con el mismo perfil `live`; ver `docs/operations.md`.
