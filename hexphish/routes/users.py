import base64
import io
import secrets
import string

from flask import abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import select
import pyotp
import qrcode
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth import admin_required, login_required
from ..db import get_db
from ..internal_email import get_internal_config, internal_config_ready, send_welcome_email
from ..models import User
from ..utils import normalize_email


def register(app):
    def generate_password(length=14):
        alphabet = string.ascii_letters + string.digits + "!@#$%&*+-_"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @app.route("/users")
    @admin_required
    def users():
        users_data = get_db().execute(select(User).order_by(User.created_at.desc())).scalars().all()
        return render_template("users.html", users=users_data)

    @app.route("/users/new", methods=["GET", "POST"])
    @admin_required
    def user_create():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = normalize_email(request.form.get("email", "").strip())
            is_admin = True if request.form.get("is_admin") == "on" else False

            if not username or not email:
                flash("Usuario y correo son obligatorios.", "error")
            else:
                db = get_db()
                config = get_internal_config(db)
                if not internal_config_ready(config):
                    flash(
                        "Configura el SMTP interno antes de crear usuarios.",
                        "error",
                    )
                    return render_template("user_form.html", user=None)
                exists = (
                    db.execute(
                        select(User.id).where((User.username == username) | (User.email == email))
                    ).first()
                    is not None
                )
                if exists:
                    flash("El usuario o correo ya existe.", "error")
                else:
                    password = generate_password()
                    user = User(
                        username=username,
                        email=email,
                        password_hash=generate_password_hash(password),
                        is_admin=is_admin,
                        must_change_password=True,
                        is_active=True,
                    )
                    db.add(user)
                    db.commit()
                    try:
                        send_welcome_email(config, user, password)
                    except Exception as exc:
                        db.delete(user)
                        db.commit()
                        flash(f"Error al enviar credenciales: {exc}", "error")
                        return render_template("user_form.html", user=None)
                    flash("Usuario creado y credenciales enviadas.", "success")
                    return redirect(url_for("users"))

        return render_template("user_form.html", user=None)

    @app.route("/users/<int:user_id>/reset", methods=["GET", "POST"])
    @admin_required
    def user_reset(user_id):
        db = get_db()
        user = db.get(User, user_id)
        if user is None:
            abort(404)

        if request.method == "POST":
            new_password = request.form.get("password", "")
            if not new_password:
                flash("La nueva contrasena es obligatoria.", "error")
            else:
                user.password_hash = generate_password_hash(new_password)
                user.must_change_password = True
                db.commit()
                flash("Contrasena restablecida.", "success")
                return redirect(url_for("users"))

        return render_template("reset_password.html", user=user)

    @app.route("/users/<int:user_id>/delete", methods=["POST"])
    @admin_required
    def user_delete(user_id):
        if g.user and g.user.id == user_id:
            flash("No puedes eliminar tu propia cuenta.", "error")
            return redirect(url_for("users"))

        db = get_db()
        user = db.get(User, user_id)
        if user is None:
            abort(404)
        if user.is_active:
            user.is_active = False
            flash("Usuario desactivado.", "success")
        else:
            user.is_active = True
            flash("Usuario reactivado.", "success")
        db.commit()
        return redirect(url_for("users"))

    @app.route("/account/password", methods=["GET", "POST"])
    @login_required
    def change_password():
        if request.method == "POST":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("password", "")
            confirm_password = request.form.get("password_confirm", "")

            if not new_password:
                flash("La nueva contrasena es obligatoria.", "error")
            elif new_password != confirm_password:
                flash("Las contrasenas no coinciden.", "error")
            elif not check_password_hash(g.user.password_hash, current_password):
                flash("Contrasena actual incorrecta.", "error")
            else:
                db = get_db()
                user = db.get(User, g.user.id)
                if user is None:
                    abort(404)
                user.password_hash = generate_password_hash(new_password)
                user.must_change_password = False
                db.commit()
                flash("Contrasena actualizada.", "success")
                return redirect(url_for("dashboard"))

        return render_template("change_password.html", must_change_password=g.user.must_change_password)

    @app.route("/account/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        db = get_db()
        user = db.get(User, g.user.id)
        if user is None:
            abort(404)

        if request.method == "POST":
            new_email = normalize_email(request.form.get("email", "").strip())
            current_password = request.form.get("current_password", "")
            if not new_email:
                flash("El correo es obligatorio.", "error")
            elif not check_password_hash(user.password_hash, current_password):
                flash("Contrasena actual incorrecta.", "error")
            else:
                exists = (
                    db.execute(
                        select(User.id).where(User.email == new_email, User.id != user.id)
                    ).first()
                    is not None
                )
                if exists:
                    flash("Ese correo ya esta en uso.", "error")
                else:
                    user.email = new_email
                    db.commit()
                    flash("Correo actualizado.", "success")
                    return redirect(url_for("profile"))

        return render_template("profile.html", user=user)

    @app.route("/account/mfa", methods=["GET", "POST"])
    @login_required
    def change_mfa():
        db = get_db()
        user = db.get(User, g.user.id)
        if user is None:
            abort(404)

        totp_setup = user.mfa_method == "totp" and not user.mfa_enabled
        qr_code = None
        otpauth_url = None

        if request.method == "POST":
            current_password = request.form.get("current_password", "")
            method = request.form.get("mfa_method")
            rotate_totp = request.form.get("rotate_totp") == "on"
            code_input = request.form.get("code", "").strip()

            if not check_password_hash(user.password_hash, current_password):
                flash("Contrasena actual incorrecta.", "error")
            elif method == "email":
                config = get_internal_config(db)
                if not internal_config_ready(config):
                    flash("Configura el SMTP interno para usar MFA por correo.", "error")
                else:
                    user.mfa_method = "email"
                    user.mfa_secret = None
                    user.mfa_enabled = True
                    db.commit()
                    flash("MFA por correo activado.", "success")
                    return redirect(url_for("change_mfa"))
            elif method == "totp":
                if user.mfa_method != "totp" or rotate_totp or not user.mfa_secret:
                    user.mfa_secret = pyotp.random_base32()
                    user.mfa_enabled = False
                user.mfa_method = "totp"
                db.commit()
                totp_setup = not user.mfa_enabled
                if code_input:
                    totp = pyotp.TOTP(user.mfa_secret or "")
                    if not totp.verify(code_input, valid_window=1):
                        flash("Codigo incorrecto.", "error")
                    else:
                        user.mfa_enabled = True
                        db.commit()
                        flash("MFA TOTP activado.", "success")
                        return redirect(url_for("change_mfa"))
                elif user.mfa_enabled and not rotate_totp:
                    flash("MFA TOTP ya configurado.", "success")
            else:
                flash("Selecciona un metodo MFA.", "error")

        if totp_setup and user.mfa_secret:
            otpauth_url = pyotp.TOTP(user.mfa_secret).provisioning_uri(
                name=user.email,
                issuer_name="HexPhish",
            )
            qr = qrcode.QRCode(box_size=6, border=2)
            qr.add_data(otpauth_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            qr_code = base64.b64encode(buffer.getvalue()).decode("ascii")

        return render_template(
            "change_mfa.html",
            user=user,
            totp_setup=totp_setup,
            qr_code=qr_code,
            otpauth_url=otpauth_url,
        )

    @app.route("/users/<int:user_id>/mfa-reset", methods=["POST"])
    @admin_required
    def user_reset_mfa(user_id):
        db = get_db()
        user = db.get(User, user_id)
        if user is None:
            abort(404)
        user.mfa_method = None
        user.mfa_secret = None
        user.mfa_enabled = False
        user.must_change_password = True
        user.session_token = secrets.token_urlsafe(32)
        db.commit()
        flash(
            "MFA reiniciado. El usuario debe configurarlo de nuevo y cambiar su contrasena.",
            "success",
        )
        return redirect(url_for("users"))
