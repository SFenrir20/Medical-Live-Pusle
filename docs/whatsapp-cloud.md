# WhatsApp Cloud API (oficial de Meta): webhook

Recibe en Social Pulse los mensajes y los estados de entrega que Meta envía. Convive con el espejo
(`wa-gateway`): ambos producen los mismos eventos y pasan por la misma bandeja, CRM, embudos y reglas.

## Qué ya está y qué falta

| Ya está | Falta (siguientes pasos) |
|---|---|
| Verificación del webhook (el «apretón de manos» de Meta) | Enviar mensajes por la Cloud API |
| Firma `X-Hub-Signature-256` obligatoria en cada entrega | Plantillas aprobadas y difusiones |
| Mensajes entrantes y estados (enviado / entregado / leído) | Regla de la ventana de 24 horas |
| Reenvíos de Meta inofensivos (id determinista por mensaje) | Descarga de fotos, audios y documentos (hoy llegan como el mismo aviso que usa el espejo) |

## Variables del servidor (servicio `api` en Dokploy; nunca en el repositorio)

| Variable | Qué es |
|---|---|
| `WA_CLOUD_VERIFY_TOKEN` | Texto que **tú inventas** (clave larga y aleatoria). El mismo va en Meta. |
| `WA_CLOUD_APP_SECRET` | «Clave secreta de la app»: Meta → Configuración de la app → Básica. |
| `WA_CLOUD_PHONE_NUMBER_ID` | Opcional pero recomendado: identificador del número; ignora eventos de otros números de la cuenta. |

Sin `VERIFY_TOKEN` y `APP_SECRET` el webhook responde 503 y no acepta nada.
Generar el texto de verificación: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Configurar en Meta

1. Cargar las variables en Dokploy y **redesplegar `api` y `web`** (el webhook debe estar arriba antes de verificar).
2. Meta → tu app → Casos de uso → WhatsApp → Personalizar → **Configuración** → Webhook:
   - **URL de devolución de llamada:** `https://TU-DOMINIO/api/whatsapp-cloud/webhook`
   - **Identificador de verificación:** el valor de `WA_CLOUD_VERIFY_TOKEN`.
   - Pulsa **Verificar y guardar**.
3. En los campos del webhook, suscribe **`messages`**.
4. Mientras la app esté **sin publicar**, Meta solo envía eventos de números de prueba y de personas con rol
   en la app; para mensajes de pacientes reales hay que publicarla (modo Live).

## Ojo con el número

Un número registrado en la Cloud API deja de funcionar en la app de WhatsApp y **también deja de funcionar el
espejo** (que es un dispositivo vinculado de esa app). Se puede probar con el número de prueba de Meta sin tocar
el número real; migrar el número real es una decisión aparte.

Seguridad: la firma se compara en tiempo constante; el cuerpo máximo es 1 MB; un elemento inválido se omite
(se registra el motivo, sin texto del mensaje) sin hacer que Meta reintente toda la entrega.
