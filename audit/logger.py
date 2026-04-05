import json
import logging
import time
from typing import Any, Optional

from sqlalchemy.orm import Session

from database import AuditLog

logger = logging.getLogger(__name__)


class TicketAuditLogger:
    """
    Structured, step-by-step audit logger for a single ticket pipeline run.
    Every agent decision is logged with input, output, confidence, and latency.
    """

    def __init__(self, ticket_id: str, db: Session):
        self.ticket_id = ticket_id
        self.db = db
        self._step_timers: dict = {}

    def start_step(self, step: str) -> None:
        self._step_timers[step] = time.time()

    def log(
        self,
        step: str,
        agent: str,
        input_summary: Any,
        output_summary: Any,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
    ) -> None:
        latency_ms = None
        if step in self._step_timers:
            latency_ms = round((time.time() - self._step_timers.pop(step)) * 1000, 2)

        entry = AuditLog(
            ticket_id=self.ticket_id,
            step=step,
            agent=agent,
            input_summary=_serialize(input_summary),
            output_summary=_serialize(output_summary),
            confidence=confidence,
            reasoning=reasoning,
            latency_ms=latency_ms,
        )
        self.db.add(entry)
        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Audit log commit failed: {e}")
            self.db.rollback()

        logger.debug(f"[AUDIT] {self.ticket_id} | {step} | {agent} | {latency_ms}ms")


def _serialize(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj[:4000]   # Cap to avoid DB bloat
    try:
        return json.dumps(obj, default=str)[:4000]
    except Exception:
        return str(obj)[:4000]
