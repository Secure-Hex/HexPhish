import secrets
from datetime import datetime, timedelta

from flask import g, request
from sqlalchemy import select

from .db import get_db
from .models import CsrfToken


CSRF_COOKIE_NAME = "hexphish_csid"
CSRF_TOKEN_TTL = timedelta(hours=12)


def ensure_csrf_session():
    session_id = request.cookies.get(CSRF_COOKIE_NAME)
    if not session_id:
        session_id = secrets.token_urlsafe(24)
        g.csrf_cookie_needs_set = True
    g.csrf_session_id = session_id
    return session_id


def get_csrf_token():
    session_id = getattr(g, "csrf_session_id", None) or ensure_csrf_session()
    db = get_db()
    token_row = (
        db.execute(select(CsrfToken).where(CsrfToken.session_key == session_id))
        .scalars()
        .first()
    )
    now = datetime.utcnow()
    if token_row is None:
        token = secrets.token_urlsafe(32)
        db.add(CsrfToken(session_key=session_id, token=token, created_at=now))
        db.commit()
        return token
    if now - token_row.created_at > CSRF_TOKEN_TTL:
        token_row.token = secrets.token_urlsafe(32)
        token_row.created_at = now
        db.commit()
    return token_row.token


def validate_csrf_token(request_token):
    if not request_token:
        return False
    session_id = getattr(g, "csrf_session_id", None) or ensure_csrf_session()
    db = get_db()
    token_row = db.execute(
        select(CsrfToken.token).where(CsrfToken.session_key == session_id)
    ).first()
    if not token_row:
        return False
    return secrets.compare_digest(token_row[0], request_token)
