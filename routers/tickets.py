import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user
from database import Ticket, AuditLog, get_db, User
from orchestration.pipeline import run_pipeline
from memory.session_memory import get_session_history, store_turn

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tickets", tags=["Tickets"])


class TicketRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    from_voice: bool = False


class TicketResponse(BaseModel):
    ticket_id: str
    status: str
    mode: Optional[str]
    intent: Optional[str]
    priority: Optional[str]
    confidence: Optional[int]
    empathy_response: Optional[str]
    resolution_plan: Optional[list]
    resolution_summary: Optional[str]
    clarification_prompt: Optional[str]
    escalation_reason: Optional[str]
    violations: Optional[list]
    stress_level: Optional[float]
    session_id: str
    sla_deadline: Optional[str]


@router.post("", response_model=TicketResponse, status_code=202)
async def create_ticket(
    body: TicketRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    session_id = body.session_id or f"sess-{uuid.uuid4().hex[:10]}"

    # Create ticket record
    ticket = Ticket(
        user_id=current_user.id,
        session_id=session_id,
        original_query=body.query.strip(),
        transcribed_from_voice=body.from_voice,
        status="open",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # Get session history for context
    session_history = get_session_history(session_id)

    # Run pipeline
    ticket = await run_pipeline(ticket, session_history, db)

    # Update session memory
    store_turn(session_id, "user", body.query)
    if ticket.intent:
        store_turn(session_id, "assistant", json.dumps({
            "intent": ticket.intent,
            "mode": ticket.mode,
            "resolution_summary": ticket.resolution_summary or ticket.clarification_prompt or ticket.escalation_reason,
        }))

    return _to_response(ticket, session_id)


@router.get("", response_model=list)
def list_tickets(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Ticket)

    # Regular users only see their own tickets
    if current_user.role == "user":
        query = query.filter_by(user_id=current_user.id)

    if status:
        query = query.filter_by(status=status)

    tickets = (
        query.order_by(Ticket.created_at.desc())
        .offset(offset)
        .limit(min(limit, 200))
        .all()
    )
    return [_ticket_summary(t) for t in tickets]


@router.get("/{ticket_id}")
def get_ticket(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter_by(id=ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if current_user.role == "user" and ticket.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    audit_logs = (
        db.query(AuditLog)
        .filter_by(ticket_id=ticket_id)
        .order_by(AuditLog.timestamp.asc())
        .all()
    )

    return {
        **_ticket_summary(ticket),
        "audit_trail": [_audit_summary(log) for log in audit_logs],
    }


@router.post("/{ticket_id}/resolve")
def resolve_ticket(
    ticket_id: str,
    resolution: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Human agent manually resolves a ticket."""
    if current_user.role not in ("admin", "agent"):
        raise HTTPException(status_code=403, detail="Only agents can manually resolve tickets")

    ticket = db.query(Ticket).filter_by(id=ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = "resolved"
    ticket.resolution_summary = resolution.get("summary", "Resolved by human agent")
    ticket.resolved_at = datetime.utcnow()
    db.commit()
    return {"message": "Ticket resolved", "ticket_id": ticket_id}


def _to_response(ticket: Ticket, session_id: str) -> TicketResponse:
    return TicketResponse(
        ticket_id=ticket.id,
        status=ticket.status,
        mode=ticket.mode,
        intent=ticket.intent,
        priority=ticket.priority,
        confidence=ticket.confidence,
        empathy_response=ticket.empathy_response,
        resolution_plan=json.loads(ticket.resolution_plan) if ticket.resolution_plan else None,
        resolution_summary=ticket.resolution_summary,
        clarification_prompt=ticket.clarification_prompt,
        escalation_reason=ticket.escalation_reason,
        violations=json.loads(ticket.violations) if ticket.violations else None,
        stress_level=ticket.stress_level,
        session_id=session_id,
        sla_deadline=ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
    )


def _ticket_summary(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "query": ticket.original_query[:100],
        "status": ticket.status,
        "mode": ticket.mode,
        "intent": ticket.intent,
        "priority": ticket.priority,
        "confidence": ticket.confidence,
        "stress_level": ticket.stress_level,
        "sla_deadline": ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
        "sla_breached": ticket.sla_breached,
        "created_at": ticket.created_at.isoformat(),
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        "transcribed_from_voice": ticket.transcribed_from_voice,
        "user_id": ticket.user_id,
    }


def _audit_summary(log: AuditLog) -> dict:
    return {
        "step": log.step,
        "agent": log.agent,
        "confidence": log.confidence,
        "reasoning": log.reasoning,
        "latency_ms": log.latency_ms,
        "timestamp": log.timestamp.isoformat(),
    }
