import os

import click
from flask import Flask, g, session

from .db import bootstrap_db, ensure_default_admin, get_db, init_app as init_db_app, init_db
from .models import User
from .routes import auth as auth_routes
from .routes import campaigns as campaign_routes
from .routes import domains as domain_routes
from .routes import errors as error_routes
from .routes import main as main_routes
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

    os.makedirs(app.instance_path, exist_ok=True)

    init_db_app(app)

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
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
        else:
            g.user = get_db().get(User, user_id)

    main_routes.register(app)
    auth_routes.register(app)
    campaign_routes.register(app)
    domain_routes.register(app)
    user_routes.register(app)
    error_routes.register(app)
    tracking_routes.register(app)

    return app
