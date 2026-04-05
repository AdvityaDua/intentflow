"""
IntentFlow — Metrics Router.
Dashboard data: overview stats, breakdowns by intent/priority, SLA compliance, timeline.
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import require_role
from database import Ticket, AuditLog, User, get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get("/overview")
def overview(
    current_user: User = Depends(require_role("admin", "agent")),
    db: Session = Depends(get_db),
):
    """High-level dashboard metrics."""
    total = db.query(func.count(Ticket.id)).scalar() or 0
    resolved = db.query(func.count(Ticket.id)).filter(Ticket.status == "resolved").scalar() or 0
    escalated = db.query(func.count(Ticket.id)).filter(Ticket.status == "escalated").scalar() or 0
    open_count = db.query(func.count(Ticket.id)).filter(Ticket.status.in_(["open", "in_progress"])).scalar() or 0
    avg_conf = db.query(func.avg(Ticket.confidence)).filter(Ticket.confidence.isnot(None)).scalar()
    sla_breached_count = db.query(func.count(Ticket.id)).filter(Ticket.sla_breached == True).scalar() or 0

    # Average resolution time (for resolved tickets)
    resolved_tickets = db.query(Ticket).filter(
        Ticket.status == "resolved",
        Ticket.resolved_at.isnot(None),
    ).all()
    avg_resolution_ms = 0
    if resolved_tickets:
        deltas = [(t.resolved_at - t.created_at).total_seconds() for t in resolved_tickets if t.resolved_at]
        avg_resolution_ms = round(sum(deltas) / len(deltas) * 1000) if deltas else 0

    return {
        "total_tickets": total,
        "resolved": resolved,
        "escalated": escalated,
        "open": open_count,
        "resolution_rate": round(resolved / total * 100, 1) if total > 0 else 0,
        "avg_confidence": round(avg_conf, 1) if avg_conf else 0,
        "avg_resolution_ms": avg_resolution_ms,
        "sla_breaches": sla_breached_count,
        "sla_compliance": round((1 - sla_breached_count / total) * 100, 1) if total > 0 else 100,
    }


@router.get("/by-intent")
def by_intent(
    current_user: User = Depends(require_role("admin", "agent")),
    db: Session = Depends(get_db),
):
    """Ticket counts grouped by intent."""
    rows = (
        db.query(Ticket.intent, func.count(Ticket.id))
        .filter(Ticket.intent.isnot(None))
        .group_by(Ticket.intent)
        .all()
    )
    return [{"intent": r[0], "count": r[1]} for r in rows]


@router.get("/by-priority")
def by_priority(
    current_user: User = Depends(require_role("admin", "agent")),
    db: Session = Depends(get_db),
):
    """Ticket counts grouped by priority."""
    rows = (
        db.query(Ticket.priority, func.count(Ticket.id))
        .filter(Ticket.priority.isnot(None))
        .group_by(Ticket.priority)
        .all()
    )
    return [{"priority": r[0], "count": r[1]} for r in rows]


@router.get("/by-mode")
def by_mode(
    current_user: User = Depends(require_role("admin", "agent")),
    db: Session = Depends(get_db),
):
    """Ticket counts grouped by resolution mode."""
    rows = (
        db.query(Ticket.mode, func.count(Ticket.id))
        .filter(Ticket.mode.isnot(None))
        .group_by(Ticket.mode)
        .all()
    )
    return [{"mode": r[0], "count": r[1]} for r in rows]


@router.get("/sla")
def sla_metrics(
    current_user: User = Depends(require_role("admin", "agent")),
    db: Session = Depends(get_db),
):
    """SLA compliance by priority."""
    priorities = ["Critical", "High", "Medium", "Low"]
    result = []
    for p in priorities:
        total = db.query(func.count(Ticket.id)).filter(Ticket.priority == p).scalar() or 0
        breached = db.query(func.count(Ticket.id)).filter(
            Ticket.priority == p, Ticket.sla_breached == True
        ).scalar() or 0
        result.append({
            "priority": p,
            "total": total,
            "breached": breached,
            "compliance": round((1 - breached / total) * 100, 1) if total > 0 else 100,
        })
    return result


@router.get("/timeline")
def timeline(
    days: int = 30,
    current_user: User = Depends(require_role("admin", "agent")),
    db: Session = Depends(get_db),
):
    """Tickets created per day over the last N days."""
    since = datetime.utcnow() - timedelta(days=days)
    tickets = db.query(Ticket).filter(Ticket.created_at >= since).all()

    by_day = {}
    for t in tickets:
        day = t.created_at.strftime("%Y-%m-%d")
        if day not in by_day:
            by_day[day] = {"date": day, "total": 0, "resolved": 0, "escalated": 0}
        by_day[day]["total"] += 1
        if t.status == "resolved":
            by_day[day]["resolved"] += 1
        elif t.status == "escalated":
            by_day[day]["escalated"] += 1

    return sorted(by_day.values(), key=lambda x: x["date"])


@router.get("/recent-tickets")
def recent_tickets(
    limit: int = 20,
    status: str = None,
    current_user: User = Depends(require_role("admin", "agent")),
    db: Session = Depends(get_db),
):
    """Recent tickets for the dashboard table."""
    query = db.query(Ticket)
    if status:
        query = query.filter_by(status=status)
    tickets = query.order_by(Ticket.created_at.desc()).limit(min(limit, 100)).all()
    return [
        {
            "id": t.id,
            "query": t.original_query[:80],
            "intent": t.intent,
            "priority": t.priority,
            "status": t.status,
            "mode": t.mode,
            "confidence": t.confidence,
            "stress_level": t.stress_level,
            "sla_breached": t.sla_breached,
            "created_at": t.created_at.isoformat(),
            "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
            "from_voice": t.transcribed_from_voice,
        }
        for t in tickets
    ]
