import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from .utils import normalize_email


def parse_recipients(raw_input):
    recipients = []
    invalid = 0
    for line in raw_input.splitlines():
        entry = line.strip()
        if not entry:
            continue
        if "," in entry:
            name, email = [part.strip() for part in entry.split(",", 1)]
        else:
            name, email = "", entry
        email = normalize_email(email)
        if "@" not in email:
            invalid += 1
            continue
        recipients.append({"full_name": name, "email": email})
    return recipients, invalid


def render_content(content, recipient, open_pixel_url=None, click_url=None):
    if not content:
        return ""
    rendered = content.replace("{{recipient_name}}", recipient.full_name or "")
    rendered = rendered.replace("{{recipient_email}}", recipient.email or "")
    if open_pixel_url:
        rendered = rendered.replace(
            "{{open_pixel}}",
            f'<img src="{open_pixel_url}" alt="" width="1" height="1" style="display:none;">',
        )
    else:
        rendered = rendered.replace("{{open_pixel}}", "")
    if click_url:
        rendered = rendered.replace("{{click_url}}", click_url)
    else:
        rendered = rendered.replace("{{click_url}}", "")
    return rendered


def build_message(campaign, domain, recipient, open_pixel_url=None, click_url=None):
    subject = campaign.subject or ""
    body_text = render_content(campaign.body_text, recipient, open_pixel_url, click_url)
    body_html = render_content(campaign.body_html, recipient, open_pixel_url, click_url)
    from_name = domain.from_name or domain.display_name or "HexPhish"
    from_email = domain.from_email or f"no-reply@{domain.domain}"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    if recipient.full_name:
        msg["To"] = formataddr((recipient.full_name, recipient.email))
    else:
        msg["To"] = recipient.email
    if body_html and body_text:
        msg.set_content(body_text)
        msg.add_alternative(body_html, subtype="html")
    elif body_html:
        msg.set_content(body_html, subtype="html")
    else:
        msg.set_content(body_text)
    return msg


def open_smtp_server(domain):
    if not domain.smtp_host:
        raise ValueError("Dominio sin host SMTP configurado.")
    if domain.smtp_port:
        port = domain.smtp_port
    elif domain.smtp_use_ssl:
        port = 465
    elif domain.smtp_use_tls:
        port = 587
    else:
        port = 25
    if domain.smtp_use_ssl:
        server = smtplib.SMTP_SSL(domain.smtp_host, port, timeout=10)
    else:
        server = smtplib.SMTP(domain.smtp_host, port, timeout=10)
    server.ehlo()
    if domain.smtp_use_tls and not domain.smtp_use_ssl:
        server.starttls()
        server.ehlo()
    if domain.smtp_username:
        server.login(domain.smtp_username, domain.smtp_password or "")
    return server


def send_message(domain, message):
    server = open_smtp_server(domain)
    try:
        server.send_message(message)
    finally:
        server.quit()


def test_smtp(domain, test_email=None):
    if test_email:
        from_name = domain.from_name or domain.display_name or "HexPhish"
        if domain.from_email:
            from_email = domain.from_email
        elif domain.domain:
            from_email = f"no-reply@{domain.domain}"
        else:
            from_email = "no-reply@localhost"
        msg = EmailMessage()
        msg["Subject"] = "HexPhish SMTP test"
        msg["From"] = formataddr((from_name, from_email))
        msg["To"] = test_email
        msg.set_content("Esta es una prueba de configuracion SMTP para HexPhish.")
        send_message(domain, msg)
        return
    server = open_smtp_server(domain)
    server.quit()
