from datetime import datetime

from flask import flash, redirect, render_template, request, url_for

from ..auth import admin_required
from ..db import get_db
from ..internal_email import get_internal_config, test_internal_smtp
from ..models import AppConfig
from ..utils import normalize_email, parse_smtp_port


def register(app):
    @app.route("/settings/email", methods=["GET", "POST"])
    @admin_required
    def email_settings():
        db = get_db()
        config = get_internal_config(db)
        if request.method == "POST":
            smtp_host = request.form.get("smtp_host", "").strip()
            smtp_port = parse_smtp_port(request.form.get("smtp_port", "").strip())
            smtp_username = request.form.get("smtp_username", "").strip()
            smtp_password = request.form.get("smtp_password", "").strip()
            smtp_use_tls = True if request.form.get("smtp_use_tls") == "on" else False
            smtp_use_ssl = True if request.form.get("smtp_use_ssl") == "on" else False
            from_name = request.form.get("from_name", "").strip()
            raw_from_email = request.form.get("from_email", "").strip()
            from_email = normalize_email(raw_from_email) if raw_from_email else ""

            if smtp_use_tls and smtp_use_ssl:
                flash("No actives TLS y SSL al mismo tiempo.", "error")
                return render_template("settings_email.html", config=config, test_email="")

            config.smtp_host = smtp_host or None
            config.smtp_port = smtp_port
            config.smtp_username = smtp_username or None
            if smtp_password:
                config.smtp_password = smtp_password
            config.smtp_use_tls = smtp_use_tls
            config.smtp_use_ssl = smtp_use_ssl
            config.from_name = from_name or None
            config.from_email = from_email or None
            config.updated_at = datetime.utcnow()
            db.commit()
            flash("Configuracion SMTP interna guardada.", "success")
            return redirect(url_for("email_settings"))

        return render_template("settings_email.html", config=config, test_email="")

    @app.route("/settings/email/test", methods=["POST"])
    @admin_required
    def email_settings_test():
        db = get_db()
        config = get_internal_config(db)
        smtp_host = request.form.get("smtp_host", "").strip()
        smtp_port = parse_smtp_port(request.form.get("smtp_port", "").strip())
        smtp_username = request.form.get("smtp_username", "").strip()
        smtp_password = request.form.get("smtp_password", "").strip()
        smtp_use_tls = True if request.form.get("smtp_use_tls") == "on" else False
        smtp_use_ssl = True if request.form.get("smtp_use_ssl") == "on" else False
        from_name = request.form.get("from_name", "").strip()
        raw_from_email = request.form.get("from_email", "").strip()
        from_email = normalize_email(raw_from_email) if raw_from_email else ""
        test_email = request.form.get("test_email", "").strip()

        if not smtp_password:
            smtp_password = config.smtp_password or ""

        temp_config = AppConfig(
            id=1,
            smtp_host=smtp_host or None,
            smtp_port=smtp_port,
            smtp_username=smtp_username or None,
            smtp_password=smtp_password or None,
            smtp_use_tls=smtp_use_tls,
            smtp_use_ssl=smtp_use_ssl,
            from_name=from_name or None,
            from_email=from_email or None,
        )

        if not smtp_host:
            flash("SMTP host es obligatorio para probar.", "error")
            return render_template("settings_email.html", config=temp_config, test_email=test_email)
        if smtp_use_tls and smtp_use_ssl:
            flash("No actives TLS y SSL al mismo tiempo.", "error")
            return render_template("settings_email.html", config=temp_config, test_email=test_email)

        try:
            test_internal_smtp(temp_config, test_email or None)
        except Exception as exc:
            flash(f"Fallo la prueba SMTP: {exc}", "error")
            return render_template("settings_email.html", config=temp_config, test_email=test_email)

        if test_email:
            flash("SMTP correcto. Correo de prueba enviado.", "success")
        else:
            flash("Conexion SMTP correcta.", "success")
        return render_template("settings_email.html", config=temp_config, test_email=test_email)
