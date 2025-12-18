from flask import g, redirect, render_template, url_for
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from ..auth import login_required
from ..db import get_db
from ..models import Campaign, Domain, User


def register(app):
    @app.route("/")
    def index():
        if g.user:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        db = get_db()
        stats = {
            "campaigns": db.scalar(select(func.count()).select_from(Campaign)) or 0,
            "domains": db.scalar(
                select(func.count()).select_from(Domain).where(Domain.is_active.is_(True))
            )
            or 0,
            "users": db.scalar(select(func.count()).select_from(User)) or 0,
        }
        latest_campaigns = (
            db.execute(
                select(Campaign)
                .options(joinedload(Campaign.send_domain))
                .order_by(Campaign.created_at.desc())
                .limit(5)
            )
            .scalars()
            .all()
        )
        return render_template("dashboard.html", stats=stats, latest_campaigns=latest_campaigns)
