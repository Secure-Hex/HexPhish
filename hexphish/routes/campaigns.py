import csv
from datetime import datetime
from io import BytesIO, StringIO
import textwrap
from urllib.parse import quote, urlparse

from flask import abort, flash, make_response, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ..auth import login_required
from ..constants import CAMPAIGN_STATUSES, RECIPIENT_STATUSES
from ..db import get_db
from ..email_utils import build_message, parse_recipients, send_message
from ..models import Campaign, Domain, Recipient


def _format_dt(value):
    return value.strftime("%Y-%m-%d %H:%M") if value else "No"


def _build_kpis(recipients):
    total = len(recipients)
    sent_recipients = [recipient for recipient in recipients if recipient.sent_at]
    sent_count = len(sent_recipients)
    opened_count = sum(1 for recipient in recipients if recipient.opened_at)
    clicked_count = sum(1 for recipient in recipients if recipient.clicked_at)
    open_rate = (opened_count / sent_count) * 100 if sent_count else 0
    click_rate = (clicked_count / sent_count) * 100 if sent_count else 0
    first_sent_at = min((recipient.sent_at for recipient in sent_recipients), default=None)
    last_sent_at = max((recipient.sent_at for recipient in sent_recipients), default=None)
    return {
        "total": total,
        "sent_count": sent_count,
        "opened_count": opened_count,
        "clicked_count": clicked_count,
        "open_rate": open_rate,
        "click_rate": click_rate,
        "first_sent_at": first_sent_at,
        "last_sent_at": last_sent_at,
    }


def _draw_wrapped_text(pdf, text, x, y, max_width, line_height):
    for line in textwrap.wrap(text or "", width=max_width):
        if y < 60:
            pdf.showPage()
            y = letter[1] - 60
        pdf.drawString(x, y, line)
        y -= line_height
    return y


def _generate_pdf_report(campaign, recipients, kpis):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 60
    margin_x = 50

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(margin_x, y, f"Reporte de campana: {campaign.name}")
    y -= 24
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin_x, y, f"Generado: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    y -= 20

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_x, y, "Resumen")
    y -= 16
    pdf.setFont("Helvetica", 10)
    sender = "Sin remitente"
    if campaign.send_domain:
        sender_name = campaign.send_domain.from_name or campaign.send_domain.display_name
        sender_email = campaign.send_domain.from_email or f"no-reply@{campaign.send_domain.domain}"
        sender = f"{sender_name} ({sender_email})"
    summary_lines = [
        f"Cliente: {campaign.client}",
        f"Estado: {campaign.status}",
        f"Dominio: {campaign.send_domain.domain if campaign.send_domain else 'Sin dominio'}",
        f"Remitente: {sender}",
        f"Asunto: {campaign.subject or 'Sin asunto'}",
        f"Landing: {campaign.landing_url or 'Sin landing'}",
        f"Primer envio: {_format_dt(kpis['first_sent_at'])}",
        f"Ultimo envio: {_format_dt(kpis['last_sent_at'])}",
    ]
    for line in summary_lines:
        y = _draw_wrapped_text(pdf, line, margin_x, y, 100, 14)
    y -= 8

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_x, y, "KPIs")
    y -= 16
    pdf.setFont("Helvetica", 10)
    kpi_lines = [
        f"Destinatarios: {kpis['total']}",
        f"Enviados: {kpis['sent_count']}",
        f"Aperturas: {kpis['opened_count']} (Open rate {kpis['open_rate']:.1f}%)",
        f"Clicks: {kpis['clicked_count']} (Click rate {kpis['click_rate']:.1f}%)",
    ]
    for line in kpi_lines:
        y = _draw_wrapped_text(pdf, line, margin_x, y, 100, 14)
    y -= 8

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_x, y, "Correo enviado")
    y -= 16
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin_x, y, "Texto plano:")
    y -= 14
    pdf.setFont("Helvetica", 9)
    y = _draw_wrapped_text(pdf, campaign.body_text or "Sin texto", margin_x, y, 110, 12)
    y -= 6
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin_x, y, "HTML:")
    y -= 14
    pdf.setFont("Helvetica", 9)
    y = _draw_wrapped_text(pdf, campaign.body_html or "Sin HTML", margin_x, y, 110, 12)
    y -= 8

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_x, y, "Destinatarios")
    y -= 16
    pdf.setFont("Courier", 8)
    headers = ["Nombre", "Correo", "Enviado", "Abierto", "Click", "Estado"]
    widths = [18, 28, 16, 16, 16, 10]
    header_line = "".join(h[:w].ljust(w) for h, w in zip(headers, widths))
    pdf.drawString(margin_x, y, header_line)
    y -= 12
    for recipient in recipients:
        row = [
            recipient.full_name or "-",
            recipient.email,
            _format_dt(recipient.sent_at),
            _format_dt(recipient.opened_at),
            _format_dt(recipient.clicked_at),
            recipient.status,
        ]
        line = "".join(str(value)[:w].ljust(w) for value, w in zip(row, widths))
        if y < 60:
            pdf.showPage()
            pdf.setFont("Courier", 8)
            y = height - 60
        pdf.drawString(margin_x, y, line)
        y -= 12

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def register(app):
    @app.route("/campaigns")
    @login_required
    def campaigns():
        campaigns_data = (
            get_db()
            .execute(
                select(Campaign)
                .options(joinedload(Campaign.send_domain))
                .order_by(Campaign.created_at.desc())
            )
            .scalars()
            .all()
        )
        return render_template("campaigns.html", campaigns=campaigns_data)

    @app.route("/campaigns/new", methods=["GET", "POST"])
    @login_required
    def campaign_create():
        db = get_db()
        domains = (
            db.execute(select(Domain).where(Domain.is_active.is_(True)).order_by(Domain.domain))
            .scalars()
            .all()
        )
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            client = request.form.get("client", "").strip()
            description = request.form.get("description", "").strip()
            status = request.form.get("status", "planned")
            landing_url = request.form.get("landing_url", "").strip()
            subject = request.form.get("subject", "").strip()
            body_text = request.form.get("body_text", "").strip()
            body_html = request.form.get("body_html", "").strip()
            send_domain_id = request.form.get("send_domain_id")
            if send_domain_id:
                send_domain_id = int(send_domain_id)
            else:
                send_domain_id = None

            if not name or not client:
                flash("Nombre y cliente son obligatorios.", "error")
            elif status not in CAMPAIGN_STATUSES:
                flash("Estado invalido.", "error")
            else:
                campaign = Campaign(
                    name=name,
                    client=client,
                    description=description,
                    status=status,
                    landing_url=landing_url or None,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    send_domain_id=send_domain_id,
                )
                db.add(campaign)
                db.commit()
                flash("Campana creada.", "success")
                return redirect(url_for("campaigns"))

        return render_template(
            "campaign_form.html",
            domains=domains,
            campaign=None,
            statuses=CAMPAIGN_STATUSES,
        )

    @app.route("/campaigns/<int:campaign_id>")
    @login_required
    def campaign_detail(campaign_id):
        db = get_db()
        campaign = (
            db.execute(
                select(Campaign)
                .options(joinedload(Campaign.send_domain))
                .where(Campaign.id == campaign_id)
            )
            .scalars()
            .first()
        )
        if campaign is None:
            abort(404)
        recipients = (
            db.execute(
                select(Recipient)
                .where(Recipient.campaign_id == campaign_id)
                .order_by(Recipient.created_at.desc())
            )
            .scalars()
            .all()
        )
        stats = {status: 0 for status in RECIPIENT_STATUSES}
        for recipient in recipients:
            if recipient.status in stats:
                stats[recipient.status] += 1
        kpis = _build_kpis(recipients)
        return render_template(
            "campaign_detail.html",
            campaign=campaign,
            recipients=recipients,
            recipient_stats=stats,
            total_recipients=kpis["total"],
            sent_count=kpis["sent_count"],
            opened_count=kpis["opened_count"],
            clicked_count=kpis["clicked_count"],
            open_rate=kpis["open_rate"],
            click_rate=kpis["click_rate"],
        )

    @app.route("/campaigns/<int:campaign_id>/report.pdf")
    @login_required
    def campaign_report_pdf(campaign_id):
        db = get_db()
        campaign = (
            db.execute(
                select(Campaign)
                .options(joinedload(Campaign.send_domain))
                .where(Campaign.id == campaign_id)
            )
            .scalars()
            .first()
        )
        if campaign is None:
            abort(404)
        recipients = (
            db.execute(
                select(Recipient)
                .where(Recipient.campaign_id == campaign_id)
                .order_by(Recipient.created_at.asc())
            )
            .scalars()
            .all()
        )
        kpis = _build_kpis(recipients)
        pdf_bytes = _generate_pdf_report(campaign, recipients, kpis)
        response = make_response(pdf_bytes)
        filename = f"reporte-campana-{campaign.id}.pdf"
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @app.route("/campaigns/<int:campaign_id>/report.csv")
    @login_required
    def campaign_report_csv(campaign_id):
        db = get_db()
        campaign = (
            db.execute(
                select(Campaign)
                .options(joinedload(Campaign.send_domain))
                .where(Campaign.id == campaign_id)
            )
            .scalars()
            .first()
        )
        if campaign is None:
            abort(404)
        recipients = (
            db.execute(
                select(Recipient)
                .where(Recipient.campaign_id == campaign_id)
                .order_by(Recipient.created_at.asc())
            )
            .scalars()
            .all()
        )
        kpis = _build_kpis(recipients)
        output = StringIO()
        writer = csv.writer(output)
        sender = "Sin remitente"
        if campaign.send_domain:
            sender_name = campaign.send_domain.from_name or campaign.send_domain.display_name
            sender_email = campaign.send_domain.from_email or f"no-reply@{campaign.send_domain.domain}"
            sender = f"{sender_name} ({sender_email})"
        writer.writerow(["campana", campaign.name])
        writer.writerow(["cliente", campaign.client])
        writer.writerow(["estado", campaign.status])
        writer.writerow(
            [
                "dominio",
                campaign.send_domain.domain if campaign.send_domain else "Sin dominio",
            ]
        )
        writer.writerow(["remitente", sender])
        writer.writerow(["asunto", campaign.subject or "Sin asunto"])
        writer.writerow(["landing", campaign.landing_url or "Sin landing"])
        writer.writerow(["primer_envio", _format_dt(kpis["first_sent_at"])])
        writer.writerow(["ultimo_envio", _format_dt(kpis["last_sent_at"])])
        writer.writerow([])
        writer.writerow(["kpi_destinatarios", kpis["total"]])
        writer.writerow(["kpi_enviados", kpis["sent_count"]])
        writer.writerow(["kpi_aperturas", kpis["opened_count"]])
        writer.writerow(["kpi_clicks", kpis["clicked_count"]])
        writer.writerow(["kpi_open_rate", f"{kpis['open_rate']:.1f}%"])
        writer.writerow(["kpi_click_rate", f"{kpis['click_rate']:.1f}%"])
        writer.writerow([])
        writer.writerow(["correo_texto", campaign.body_text or "Sin texto"])
        writer.writerow(["correo_html", campaign.body_html or "Sin HTML"])
        writer.writerow([])
        writer.writerow(
            ["nombre", "correo", "enviado", "abierto", "click", "estado", "ultimo_error"]
        )
        for recipient in recipients:
            writer.writerow(
                [
                    recipient.full_name or "-",
                    recipient.email,
                    _format_dt(recipient.sent_at),
                    _format_dt(recipient.opened_at),
                    _format_dt(recipient.clicked_at),
                    recipient.status,
                    recipient.last_error or "",
                ]
            )
        response = make_response(output.getvalue())
        filename = f"reporte-campana-{campaign.id}.csv"
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @app.route("/campaigns/<int:campaign_id>/recipients", methods=["POST"])
    @login_required
    def campaign_add_recipients(campaign_id):
        db = get_db()
        campaign = db.get(Campaign, campaign_id)
        if campaign is None:
            abort(404)
        raw_recipients = request.form.get("recipients_bulk", "").strip()
        if not raw_recipients:
            flash("Ingresa al menos un correo.", "error")
            return redirect(url_for("campaign_detail", campaign_id=campaign_id))
        entries, invalid_count = parse_recipients(raw_recipients)
        if not entries:
            flash("No se encontraron correos validos.", "error")
            return redirect(url_for("campaign_detail", campaign_id=campaign_id))
        existing_emails = {
            email
            for (email,) in db.execute(
                select(Recipient.email).where(Recipient.campaign_id == campaign_id)
            ).all()
        }
        added = 0
        for entry in entries:
            if entry["email"] in existing_emails:
                continue
            db.add(
                Recipient(
                    campaign_id=campaign_id,
                    full_name=entry["full_name"],
                    email=entry["email"],
                    status="pending",
                )
            )
            existing_emails.add(entry["email"])
            added += 1
        db.commit()
        message = f"Destinatarios agregados: {added}."
        if invalid_count:
            message = f"{message} Invalidos: {invalid_count}."
        flash(message, "success")
        return redirect(url_for("campaign_detail", campaign_id=campaign_id))

    @app.route("/campaigns/<int:campaign_id>/recipients/<int:recipient_id>/delete", methods=["POST"])
    @login_required
    def campaign_delete_recipient(campaign_id, recipient_id):
        db = get_db()
        recipient = db.get(Recipient, recipient_id)
        if recipient is None or recipient.campaign_id != campaign_id:
            abort(404)
        db.delete(recipient)
        db.commit()
        flash("Destinatario eliminado.", "success")
        return redirect(url_for("campaign_detail", campaign_id=campaign_id))

    @app.route("/campaigns/<int:campaign_id>/send", methods=["POST"])
    @login_required
    def campaign_send(campaign_id):
        db = get_db()
        campaign = (
            db.execute(
                select(Campaign)
                .options(joinedload(Campaign.send_domain))
                .where(Campaign.id == campaign_id)
            )
            .scalars()
            .first()
        )
        if campaign is None:
            abort(404)
        if campaign.send_domain is None or not campaign.send_domain.is_active:
            flash("Selecciona un dominio activo con SMTP configurado.", "error")
            return redirect(url_for("campaign_detail", campaign_id=campaign_id))
        if not campaign.send_domain.smtp_host:
            flash("Configura el host SMTP del dominio seleccionado.", "error")
            return redirect(url_for("campaign_detail", campaign_id=campaign_id))
        if not campaign.subject or (not campaign.body_text and not campaign.body_html):
            flash("Completa asunto y cuerpo del correo antes de enviar.", "error")
            return redirect(url_for("campaign_detail", campaign_id=campaign_id))
        if campaign.landing_url:
            parsed = urlparse(campaign.landing_url)
            if parsed.scheme not in {"http", "https"}:
                flash("La URL de landing debe incluir http:// o https://.", "error")
                return redirect(url_for("campaign_detail", campaign_id=campaign_id))
        recipients = (
            db.execute(
                select(Recipient)
                .where(Recipient.campaign_id == campaign_id, Recipient.status == "pending")
                .order_by(Recipient.created_at.asc())
            )
            .scalars()
            .all()
        )
        if not recipients:
            flash("No hay destinatarios pendientes.", "error")
            return redirect(url_for("campaign_detail", campaign_id=campaign_id))

        sent_count = 0
        failed_count = 0
        base_url = request.host_url.rstrip("/")
        for recipient in recipients:
            try:
                open_pixel_url = f"{base_url}{url_for('track_open', recipient_id=recipient.id)}"
                click_url = None
                if campaign.landing_url:
                    click_url = (
                        f"{base_url}{url_for('track_click', recipient_id=recipient.id)}"
                        f"?target={quote(campaign.landing_url)}"
                    )
                message = build_message(
                    campaign,
                    campaign.send_domain,
                    recipient,
                    open_pixel_url=open_pixel_url,
                    click_url=click_url,
                )
                send_message(campaign.send_domain, message)
                recipient.status = "sent"
                recipient.sent_at = datetime.utcnow()
                recipient.last_error = None
                sent_count += 1
            except Exception as exc:
                recipient.status = "failed"
                recipient.last_error = str(exc)[:500]
                failed_count += 1
            db.commit()

        if failed_count:
            flash(
                f"Envios completados. Enviados: {sent_count}. Fallidos: {failed_count}.",
                "error",
            )
        else:
            flash(f"Envios completados. Enviados: {sent_count}.", "success")
        return redirect(url_for("campaign_detail", campaign_id=campaign_id))

    @app.route("/campaigns/<int:campaign_id>/edit", methods=["GET", "POST"])
    @login_required
    def campaign_edit(campaign_id):
        db = get_db()
        campaign = db.get(Campaign, campaign_id)
        if campaign is None:
            abort(404)
        domains = db.execute(select(Domain).order_by(Domain.domain)).scalars().all()

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            client = request.form.get("client", "").strip()
            description = request.form.get("description", "").strip()
            status = request.form.get("status", "planned")
            landing_url = request.form.get("landing_url", "").strip()
            subject = request.form.get("subject", "").strip()
            body_text = request.form.get("body_text", "").strip()
            body_html = request.form.get("body_html", "").strip()
            send_domain_id = request.form.get("send_domain_id")
            if send_domain_id:
                send_domain_id = int(send_domain_id)
            else:
                send_domain_id = None

            if not name or not client:
                flash("Nombre y cliente son obligatorios.", "error")
            elif status not in CAMPAIGN_STATUSES:
                flash("Estado invalido.", "error")
            else:
                campaign.name = name
                campaign.client = client
                campaign.description = description
                campaign.status = status
                campaign.landing_url = landing_url or None
                campaign.subject = subject
                campaign.body_text = body_text
                campaign.body_html = body_html
                campaign.send_domain_id = send_domain_id
                db.commit()
                flash("Campana actualizada.", "success")
                return redirect(url_for("campaigns"))

        return render_template(
            "campaign_form.html",
            domains=domains,
            campaign=campaign,
            statuses=CAMPAIGN_STATUSES,
        )

    @app.route("/campaigns/<int:campaign_id>/delete", methods=["POST"])
    @login_required
    def campaign_delete(campaign_id):
        db = get_db()
        campaign = db.get(Campaign, campaign_id)
        if campaign is None:
            abort(404)
        db.delete(campaign)
        db.commit()
        flash("Campana eliminada.", "success")
        return redirect(url_for("campaigns"))
