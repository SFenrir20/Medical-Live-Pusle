# Integración visual Lovable → Expo

## Origen y destino

- Origen leído, sin modificaciones: `C:\Users\USUARIO\Desktop\livepulse-proyecto`.
- Destino: `apps/mobile` en Medical LivePulse.
- El origen es React 19 + TanStack Start + Tailwind, con autenticación simulada.
- Se adaptaron sus pantallas a React Native y Expo Router; no se copiaron dependencias DOM ni servidor TanStack.

## Implementado

Paleta y tarjetas del diseño, marca con pulso SVG, login validado en español,
mostrar/ocultar contraseña, recordar acceso demo, recuperación explícitamente simulada,
inicio, selección de cuenta e historial pendiente de fuente real. Rutas de jornada e historial
redirigen al login si no hay sesión demo. Cerrar sesión elimina el marcador recordado.

El botón de entrada explica que aún no registra datos: no inventa turnos ni llama a la API
usando credenciales demo. Recuperación no envía correo. AsyncStorage solo contiene el
marcador demo; al implementar tokens reales debe definirse su almacenamiento seguro.

## Confirmado por el usuario

- Usuarios independientes para LivePulse.
- Cuentas: `@medical.cirugias` (id interno medical), `@medical.cirugias2` (id interno medical-2).
- Medical 360: `C:\Users\USUARIO\Desktop\reportes_streamlit`.

## Punto de integración Medical 360

Proyecto revisado en lectura: frontend React en `frontend`, FastAPI en `webapp.py`,
implementación Streamlit también presente. `frontend/src/components/Marketing.tsx`
ya tiene TikTok Live, NPS y Match con BD, pero no una fuente TikTok conectada.
No se modificaron sus datos ni su autenticación. La conexión de métricas sigue pendiente
de endpoints reales y autorización entre servicios. No derivar identidades clínicas de
usuarios o teléfonos de TikTok automáticamente.

## Validación

TypeScript, ESLint, exportación web y alineación de dependencias con SDK 51.
Cinco pruebas automatizadas cubren validación/credenciales, recuerdo demo, recuperación,
protección de rutas y selección de segunda cuenta/cierre de sesión.
Verificación en navegador: login y navegación con cuentas confirmadas.
No se generó APK/IPA ni se validaron dispositivos nativos. Los pendientes de actualización
de Expo y vulnerabilidades del informe previo continúan.

## Para producción

Implementar autenticación independiente, PostgreSQL y turnos transaccionales. Solicitar
nombres/correos y roles de usuarios iniciales, sin contraseñas por chat; establecer mecanismo
de invitación y proveedor de correo. Validar captura real de ambas cuentas en una transmisión.
Confirmar servidor de despliegue y CRM para etapas siguientes.
