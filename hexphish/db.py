import os

from flask import g
from sqlalchemy import create_engine, select
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import generate_password_hash

from .models import Base, User


engine = None
SessionLocal = None


def init_app(app):
    global engine, SessionLocal
    engine = create_engine(
        f"sqlite:///{app.config['DATABASE']}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True))
    app.teardown_appcontext(close_db)


def get_db():
    if "db_session" not in g:
        g.db_session = SessionLocal()
    return g.db_session


def close_db(_error=None):
    db_session = g.pop("db_session", None)
    if db_session is not None:
        db_session.close()
    if SessionLocal is not None:
        SessionLocal.remove()


def init_db():
    Base.metadata.create_all(bind=engine)


def ensure_default_admin():
    db = get_db()
    existing = db.execute(select(User.id).limit(1)).first()
    if existing:
        return
    admin = User(
        username="admin",
        email="admin@hexphish.local",
        password_hash=generate_password_hash("ChangeMe!"),
        is_admin=True,
    )
    db.add(admin)
    db.commit()


def bootstrap_db(app):
    db_path = app.config["DATABASE"]
    first_time = not os.path.exists(db_path)
    init_db()
    if first_time:
        ensure_default_admin()
