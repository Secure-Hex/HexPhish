from datetime import datetime
from urllib.parse import unquote, urlparse

from flask import abort, make_response, redirect, request

from ..db import get_db
from ..models import Recipient


PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
    b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
    b"\x00\x02\x02D\x01\x00;"
)


def register(app):
    @app.route("/track/open/<int:recipient_id>.gif")
    def track_open(recipient_id):
        db = get_db()
        recipient = db.get(Recipient, recipient_id)
        if recipient:
            if recipient.opened_at is None:
                recipient.opened_at = datetime.utcnow()
            recipient.last_ip = request.remote_addr
            recipient.last_user_agent = (request.user_agent.string or "")[:500]
            db.commit()
        response = make_response(PIXEL_GIF)
        response.headers["Content-Type"] = "image/gif"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

    @app.route("/track/click/<int:recipient_id>")
    def track_click(recipient_id):
        target = request.args.get("target", "")
        if not target:
            abort(400)
        target = unquote(target)
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"}:
            abort(400)

        db = get_db()
        recipient = db.get(Recipient, recipient_id)
        if recipient:
            if recipient.clicked_at is None:
                recipient.clicked_at = datetime.utcnow()
            recipient.last_ip = request.remote_addr
            recipient.last_user_agent = (request.user_agent.string or "")[:500]
            db.commit()
        return redirect(target, code=302)
