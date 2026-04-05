import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database import SessionLocal, Ticket, SLAConfig

logger = logging.getLogger(__name__)

_monitor_running = False


def get_sla_deadline(priority: str, db: Session) -> datetime:
    """Calculate SLA deadline based on priority config."""
    config = db.query(SLAConfig).filter_by(priority=priority).first()
    minutes = config.deadline_minutes if config else 480
    return datetime.utcnow() + timedelta(minutes=minutes)


def get_escalation_threshold(priority: str, db: Session) -> int:
    """Minutes before SLA deadline to trigger escalation warning."""
    config = db.query(SLAConfig).filter_by(priority=priority).first()
    return config.escalation_minutes if config else 60


async def check_sla_breaches() -> dict:
    """
    Check all open tickets for SLA breaches.
    Returns summary of actions taken.
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        open_tickets = (
            db.query(Ticket)
            .filter(Ticket.status.in_(["open", "in_progress"]))
            .filter(Ticket.sla_deadline.isnot(None))
            .all()
        )

        breached = []
        approaching = []

        for ticket in open_tickets:
            if ticket.sla_deadline <= now and not ticket.sla_breached:
                ticket.sla_breached = True
                # Auto-escalate if not already escalated
                if ticket.status != "escalated":
                    ticket.status = "escalated"
                    ticket.escalation_reason = f"SLA breached at {now.isoformat()}"
                    logger.warning(f"SLA BREACH: Ticket {ticket.id} (priority={ticket.priority})")
                breached.append(ticket.id)

            elif ticket.sla_deadline > now:
                mins_remaining = (ticket.sla_deadline - now).total_seconds() / 60
                esc_threshold = get_escalation_threshold(ticket.priority, db)
                if mins_remaining <= esc_threshold:
                    approaching.append({
                        "ticket_id": ticket.id,
                        "priority": ticket.priority,
                        "minutes_remaining": round(mins_remaining, 1),
                    })

        db.commit()
        return {
            "checked": len(open_tickets),
            "breached": len(breached),
            "approaching": approaching,
            "timestamp": now.isoformat(),
        }
    finally:
        db.close()


async def run_sla_monitor(interval_seconds: int = 60):
    """Background loop — runs every `interval_seconds`."""
    global _monitor_running
    _monitor_running = True
    logger.info(f"SLA monitor started (interval: {interval_seconds}s)")
    while _monitor_running:
        try:
            result = await check_sla_breaches()
            if result["breached"] > 0:
                logger.warning(f"SLA Monitor: {result['breached']} breach(es) detected")
            if result["approaching"]:
                logger.info(f"SLA Monitor: {len(result['approaching'])} ticket(s) approaching deadline")
        except Exception as e:
            logger.error(f"SLA monitor error: {e}")
        await asyncio.sleep(interval_seconds)


def stop_sla_monitor():
    global _monitor_running
    _monitor_running = False
