"""
IntentFlow — Admin Router.
Management endpoints for users, SLA config, and knowledge base.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_role
from database import User, SLAConfig, KnowledgeArticle, get_db
from rag.retriever import index as rag_index

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Users ─────────────────────────────────────────────────────────────────────


@router.get("/users")
def list_users(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    users = db.query(User).offset(offset).limit(min(limit, 200)).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


class RoleUpdate(BaseModel):
    role: str


@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: str,
    body: RoleUpdate,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    if body.role not in ("user", "agent", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role. Must be: user, agent, or admin")

    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = body.role
    db.commit()
    return {"message": f"User {user_id} role updated to {body.role}"}


@router.put("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: str,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    user.is_active = False
    db.commit()
    return {"message": f"User {user_id} deactivated"}


@router.put("/users/{user_id}/activate")
def activate_user(
    user_id: str,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = True
    db.commit()
    return {"message": f"User {user_id} activated"}


# ── SLA Config ────────────────────────────────────────────────────────────────


@router.get("/sla-config")
def get_sla_config(
    current_user: User = Depends(require_role("admin", "agent")),
    db: Session = Depends(get_db),
):
    configs = db.query(SLAConfig).all()
    return [
        {
            "id": c.id,
            "priority": c.priority,
            "deadline_minutes": c.deadline_minutes,
            "escalation_minutes": c.escalation_minutes,
        }
        for c in configs
    ]


class SLAUpdate(BaseModel):
    deadline_minutes: int
    escalation_minutes: int


@router.put("/sla-config/{priority}")
def update_sla_config(
    priority: str,
    body: SLAUpdate,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    config = db.query(SLAConfig).filter_by(priority=priority).first()
    if not config:
        raise HTTPException(status_code=404, detail=f"SLA config for priority '{priority}' not found")

    if body.deadline_minutes < 1:
        raise HTTPException(status_code=400, detail="Deadline must be at least 1 minute")
    if body.escalation_minutes >= body.deadline_minutes:
        raise HTTPException(status_code=400, detail="Escalation must be less than deadline")

    config.deadline_minutes = body.deadline_minutes
    config.escalation_minutes = body.escalation_minutes
    db.commit()
    return {"message": f"SLA config for '{priority}' updated"}


# ── Knowledge Base ────────────────────────────────────────────────────────────


@router.get("/knowledge")
def list_knowledge(
    current_user: User = Depends(require_role("admin", "agent")),
    db: Session = Depends(get_db),
):
    articles = db.query(KnowledgeArticle).all()
    return [
        {
            "id": a.id,
            "title": a.title,
            "category": a.category,
            "tags": a.tags,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in articles
    ]


class KBArticleCreate(BaseModel):
    id: str
    title: str
    content: str
    category: Optional[str] = None
    tags: Optional[str] = None


@router.post("/knowledge")
def add_knowledge_article(
    body: KBArticleCreate,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    existing = db.query(KnowledgeArticle).filter_by(id=body.id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Article {body.id} already exists")

    article = KnowledgeArticle(
        id=body.id,
        title=body.title,
        content=body.content,
        category=body.category,
        tags=body.tags,
    )
    db.add(article)
    db.commit()

    # Auto-index in ChromaDB
    rag_index(
        body.id,
        f"{body.title}\n\n{body.content}",
        {"title": body.title, "category": body.category or "", "tags": body.tags or ""},
    )

    return {"message": f"Article {body.id} added and indexed", "id": body.id}
