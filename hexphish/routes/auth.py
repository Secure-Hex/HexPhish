from flask import flash, redirect, render_template, request, session, url_for
from sqlalchemy import func, or_, select
from werkzeug.security import check_password_hash

from ..db import get_db
from ..models import User


def register(app):
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

            if error is None:
                session.clear()
                session["user_id"] = user.id
                return redirect(url_for("dashboard"))

            flash(error, "error")

        return render_template("login.html", body_class="auth")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))
