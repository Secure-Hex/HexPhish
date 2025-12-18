from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Domain(Base):
    __tablename__ = "domains"

    id = Column(Integer, primary_key=True)
    domain = Column(String(255), unique=True, nullable=False)
    display_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    smtp_host = Column(String(255))
    smtp_port = Column(Integer)
    smtp_username = Column(String(255))
    smtp_password = Column(String(255))
    smtp_use_tls = Column(Boolean, nullable=False, default=True)
    smtp_use_ssl = Column(Boolean, nullable=False, default=False)
    from_name = Column(String(255))
    from_email = Column(String(255))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    campaigns = relationship("Campaign", back_populates="send_domain")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    client = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(20), nullable=False)
    landing_url = Column(String(500))
    subject = Column(String(255))
    body_text = Column(Text)
    body_html = Column(Text)
    send_domain_id = Column(Integer, ForeignKey("domains.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    send_domain = relationship("Domain", back_populates="campaigns")
    recipients = relationship("Recipient", back_populates="campaign", cascade="all, delete-orphan")


class Recipient(Base):
    __tablename__ = "recipients"

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    full_name = Column(String(255))
    email = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    opened_at = Column(DateTime)
    clicked_at = Column(DateTime)
    last_ip = Column(String(64))
    last_user_agent = Column(String(500))
    sent_at = Column(DateTime)
    last_error = Column(String(500))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    campaign = relationship("Campaign", back_populates="recipients")


class CsrfToken(Base):
    __tablename__ = "csrf_tokens"

    id = Column(Integer, primary_key=True)
    session_key = Column(String(128), unique=True, nullable=False)
    token = Column(String(128), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
