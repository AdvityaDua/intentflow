"""
IntentFlow — Database models and engine (SQLAlchemy).
Models: User, Ticket, AuditLog, KnowledgeArticle, LearningMemory, SLAConfig
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text,
    create_engine, event,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _gen_id() -> str:
    return uuid.uuid4().hex[:12]


# ── Models ────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(String(12), primary_key=True, default=_gen_id)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")  # user | agent | admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String(12), primary_key=True, default=_gen_id)
    user_id = Column(String(12), nullable=False, index=True)
    session_id = Column(String(50), nullable=True)
    original_query = Column(Text, nullable=False)
    transcribed_from_voice = Column(Boolean, default=False)

    # Triage
    intent = Column(String(50), nullable=True)
    priority = Column(String(20), nullable=True)
    stress_level = Column(Float, nullable=True)
    confidence = Column(Integer, nullable=True)

    # Pipeline state
    status = Column(String(30), default="open", index=True)  # open | in_progress | resolved | escalated
    mode = Column(String(20), nullable=True)  # AUTO | ASSISTED | ESCALATED | CLARIFICATION

    # Results
    empathy_response = Column(Text, nullable=True)
    resolution_plan = Column(Text, nullable=True)   # JSON string
    resolution_summary = Column(Text, nullable=True)
    actions_executed = Column(Text, nullable=True)   # JSON string
    violations = Column(Text, nullable=True)         # JSON string

    # Escalation
    escalation_reason = Column(Text, nullable=True)
    clarification_prompt = Column(Text, nullable=True)

    # SLA
    sla_deadline = Column(DateTime, nullable=True)
    sla_breached = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(String(12), nullable=False, index=True)
    step = Column(String(50), nullable=False)
    agent = Column(String(50), nullable=False)
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=True)
    latency_ms = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id = Column(String(20), primary_key=True)        # e.g., KB-001
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50), nullable=True)
    tags = Column(String(500), nullable=True)          # comma-separated
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningMemory(Base):
    __tablename__ = "learning_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    context_hash = Column(String(16), nullable=False, unique=True, index=True)
    action_type = Column(String(50), nullable=False)
    successful_path = Column(Text, nullable=True)      # JSON string
    alternative_paths = Column(Text, nullable=True)     # JSON string
    failure_modes = Column(Text, nullable=True)          # JSON string
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SLAConfig(Base):
    __tablename__ = "sla_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    priority = Column(String(20), unique=True, nullable=False)  # Critical | High | Medium | Low
    deadline_minutes = Column(Integer, nullable=False)
    escalation_minutes = Column(Integer, nullable=False)         # When to warn before deadline


# ── Database Helpers ──────────────────────────────────────────────────────────


def get_db():
    """FastAPI dependency — yields a DB session and auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables and seed SLA defaults."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Seed SLA config if empty
        if db.query(SLAConfig).count() == 0:
            defaults = [
                SLAConfig(priority="Critical", deadline_minutes=30, escalation_minutes=10),
                SLAConfig(priority="High", deadline_minutes=120, escalation_minutes=30),
                SLAConfig(priority="Medium", deadline_minutes=480, escalation_minutes=60),
                SLAConfig(priority="Low", deadline_minutes=1440, escalation_minutes=120),
            ]
            db.add_all(defaults)
            db.commit()
    finally:
        db.close()