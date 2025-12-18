import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from .models import AppConfig


def get_internal_config(db):
    config = db.get(AppConfig, 1)
    if config is None:
        config = AppConfig(id=1)
        db.add(config)
        db.commit()
    return config


def internal_config_ready(config):
    return bool(config.smtp_host and (config.from_email or config.smtp_username))


def open_internal_smtp(config):
    if not config.smtp_host:
        raise ValueError("SMTP interno sin host configurado.")
    if config.smtp_port:
        port = config.smtp_port
    elif config.smtp_use_ssl:
        port = 465
    elif config.smtp_use_tls:
        port = 587
    else:
        port = 25
    if config.smtp_use_ssl:
        server = smtplib.SMTP_SSL(config.smtp_host, port, timeout=10)
    else:
        server = smtplib.SMTP(config.smtp_host, port, timeout=10)
    server.ehlo()
    if config.smtp_use_tls and not config.smtp_use_ssl:
        server.starttls()
        server.ehlo()
    if config.smtp_username:
        server.login(config.smtp_username, config.smtp_password or "")
    return server


def send_internal_message(config, message):
    server = open_internal_smtp(config)
    try:
        server.send_message(message)
    finally:
        server.quit()


def test_internal_smtp(config, test_email=None):
    if test_email:
        from_name = config.from_name or "HexPhish"
        from_email = config.from_email or config.smtp_username or "no-reply@localhost"
        msg = EmailMessage()
        msg["Subject"] = "HexPhish SMTP test"
        msg["From"] = formataddr((from_name, from_email))
        msg["To"] = test_email
        msg.set_content("Esta es una prueba de configuracion SMTP interna para HexPhish.")
        send_internal_message(config, msg)
        return
    server = open_internal_smtp(config)
    server.quit()


def send_welcome_email(config, user, password):
    from_name = config.from_name or "HexPhish"
    from_email = config.from_email or config.smtp_username or "no-reply@localhost"
    msg = EmailMessage()
    msg["Subject"] = "Tu acceso inicial a HexPhish"
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = user.email
    msg.set_content(
        "Hola,\n\n"
        "Se ha creado tu cuenta en HexPhish.\n\n"
        f"Usuario: {user.username}\n"
        f"Contrasena inicial: {password}\n\n"
        "Por seguridad, al ingresar deberas cambiar tu contrasena.\n"
    )
    send_internal_message(config, msg)


def send_password_reset_email(config, user, reset_url):
    from_name = config.from_name or "HexPhish"
    from_email = config.from_email or config.smtp_username or "no-reply@localhost"
    msg = EmailMessage()
    msg["Subject"] = "Recuperacion de contrasena HexPhish"
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = user.email
    msg.set_content(
        "Hola,\n\n"
        "Recibimos una solicitud para restablecer tu contrasena.\n"
        "Si fuiste tu, usa el siguiente enlace (valido por 2 horas):\n\n"
        f"{reset_url}\n\n"
        "Si no solicitaste el cambio, puedes ignorar este mensaje.\n"
    )
    send_internal_message(config, msg)


def send_mfa_code(config, user, code):
    from_name = config.from_name or "HexPhish"
    from_email = config.from_email or config.smtp_username or "no-reply@localhost"
    msg = EmailMessage()
    msg["Subject"] = "Codigo de acceso HexPhish"
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = user.email
    msg.set_content(
        "Tu codigo de verificacion es:\n\n"
        f"{code}\n\n"
        "Este codigo expira en 10 minutos.\n"
    )
    send_internal_message(config, msg)
