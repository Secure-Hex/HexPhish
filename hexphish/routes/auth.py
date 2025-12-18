import base64
import hashlib
import io
import secrets
from datetime import datetime, timedelta

import pyotp
import qrcode
from flask import flash, redirect, render_template, request, session, url_for
from sqlalchemy import func, or_, select, update
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db
from ..internal_email import (
    get_internal_config,
    internal_config_ready,
    send_mfa_code,
    send_password_reset_email,
)
from ..models import MfaChallenge, PasswordResetToken, User
from ..utils import normalize_email


def register(app):
    def get_pending_user():
        user_id = session.get("pending_user_id")
        if not user_id:
            return None
        return get_db().get(User, user_id)

    def complete_login(user):
        db = get_db()
        if not user.session_token:
            user.session_token = secrets.token_urlsafe(32)
            db.commit()
        session.pop("pending_user_id", None)
        session["user_id"] = user.id
        session["session_token"] = user.session_token

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            identifier = request.form.get("identifier", "").strip().lower()
            password = request.form.get("password", "")
            error = None
            if not identifier or not password:
                error = "Completa usuario/correo y contrasena."
            else:
                user = (
                    get_db()
                    .execute(
                        select(User).where(
                            or_(
                                func.lower(User.username) == identifier,
                                func.lower(User.email) == identifier,
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                if user is None or not check_password_hash(user.password_hash, password):
                    error = "Credenciales invalidas."
                elif not user.is_active:
                    error = "Cuenta desactivada."

            if error is None:
                session.clear()
                session["pending_user_id"] = user.id
                if not user.mfa_method:
                    return redirect(url_for("mfa_setup"))
                return redirect(url_for("mfa_verify"))

            flash(error, "error")

        return render_template("login.html", body_class="auth")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/mfa/setup", methods=["GET", "POST"])
    def mfa_setup():
        pending_user = get_pending_user()
        if not pending_user:
            return redirect(url_for("login"))

        if request.method == "POST":
            method = request.form.get("mfa_method")
            db = get_db()
            user = db.get(User, pending_user.id)
            if method == "email":
                config = get_internal_config(db)
                if not internal_config_ready(config):
                    flash("Configura el SMTP interno para usar MFA por correo.", "error")
                    return render_template("mfa_setup.html", user=pending_user, body_class="auth")
                user.mfa_method = "email"
                user.mfa_enabled = True
                user.mfa_secret = None
                db.commit()
                return redirect(url_for("mfa_verify"))
            if method == "totp":
                if not user.mfa_secret:
                    user.mfa_secret = pyotp.random_base32()
                user.mfa_method = "totp"
                user.mfa_enabled = False
                db.commit()
                return redirect(url_for("mfa_verify"))

            flash("Selecciona un metodo de MFA.", "error")

        return render_template("mfa_setup.html", user=pending_user, body_class="auth")

    @app.route("/mfa/verify", methods=["GET", "POST"])
    def mfa_verify():
        pending_user = get_pending_user()
        if not pending_user:
            return redirect(url_for("login"))

        db = get_db()
        user = db.get(User, pending_user.id)
        if user is None or not user.mfa_method:
            return redirect(url_for("mfa_setup"))

        now = datetime.utcnow()
        if user.mfa_method == "email":
            config = get_internal_config(db)
            if not internal_config_ready(config):
                flash("Configura el SMTP interno para usar MFA por correo.", "error")
                return redirect(url_for("mfa_setup"))
            active_challenge = (
                db.execute(
                    select(MfaChallenge)
                    .where(
                        MfaChallenge.user_id == user.id,
                        MfaChallenge.used_at.is_(None),
                        MfaChallenge.expires_at > now,
                    )
                    .order_by(MfaChallenge.created_at.desc())
                )
                .scalars()
                .first()
            )
            if active_challenge is None:
                code = f"{secrets.randbelow(1000000):06d}"
                token_hash = hashlib.sha256(code.encode()).hexdigest()
                challenge = MfaChallenge(
                    user_id=user.id,
                    code_hash=token_hash,
                    expires_at=now + timedelta(minutes=10),
                )
                db.add(challenge)
                db.commit()
                try:
                    send_mfa_code(config, user, code)
                except Exception:
                    flash("No se pudo enviar el codigo MFA.", "error")
            if request.method == "POST":
                code_input = request.form.get("code", "").strip()
                if not active_challenge:
                    active_challenge = (
                        db.execute(
                            select(MfaChallenge)
                            .where(
                                MfaChallenge.user_id == user.id,
                                MfaChallenge.used_at.is_(None),
                                MfaChallenge.expires_at > now,
                            )
                            .order_by(MfaChallenge.created_at.desc())
                        )
                        .scalars()
                        .first()
                    )
                if not active_challenge:
                    flash("Codigo expirado. Solicita uno nuevo.", "error")
                else:
                    input_hash = hashlib.sha256(code_input.encode()).hexdigest()
                    if input_hash != active_challenge.code_hash:
                        flash("Codigo incorrecto.", "error")
                    else:
                        active_challenge.used_at = now
                        if not user.mfa_enabled:
                            user.mfa_enabled = True
                        db.commit()
                        complete_login(user)
                        return redirect(url_for("dashboard"))

            return render_template("mfa_verify.html", method="email", user=user, body_class="auth")

        if user.mfa_method == "totp":
            if request.method == "POST":
                code_input = request.form.get("code", "").strip()
                totp = pyotp.TOTP(user.mfa_secret or "")
                if not totp.verify(code_input, valid_window=1):
                    flash("Codigo incorrecto.", "error")
                else:
                    if not user.mfa_enabled:
                        user.mfa_enabled = True
                        db.commit()
                    complete_login(user)
                    return redirect(url_for("dashboard"))

            otpauth_url = None
            qr_code = None
            if user.mfa_secret:
                otpauth_url = pyotp.TOTP(user.mfa_secret).provisioning_uri(
                    name=user.email,
                    issuer_name="HexPhish",
                )
                if not user.mfa_enabled:
                    qr = qrcode.QRCode(box_size=6, border=2)
                    qr.add_data(otpauth_url)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG")
                    qr_code = base64.b64encode(buffer.getvalue()).decode("ascii")
            return render_template(
                "mfa_verify.html",
                method="totp",
                user=user,
                otpauth_url=otpauth_url,
                show_secret=not user.mfa_enabled,
                qr_code=qr_code,
                body_class="auth",
            )

        flash("Metodo MFA no valido.", "error")
        return redirect(url_for("mfa_setup"))

    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        if request.method == "POST":
            raw_email = request.form.get("email", "").strip()
            email = normalize_email(raw_email) if raw_email else ""
            if email:
                db = get_db()
                user = (
                    db.execute(select(User).where(func.lower(User.email) == email))
                    .scalars()
                    .first()
                )
                if user and user.is_active:
                    config = get_internal_config(db)
                    if internal_config_ready(config):
                        now = datetime.utcnow()
                        db.execute(
                            update(PasswordResetToken)
                            .where(
                                PasswordResetToken.user_id == user.id,
                                PasswordResetToken.used_at.is_(None),
                            )
                            .values(used_at=now)
                        )
                        raw_token = secrets.token_urlsafe(32)
                        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
                        reset_token = PasswordResetToken(
                            user_id=user.id,
                            token_hash=token_hash,
                            expires_at=now + timedelta(hours=2),
                        )
                        db.add(reset_token)
                        db.commit()
                        reset_url = url_for(
                            "reset_password", token=raw_token, _external=True
                        )
                        try:
                            send_password_reset_email(config, user, reset_url)
                        except Exception:
                            pass
            flash(
                "Si el correo existe, recibiras un enlace para restablecer la contrasena.",
                "success",
            )
            return redirect(url_for("login"))

        return render_template("forgot_password.html", body_class="auth")

    @app.route("/reset-password/<token>", methods=["GET", "POST"])
    def reset_password(token):
        db = get_db()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        reset_token = (
            db.execute(
                select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
            )
            .scalars()
            .first()
        )
        now = datetime.utcnow()
        if (
            reset_token is None
            or reset_token.used_at is not None
            or reset_token.expires_at < now
        ):
            flash("El enlace es invalido o expiro.", "error")
            return redirect(url_for("login"))

        if request.method == "POST":
            new_password = request.form.get("password", "")
            if not new_password:
                flash("La contrasena es obligatoria.", "error")
            else:
                user = db.get(User, reset_token.user_id)
                if user is None:
                    flash("El enlace es invalido o expiro.", "error")
                    return redirect(url_for("login"))
                user.password_hash = generate_password_hash(new_password)
                user.must_change_password = False
                reset_token.used_at = now
                db.commit()
                flash("Contrasena actualizada. Ya puedes ingresar.", "success")
                return redirect(url_for("login"))

        return render_template("reset_password_public.html", body_class="auth")
