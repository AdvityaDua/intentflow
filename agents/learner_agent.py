"""
Self-Healing Learner Agent.

When the Action Agent hits a failure (e.g., endpoint changed, UI drifted),
this agent:
1. Checks LearningMemory for previously-healed paths for this context.
2. If found, tries the healed path.
3. If not found, attempts alternative approaches from a pre-defined catalog.
4. Records any successful alternative path back to LearningMemory for future use.

This models the "UI drift detection and self-healing" without requiring
a full browser automation engine — it works at the API/action layer.
"""

import hashlib
import json
import logging
from typing import Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import LearningMemory
from agents.action_agent import _execute_single_action

logger = logging.getLogger(__name__)


class HealResult(BaseModel):
    healed: bool
    healed_path: Optional[dict]
    attempted_alternatives: list
    new_knowledge_created: bool
    summary: str


# ── Alternative action catalog ────────────────────────────────────────────────
# When a primary action fails, try these alternatives in order.

ALTERNATIVE_CATALOG = {
    "POST /iam/reset-password": [
        {"action": "reset_via_ad", "endpoint": "POST /iam/ad-password-reset", "params": {}},
        {"action": "reset_via_sso", "endpoint": "POST /iam/sso-reset", "params": {}},
        {"action": "manual_reset_ticket", "endpoint": "POST /ticket/create", "params": {"category": "password_manual_reset"}},
    ],
    "PUT /iam/unlock": [
        {"action": "unlock_via_ad", "endpoint": "PUT /iam/ad-unlock", "params": {}},
        {"action": "unlock_ticket", "endpoint": "POST /ticket/create", "params": {"category": "account_unlock_manual"}},
    ],
    "POST /billing/refund": [
        {"action": "refund_v2", "endpoint": "POST /billing/v2/refund", "params": {}},
        {"action": "manual_refund_ticket", "endpoint": "POST /ticket/create", "params": {"category": "manual_refund"}},
    ],
}


def _context_hash(intent: str, failed_endpoint: str) -> str:
    return hashlib.sha256(f"{intent}:{failed_endpoint}".encode()).hexdigest()[:16]


async def heal(
    intent: str,
    failed_action: dict,
    context: dict,
    db: Session,
) -> HealResult:
    """
    Attempt self-healing after an action failure.
    """
    failed_endpoint = failed_action.get("endpoint", "")
    ctx_hash = _context_hash(intent, failed_endpoint)

    # 1. Check learning memory for a previously-healed path
    memory = db.query(LearningMemory).filter_by(context_hash=ctx_hash).first()
    if memory and memory.successful_path:
        learned_action = json.loads(memory.successful_path)
        logger.info(f"Learner: found healed path in memory for {failed_endpoint}")
        success, data, error = await _execute_single_action(learned_action, context)
        if success:
            # Update usage count
            memory.usage_count += 1
            db.commit()
            return HealResult(
                healed=True,
                healed_path=learned_action,
                attempted_alternatives=[learned_action],
                new_knowledge_created=False,
                summary=f"Used previously-healed path: {learned_action.get('endpoint')}",
            )
        else:
            # Learned path also failed — mark it and try fresh alternatives
            logger.warning(f"Learner: previously-healed path also failed: {error}")
            memory.successful_path = None
            memory.failure_modes = json.dumps(
                json.loads(memory.failure_modes or "[]") + [{"endpoint": learned_action.get("endpoint"), "error": error}]
            )
            db.commit()

    # 2. Try alternatives from catalog
    alternatives = ALTERNATIVE_CATALOG.get(failed_endpoint, [])
    attempted = []

    for alt_action in alternatives:
        logger.info(f"Learner: trying alternative {alt_action.get('endpoint')}")
        # Merge params from failed action into alternative
        merged = {**alt_action, "params": {**failed_action.get("params", {}), **alt_action.get("params", {})}}
        attempted.append(merged)

        success, data, error = await _execute_single_action(merged, context)
        if success:
            # Save to learning memory
            if memory:
                memory.successful_path = json.dumps(merged)
                memory.usage_count += 1
                db.commit()
            else:
                new_memory = LearningMemory(
                    context_hash=ctx_hash,
                    action_type=intent,
                    successful_path=json.dumps(merged),
                    alternative_paths=json.dumps(attempted),
                    failure_modes=json.dumps([{"endpoint": failed_endpoint, "error": failed_action.get("error")}]),
                    usage_count=1,
                )
                db.add(new_memory)
                db.commit()

            logger.info(f"Learner: self-healed via {merged.get('endpoint')} — saved to memory")
            return HealResult(
                healed=True,
                healed_path=merged,
                attempted_alternatives=attempted,
                new_knowledge_created=True,
                summary=f"Self-healed: original endpoint {failed_endpoint} was unavailable. "
                        f"Successfully used alternative: {merged.get('endpoint')}. "
                        f"Path saved to learning memory for future use.",
            )

    # 3. All alternatives exhausted — escalate
    logger.warning(f"Learner: all alternatives exhausted for {failed_endpoint}")
    return HealResult(
        healed=False,
        healed_path=None,
        attempted_alternatives=attempted,
        new_knowledge_created=False,
        summary=f"Self-healing failed for {failed_endpoint}. "
                f"Tried {len(attempted)} alternatives. Escalation required.",
    )
