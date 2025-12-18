from flask import abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from ..auth import admin_required
from ..db import get_db
from ..models import User
from ..utils import normalize_email


def register(app):
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
            password = request.form.get("password", "")
            is_admin = True if request.form.get("is_admin") == "on" else False

            if not username or not email or not password:
                flash("Usuario, correo y contrasena son obligatorios.", "error")
            else:
                db = get_db()
                exists = (
                    db.execute(
                        select(User.id).where((User.username == username) | (User.email == email))
                    ).first()
                    is not None
                )
                if exists:
                    flash("El usuario o correo ya existe.", "error")
                else:
                    user = User(
                        username=username,
                        email=email,
                        password_hash=generate_password_hash(password),
                        is_admin=is_admin,
                    )
                    db.add(user)
                    db.commit()
                    flash("Usuario creado.", "success")
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
        db.delete(user)
        db.commit()
        flash("Usuario eliminado.", "success")
        return redirect(url_for("users"))
