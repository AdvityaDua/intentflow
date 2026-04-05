"""
Main orchestration pipeline for IntentFlow v2.
Wires all agents together in the correct sequence:
  Triage → Empathy → Knowledge (RAG) → Judge → Action → Learner
"""

import asyncio
import logging
import time
from typing import Optional

from sqlalchemy.orm import Session

from config import get_settings
from database import Ticket
from audit.logger import TicketAuditLogger
from sla.monitor import get_sla_deadline
from agents.router_agent import triage, TriageResult
from agents.empathy_engine import generate_empathy_response
from agents.knowledge_agent import retrieve_and_plan
from agents.judge_agent import audit
from agents.action_agent import execute_plan
from agents.learner_agent import heal

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_pipeline(
    ticket: Ticket,
    session_history: str,
    db: Session,
) -> Ticket:
    """
    Execute the full IntentFlow pipeline for a ticket.
    Updates the ticket in-place and returns it.
    """
    auditor = TicketAuditLogger(ticket.id, db)
    t_start = time.time()

    try:
        # ── PHASE 1: TRIAGE ────────────────────────────────────────────────────
        auditor.start_step("triage")
        triage_result = await triage(ticket.original_query, session_history)

        ticket.intent = triage_result.intent
        ticket.priority = triage_result.priority
        ticket.stress_level = triage_result.stress_level

        # Update SLA deadline now that we know priority
        ticket.sla_deadline = get_sla_deadline(triage_result.priority, db)

        auditor.log(
            "triage", "RouterAgent",
            {"query": ticket.original_query},
            {"intent": triage_result.intent, "priority": triage_result.priority, "stress": triage_result.stress_level},
            confidence=triage_result.confidence,
            reasoning=f"Intent: {triage_result.intent}, Priority: {triage_result.priority}",
        )

        # Needs clarification?
        if triage_result.needs_clarification:
            ticket.status = "open"
            ticket.mode = "CLARIFICATION"
            ticket.clarification_prompt = triage_result.clarification_question
            db.commit()
            return ticket

        # ── PHASE 2: EMPATHY RESPONSE ──────────────────────────────────────────
        auditor.start_step("empathy")
        empathy = await generate_empathy_response(
            ticket.original_query,
            triage_result.intent,
            triage_result.priority,
            triage_result.stress_level,
        )
        ticket.empathy_response = empathy.full_response
        auditor.log(
            "empathy", "EmpathyEngine",
            {"stress_level": triage_result.stress_level},
            {"response": empathy.full_response},
        )

        # ── PHASE 3: KNOWLEDGE RETRIEVAL + PLAN ───────────────────────────────
        auditor.start_step("knowledge")
        plan = await retrieve_and_plan(
            intent=triage_result.intent,
            entities=triage_result.entities,
            priority=triage_result.priority,
            original_query=ticket.original_query,
            session_history=session_history,
            db=db,
        )

        import json
        ticket.resolution_plan = json.dumps(plan.steps)

        auditor.log(
            "knowledge", "KnowledgeAgent",
            {"intent": triage_result.intent, "entities": triage_result.entities},
            {"steps": plan.steps, "sources": plan.sources, "risk": plan.risk_level},
            reasoning=plan.reasoning,
        )

        # Plan returned clarification needed?
        if plan.fallback_triggered or plan.clarification_needed:
            ticket.status = "open"
            ticket.mode = "CLARIFICATION"
            ticket.clarification_prompt = plan.clarification_needed or "Could you provide more details?"
            db.commit()
            return ticket

        # ── PHASE 4: JUDGE AGENT (Safety + Confidence) ────────────────────────
        auditor.start_step("judge")
        judge_result = await audit(
            query=ticket.original_query,
            intent=triage_result.intent,
            entities=triage_result.entities,
            plan_steps=plan.steps,
            api_actions=plan.api_actions,
            reasoning=plan.reasoning,
            sources=plan.sources,
            triage_confidence=triage_result.confidence,
            risk_level=plan.risk_level,
        )

        ticket.confidence = judge_result.confidence
        ticket.violations = json.dumps(judge_result.violations)

        auditor.log(
            "judge", "JudgeAgent",
            {"plan_steps": plan.steps},
            {
                "confidence": judge_result.confidence,
                "violations": judge_result.violations,
                "alignment": judge_result.alignment_score,
            },
            confidence=judge_result.confidence / 100,
            reasoning=judge_result.recommendation,
        )

        # ── PHASE 5: DECIDE MODE ───────────────────────────────────────────────
        mode = _decide_mode(judge_result, triage_result, plan)
        ticket.mode = mode

        if mode == "ESCALATED":
            ticket.status = "escalated"
            ticket.escalation_reason = (
                judge_result.recommendation
                + (f"\nDiagnostic: {judge_result.diagnostic}" if judge_result.diagnostic else "")
            )
            db.commit()
            auditor.log(
                "decision", "DecisionEngine",
                {"confidence": judge_result.confidence, "violations": judge_result.violations},
                {"mode": "ESCALATED"},
                reasoning="Escalated due to low confidence or policy violation",
            )
            return ticket

        if mode == "ASSISTED":
            ticket.status = "escalated"  # Requires human review
            ticket.escalation_reason = f"Confidence {judge_result.confidence}% — human review required before execution."
            db.commit()
            auditor.log(
                "decision", "DecisionEngine",
                {"confidence": judge_result.confidence},
                {"mode": "ASSISTED"},
                confidence=judge_result.confidence / 100,
            )
            return ticket

        # ── PHASE 6: AUTONOMOUS EXECUTION (AUTO mode only) ────────────────────
        if mode == "AUTO":
            auditor.start_step("execution")
            ticket.status = "in_progress"
            db.commit()

            action_result = await execute_plan(
                actions=judge_result.safe_actions,
                context={**triage_result.entities, "user_id": ticket.user_id},
            )

            ticket.actions_executed = json.dumps(
                [a.get("action", "?") for a in action_result.executed_actions]
            )

            # ── PHASE 7: SELF-HEALING (if action failed) ──────────────────────
            if not action_result.success and action_result.needs_self_healing:
                auditor.log(
                    "execution", "ActionAgent",
                    {"actions": judge_result.safe_actions},
                    {"success": False, "failed_at": action_result.failed_action},
                    reasoning=action_result.failure_reason,
                )
                auditor.start_step("self_healing")

                heal_result = await heal(
                    intent=triage_result.intent,
                    failed_action=action_result.failed_action,
                    context={**triage_result.entities, "user_id": ticket.user_id},
                    db=db,
                )

                auditor.log(
                    "self_healing", "LearnerAgent",
                    {"failed_endpoint": action_result.failed_action.get("endpoint")},
                    {"healed": heal_result.healed, "summary": heal_result.summary},
                    reasoning=heal_result.summary,
                )

                if heal_result.healed:
                    ticket.status = "resolved"
                    ticket.resolution_summary = (
                        f"{empathy.full_response}\n\n"
                        f"✅ Issue resolved automatically.\n"
                        f"🔧 Self-healed: {heal_result.summary}"
                    )
                else:
                    ticket.status = "escalated"
                    ticket.escalation_reason = (
                        f"Autonomous execution failed and self-healing exhausted: {heal_result.summary}"
                    )
            elif action_result.success:
                auditor.log(
                    "execution", "ActionAgent",
                    {"actions": judge_result.safe_actions},
                    {"success": True, "executed": len(action_result.executed_actions)},
                    confidence=1.0,
                    reasoning="All actions executed successfully",
                )
                ticket.status = "resolved"
                ticket.resolution_summary = (
                    f"{empathy.full_response}\n\n"
                    f"✅ Issue resolved automatically.\n\n"
                    f"**Actions taken:**\n" +
                    "\n".join(f"• {s}" for s in plan.steps)
                )

        from datetime import datetime
        if ticket.status == "resolved":
            ticket.resolved_at = datetime.utcnow()

        db.commit()

    except Exception as e:
        logger.error(f"Pipeline error for ticket {ticket.id}: {e}", exc_info=True)
        ticket.status = "escalated"
        ticket.escalation_reason = f"Pipeline error: {e}"
        ticket.mode = "ESCALATED"
        db.commit()

    total_ms = round((time.time() - t_start) * 1000, 2)
    logger.info(f"Pipeline complete: ticket={ticket.id} mode={ticket.mode} status={ticket.status} ({total_ms}ms)")
    return ticket


def _decide_mode(judge_result, triage_result, plan) -> str:
    """Four-way decision: AUTO | ASSISTED | ESCALATED | CLARIFICATION"""
    # Critical violations → immediate escalation
    if judge_result.violations:
        from agents.judge_agent import _has_critical_violation
        if _has_critical_violation(judge_result.violations):
            return "ESCALATED"
        return "ASSISTED"

    # No valid actions to execute → assisted
    if not judge_result.safe_actions:
        return "ASSISTED"

    # Confidence routing
    if judge_result.confidence >= settings.AUTO_THRESHOLD:
        return "AUTO"
    elif judge_result.confidence >= settings.ASSISTED_THRESHOLD:
        return "ASSISTED"
    else:
        return "ESCALATED"
