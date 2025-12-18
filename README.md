# HexPhish

[![Python](https://img.shields.io/badge/python-3.10%2B-1f6feb?style=flat-square)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-2.x-0f172a?style=flat-square)](https://flask.palletsprojects.com/)
[![SQLAlchemy](https://img.shields.io/badge/sqlalchemy-2.x-bb0000?style=flat-square)](https://www.sqlalchemy.org/)
[![License](https://img.shields.io/badge/license-GPL--3.0-6b7280?style=flat-square)](LICENSE)

HexPhish es una plataforma open source para gestionar campanas de phishing etico de punta a punta. Permite planificar, enviar, medir y reportar simulaciones con control por dominio y trazabilidad por destinatario, todo desde una interfaz profesional.

## Caracteristicas principales

- Gestion completa de campanas con estados, cliente, dominio, contenido y landing.
- Control de dominios con configuracion SMTP, remitente, TLS/SSL y prueba de conexion/envio.
- SMTP interno para notificaciones y recuperacion de cuentas.
- Destinatarios por campana (carga masiva) con tracking individual de envio, apertura y click.
- KPIs automaticos: enviados, aperturas, clicks, open rate y click rate.
- Reportes descargables en PDF y CSV con detalle por destinatario.
- Contenido personalizable con tokens `{{recipient_name}}`, `{{recipient_email}}`, `{{open_pixel}}`, `{{click_url}}`.
- Roles y administracion de usuarios (alta, baja, reset de contrasena).
- Desactivacion/reactivacion de cuentas sin eliminarlas.
- Recuperacion de contrasena por email con enlaces de un solo uso (2 horas).
- Cambio de contrasena obligatorio en el primer acceso del usuario.
- MFA obligatorio para todos los usuarios (correo o TOTP).
- Los usuarios pueden cambiar su metodo MFA desde la plataforma.
- Los administradores pueden reiniciar el MFA de otros usuarios.
- El reinicio de MFA fuerza cambio de contrasena en el siguiente login.
- Al reiniciar MFA se invalida la sesion activa del usuario.
- Perfil de usuario con cambio de correo protegido por contrasena.
- UI moderna y responsive enfocada en operacion diaria.

## Stack

- Python 3.10+ (recomendado)
- Flask
- SQLAlchemy (SQLite por defecto)
- ReportLab (PDF)
- PyOTP (TOTP)
- qrcode (QR para TOTP)

## Instalacion rapida

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Inicializar base de datos

```bash
flask --app app.py init-db
```

Se crea un usuario administrador inicial:
- Usuario: `admin`
- Contrasena: `ChangeMe!`

Claves/valores por defecto:
- `HEXPHISH_SECRET_KEY`: `dev-change-me`
- Base de datos: `instance/hexphish.db`

## Ejecutar la app

```bash
flask --app app.py run
```

## Flujo sugerido

1. Crea un dominio y configura SMTP (puedes probar la conexion o enviar un test).
2. Crea una campana con asunto, cuerpo y landing.
3. Carga destinatarios (uno por linea).
4. Envia correos pendientes desde el detalle de la campana.
5. Revisa KPIs y descarga reportes en PDF/CSV.
6. Configura el SMTP interno para credenciales y recuperacion de contrasenas.
7. En el primer login configura MFA (correo o TOTP).

## Tokens de contenido

Inserta tokens en el cuerpo del correo para personalizacion y tracking:

- `{{recipient_name}}` Nombre del destinatario.
- `{{recipient_email}}` Correo del destinatario.
- `{{open_pixel}}` Pixel de tracking de apertura (solo HTML).
- `{{click_url}}` URL trackeada (redirige a la landing).

## Reportes

Desde el detalle de cada campana puedes descargar:
- PDF con KPIs, contenido enviado y detalle por destinatario.
- CSV con metadatos, KPIs y listado completo.

## Hoja de ruta

- Modo infraestructura: ejecutar el propio HexPhish como stack integrado de SMTP y DNS para laboratorios.
- Adjuntos de prueba con tracking de descarga para validar comportamiento del usuario.

## Seguridad y uso responsable

HexPhish esta pensado para simulaciones de seguridad autorizadas. Usa siempre dominios, listas y permisos aprobados.

## Notas

- La base SQLite se guarda en `instance/hexphish.db`.
- Si cambias el esquema, recrea la base antes de iniciar.
- Para produccion, configura `HEXPHISH_SECRET_KEY` y considera una base externa.
- La creacion de usuarios genera una contrasena aleatoria enviada por correo.
- Sin SMTP interno configurado no se podran enviar credenciales ni enlaces de recuperacion.
- MFA por correo requiere SMTP interno configurado; TOTP no.
- Si un usuario esta desactivado no podra iniciar sesion hasta ser reactivado por un admin.

## Licencia

GPL-3.0. Ver `LICENSE`.
