import os
import secrets

import click
from flask import Flask, abort, flash, g, redirect, request, session, url_for
from markupsafe import Markup

from .csrf import CSRF_COOKIE_NAME, ensure_csrf_session, get_csrf_token, validate_csrf_token
from .db import bootstrap_db, ensure_default_admin, get_db, init_app as init_db_app, init_db
from .models import User
from .routes import auth as auth_routes
from .routes import campaigns as campaign_routes
from .routes import domains as domain_routes
from .routes import errors as error_routes
from .routes import main as main_routes
from .routes import settings as settings_routes
from .routes import tracking as tracking_routes
from .routes import users as user_routes


def create_app():
    package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    template_dir = os.path.join(package_root, "templates")
    static_dir = os.path.join(package_root, "static")
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config["SECRET_KEY"] = os.environ.get("HEXPHISH_SECRET_KEY", "dev-change-me")
    app.config["DATABASE"] = os.path.join(app.instance_path, "hexphish.db")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["DB_BOOTSTRAPPED"] = False
    app.config["FORCE_HTTPS_HEADERS"] = os.environ.get("HEXPHISH_FORCE_HTTPS_HEADERS") == "1"

    os.makedirs(app.instance_path, exist_ok=True)

    init_db_app(app)

    def csrf_input():
        return Markup(f'<input type="hidden" name="csrf_token" value="{get_csrf_token()}">')

    app.jinja_env.globals["csrf_token"] = get_csrf_token
    app.jinja_env.globals["csrf_input"] = csrf_input

    @app.cli.command("init-db")
    def init_db_command():
        init_db()
        ensure_default_admin()
        click.echo("Base de datos inicializada. Usuario admin: admin / ChangeMe!")

    @app.before_request
    def load_logged_in_user():
        if not app.config["DB_BOOTSTRAPPED"]:
            bootstrap_db(app)
            app.config["DB_BOOTSTRAPPED"] = True
        ensure_csrf_session()
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
        else:
            g.user = get_db().get(User, user_id)

    @app.before_request
    def enforce_session_token():
        if getattr(g, "user", None):
            if not g.user.session_token:
                g.user.session_token = secrets.token_urlsafe(32)
                get_db().commit()
                session["session_token"] = g.user.session_token
                return None
            if session.get("session_token") != g.user.session_token:
                flash("Sesion expirada. Inicia nuevamente.", "error")
                session.clear()
                return redirect(url_for("login"))

    @app.before_request
    def enforce_password_change():
        if getattr(g, "user", None) and g.user.must_change_password:
            allowed_endpoints = {"change_password", "logout", "static"}
            if request.endpoint is None:
                return None
            if request.endpoint.startswith("static"):
                return None
            if request.endpoint not in allowed_endpoints:
                return redirect(url_for("change_password"))

    @app.before_request
    def enforce_active_user():
        if getattr(g, "user", None) and not g.user.is_active:
            flash("Cuenta desactivada.", "error")
            session.pop("user_id", None)
            session.pop("pending_user_id", None)
            return redirect(url_for("login"))

    @app.before_request
    def csrf_protect():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            request_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not validate_csrf_token(request_token):
                abort(400)

    @app.after_request
    def apply_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=(), interest-cohort=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("X-DNS-Prefetch-Control", "off")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "script-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        if request.is_secure or app.config["FORCE_HTTPS_HEADERS"]:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains; preload",
            )
        if getattr(g, "csrf_cookie_needs_set", False):
            response.set_cookie(
                CSRF_COOKIE_NAME,
                g.csrf_session_id,
                httponly=True,
                samesite="Lax",
                secure=bool(request.is_secure or app.config["FORCE_HTTPS_HEADERS"]),
                path="/",
            )
        return response

    main_routes.register(app)
    auth_routes.register(app)
    campaign_routes.register(app)
    domain_routes.register(app)
    user_routes.register(app)
    error_routes.register(app)
    tracking_routes.register(app)
    settings_routes.register(app)

    return app
