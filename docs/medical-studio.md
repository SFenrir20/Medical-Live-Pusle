# MedicalBot, mensajes por etapa y MedicalClic

Acceso: **TOOLS → Automatizaciones**. Las tres tarjetas abren los módulos. La gestión de
automatizaciones requiere `automation:manage` (administrador); los perfiles con
`automation:read` pueden consultar. La biblioteca de respuestas manuales conserva `crm:manage`.

## MedicalBot

El recorrido tiene seis secciones: canales, conversaciones/IA, diseño de flujo, simulador,
activación y mejora. Reutiliza los endpoints existentes de canales, agente, conocimiento,
flujos y pruebas. El editor permite arrastrar, conectar, configurar, nombrar, guardar y probar
nodos; incluye deshacer/rehacer hasta 40 cambios en la sesión de edición.

Solo se muestran nodos ejecutables del catálogo del backend. No se añadió ejecución arbitraria
de código ni envío de email. El agente utiliza la configuración y conocimiento existentes;
un proveedor externo puede requerir credenciales propias. La navegación del asistente no
certifica que los pasos estén completados. La activación de un flujo y la política de un canal
siguen siendo controles separados.

## Mensajes por etapa

`GET/PUT /api/automation/studio/messages` guarda los cuatro mensajes y mantiene un borrador de
flujo por cada uno. Guardar de nuevo actualiza esos mismos flujos y los deja desactivados en el
simulador, incluso si se habían editado o activado. La escritura es transaccional y auditada.

- Bienvenida: disparador de mensaje entrante. No supone detectar automáticamente el primer
  mensaje de una paciente; el flujo puede modificarse antes de activarlo.
- Leads, recordatorio de cita y seguimiento: disparador manual. No existe integración automática
  con citas ni con cambios de etapa para estos presets.
- La espera se cuenta desde el disparador; en las pruebas se omite, como en el motor existente.
- El interruptor incluye u omite el bloque de respuesta en el borrador. No activa envíos reales.
- «Guardar y probar» usa el endpoint existente de prueba de flujos. No envía a un teléfono real.

Los mensajes por etapa son distintos de los atajos manuales de las asesoras. La biblioteca
anterior permanece disponible debajo, en un panel desplegable.

## MedicalClic

`GET/PUT /api/automation/studio/widget` persiste título, descripción, colores, posición y cuentas
de contacto. La validación permite únicamente números E.164 y nombres de cuenta; no acepta URLs
arbitrarias. La edición es solo para administradores y se audita.

El widget es un componente para la **web de la clínica**, no botones interactivos dentro de un
mensaje de WhatsApp. Abre enlaces `wa.me`, Instagram y Messenger, sin necesitar API oficial.
«Copiar y guardar» genera un script independiente que se pega antes de `</body>` en la web.
No contiene claves ni consulta el CRM. Los títulos se insertan como texto y la configuración
se escapa para que no pueda cerrar el bloque script. No duplica el widget al insertarlo dos veces.

El código copiado es una instantánea: para actualizarlo hay que copiar y publicar otra vez.
Si la web usa CSP que bloquea scripts inline, su responsable debe integrarlo como archivo JS
autorizado por esa política; el configurador no cambia la seguridad de la web.

## Despliegue y validación

Incluye la migración aditiva **0019** (`automation_studio_settings`). El contenedor API ejecuta
`alembic upgrade head` al iniciar; reconstruir API y frontend con la configuración normal de
Clerk. No se habilitaron bots ni campañas del espejo real.

Pruebas backend: permisos, cuentas inválidas, persistencia, reutilización de borradores y
ejecución en simulador. Pruebas frontend: URLs, escape de HTML y ejecución autónoma del widget.
La revisión visual local usa datos ficticios y no acredita conectividad con WhatsApp real.
