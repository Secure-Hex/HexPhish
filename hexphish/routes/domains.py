from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select, update

from ..auth import login_required
from ..db import get_db
from ..email_utils import test_smtp
from ..models import Campaign, Domain
from ..utils import normalize_email, parse_smtp_port


def register(app):
    @app.route("/domains")
    @login_required
    def domains():
        domains_data = (
            get_db().execute(select(Domain).order_by(Domain.created_at.desc())).scalars().all()
        )
        return render_template("domains.html", domains=domains_data)

    @app.route("/domains/new", methods=["GET", "POST"])
    @login_required
    def domain_create():
        if request.method == "POST":
            domain_value = request.form.get("domain", "").strip().lower()
            display_name = request.form.get("display_name", "").strip()
            is_active = True if request.form.get("is_active") == "on" else False
            smtp_host = request.form.get("smtp_host", "").strip()
            smtp_port = parse_smtp_port(request.form.get("smtp_port", "").strip())
            smtp_username = request.form.get("smtp_username", "").strip()
            smtp_password = request.form.get("smtp_password", "").strip()
            smtp_use_tls = True if request.form.get("smtp_use_tls") == "on" else False
            smtp_use_ssl = True if request.form.get("smtp_use_ssl") == "on" else False
            from_name = request.form.get("from_name", "").strip()
            raw_from_email = request.form.get("from_email", "").strip()
            from_email = normalize_email(raw_from_email) if raw_from_email else ""

            if not domain_value or not display_name:
                flash("Dominio y nombre visible son obligatorios.", "error")
            else:
                db = get_db()
                exists = (
                    db.execute(select(Domain.id).where(Domain.domain == domain_value)).first()
                    is not None
                )
                if exists:
                    flash("Ese dominio ya existe.", "error")
                else:
                    domain = Domain(
                        domain=domain_value,
                        display_name=display_name,
                        is_active=is_active,
                        smtp_host=smtp_host or None,
                        smtp_port=smtp_port,
                        smtp_username=smtp_username or None,
                        smtp_password=smtp_password or None,
                        smtp_use_tls=smtp_use_tls,
                        smtp_use_ssl=smtp_use_ssl,
                        from_name=from_name or None,
                        from_email=from_email or None,
                    )
                    db.add(domain)
                    db.commit()
                    flash("Dominio agregado.", "success")
                    return redirect(url_for("domains"))

        return render_template("domain_form.html", domain=None)

    @app.route("/domains/test-smtp", methods=["POST"])
    @login_required
    def domain_test_smtp():
        domain_value = request.form.get("domain", "").strip().lower()
        display_name = request.form.get("display_name", "").strip()
        is_active = True if request.form.get("is_active") == "on" else False
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
        domain_id = request.form.get("domain_id")

        existing_domain = None
        if domain_id:
            existing_domain = get_db().get(Domain, int(domain_id))
        if existing_domain and not smtp_password:
            smtp_password = existing_domain.smtp_password or ""

        temp_domain = Domain(
            domain=domain_value,
            display_name=display_name or domain_value or "HexPhish",
            is_active=is_active,
            smtp_host=smtp_host or None,
            smtp_port=smtp_port,
            smtp_username=smtp_username or None,
            smtp_password=smtp_password or None,
            smtp_use_tls=smtp_use_tls,
            smtp_use_ssl=smtp_use_ssl,
            from_name=from_name or None,
            from_email=from_email or None,
        )
        if existing_domain:
            temp_domain.id = existing_domain.id

        if not smtp_host:
            flash("SMTP host es obligatorio para probar.", "error")
            return render_template("domain_form.html", domain=temp_domain, test_email=test_email)
        if smtp_use_tls and smtp_use_ssl:
            flash("No actives TLS y SSL al mismo tiempo.", "error")
            return render_template("domain_form.html", domain=temp_domain, test_email=test_email)

        try:
            test_smtp(temp_domain, test_email or None)
        except Exception as exc:
            flash(f"Fallo la prueba SMTP: {exc}", "error")
            return render_template("domain_form.html", domain=temp_domain, test_email=test_email)

        if test_email:
            flash("SMTP correcto. Correo de prueba enviado.", "success")
        else:
            flash("Conexion SMTP correcta.", "success")
        return render_template("domain_form.html", domain=temp_domain, test_email=test_email)

    @app.route("/domains/<int:domain_id>/edit", methods=["GET", "POST"])
    @login_required
    def domain_edit(domain_id):
        db = get_db()
        domain = db.get(Domain, domain_id)
        if domain is None:
            abort(404)

        if request.method == "POST":
            domain_value = request.form.get("domain", "").strip().lower()
            display_name = request.form.get("display_name", "").strip()
            is_active = True if request.form.get("is_active") == "on" else False
            smtp_host = request.form.get("smtp_host", "").strip()
            smtp_port = parse_smtp_port(request.form.get("smtp_port", "").strip())
            smtp_username = request.form.get("smtp_username", "").strip()
            smtp_password = request.form.get("smtp_password", "").strip()
            smtp_use_tls = True if request.form.get("smtp_use_tls") == "on" else False
            smtp_use_ssl = True if request.form.get("smtp_use_ssl") == "on" else False
            from_name = request.form.get("from_name", "").strip()
            raw_from_email = request.form.get("from_email", "").strip()
            from_email = normalize_email(raw_from_email) if raw_from_email else ""

            if not domain_value or not display_name:
                flash("Dominio y nombre visible son obligatorios.", "error")
            else:
                exists = (
                    db.execute(
                        select(Domain.id).where(
                            Domain.domain == domain_value, Domain.id != domain_id
                        )
                    ).first()
                    is not None
                )
                if exists:
                    flash("Ese dominio ya existe.", "error")
                else:
                    domain.domain = domain_value
                    domain.display_name = display_name
                    domain.is_active = is_active
                    domain.smtp_host = smtp_host or None
                    domain.smtp_port = smtp_port
                    domain.smtp_username = smtp_username or None
                    if smtp_password:
                        domain.smtp_password = smtp_password
                    domain.smtp_use_tls = smtp_use_tls
                    domain.smtp_use_ssl = smtp_use_ssl
                    domain.from_name = from_name or None
                    domain.from_email = from_email or None
                    db.commit()
                    flash("Dominio actualizado.", "success")
                    return redirect(url_for("domains"))

        return render_template("domain_form.html", domain=domain, test_email="")

    @app.route("/domains/<int:domain_id>/delete", methods=["POST"])
    @login_required
    def domain_delete(domain_id):
        db = get_db()
        domain = db.get(Domain, domain_id)
        if domain is None:
            abort(404)
        db.execute(
            update(Campaign).where(Campaign.send_domain_id == domain_id).values(send_domain_id=None)
        )
        db.delete(domain)
        db.commit()
        flash("Dominio eliminado.", "success")
        return redirect(url_for("domains"))
