import logging
from typing import List, Optional

from pydantic import BaseModel
from llm_client import get_llm
from rag.retriever import search

logger = logging.getLogger(__name__)


class ResolutionPlan(BaseModel):
    steps: List[str]
    api_actions: List[dict]         # {"action": str, "endpoint": str, "params": dict}
    sources: List[str]
    reasoning: str
    risk_level: str                 # Low | Medium | High
    estimated_duration_seconds: int
    fallback_triggered: bool
    clarification_needed: Optional[str]


def _format_rag_context(results: List[dict]) -> str:
    if not results:
        return "No relevant knowledge found in the knowledge base."
    lines = []
    for i, doc in enumerate(results, 1):
        score = doc.get("score", 0)
        meta = doc.get("metadata", {})
        title = meta.get("title", f"Document {i}")
        lines.append(f"[{doc['id']}] {title} (relevance: {score:.2f})\n{doc['text']}")
    return "\n\n---\n\n".join(lines)


SAFE_API_ACTIONS = {
    "password_reset": [
        {"action": "verify_identity", "endpoint": "POST /iam/verify-identity", "params": {"user_id": "{user_id}"}},
        {"action": "send_reset_link", "endpoint": "POST /iam/reset-password", "params": {"email": "{email}", "method": "email_link"}},
    ],
    "account_unlock": [
        {"action": "verify_identity", "endpoint": "POST /iam/verify-identity", "params": {"user_id": "{user_id}"}},
        {"action": "unlock_account", "endpoint": "PUT /iam/unlock", "params": {"user_id": "{user_id}"}},
    ],
    "access_request": [
        {"action": "create_access_ticket", "endpoint": "POST /access/request", "params": {"user_id": "{user_id}", "system": "{system}"}},
        {"action": "notify_manager", "endpoint": "POST /user/notify", "params": {"type": "approval_request"}},
    ],
    "refund_request": [
        {"action": "verify_order", "endpoint": "GET /billing/order", "params": {"order_id": "{order_id}"}},
        {"action": "check_eligibility", "endpoint": "GET /billing/refund-eligibility", "params": {"order_id": "{order_id}"}},
        {"action": "process_refund", "endpoint": "POST /billing/refund", "params": {"order_id": "{order_id}", "reason": "{reason}"}},
    ],
    "billing_dispute": [
        {"action": "lookup_invoice", "endpoint": "GET /billing/invoice", "params": {"invoice_id": "{invoice_id}"}},
        {"action": "flag_dispute", "endpoint": "POST /billing/dispute", "params": {"invoice_id": "{invoice_id}"}},
    ],
    "technical_issue": [
        {"action": "create_ticket", "endpoint": "POST /ticket/create", "params": {"category": "technical"}},
        {"action": "assign_technician", "endpoint": "PUT /ticket/assign", "params": {"ticket_id": "{ticket_id}"}},
    ],
}


async def generate_plan(
    intent: str,
    entities: dict,
    priority: str,
    rag_results: List[dict],
    session_history: str = "",
    retry_diagnostic: Optional[str] = None,
) -> ResolutionPlan:
    """
    Generate a step-by-step resolution plan grounded in RAG knowledge.
    """
    rag_context = _format_rag_context(rag_results)
    suggested_actions = SAFE_API_ACTIONS.get(intent, [
        {"action": "create_ticket", "endpoint": "POST /ticket/create", "params": {"category": intent}},
    ])

    retry_section = ""
    if retry_diagnostic:
        retry_section = f"\nPREVIOUS ATTEMPT FAILED — Address this diagnostic:\n{retry_diagnostic}\n"

    prompt = f"""You are a senior enterprise IT support specialist. Generate a precise resolution plan.

INTENT: {intent}
ENTITIES: {entities}
PRIORITY: {priority}
{retry_section}
AVAILABLE API ACTIONS:
{suggested_actions}

KNOWLEDGE BASE CONTEXT (use ONLY this — do not invent steps):
{rag_context}

SESSION HISTORY:
{session_history or "None"}

INSTRUCTIONS:
1. Create an ordered step-by-step resolution plan using ONLY the knowledge base context.
2. Each step must be actionable and specific.
3. Map steps to the available API actions where applicable.
4. Assess risk: Low (standard procedure), Medium (reversible impact), High (irreversible or sensitive).
5. If knowledge base has insufficient info, set fallback_triggered=true.
6. List all source document IDs used (e.g., "KB-001").
7. Estimate completion time in seconds.
8. reasoning must reference specific source docs.

Respond ONLY with valid JSON:
{{
  "steps": ["Step 1: Verify user identity", "Step 2: Send password reset email"],
  "api_actions": [{{"action": "verify_identity", "endpoint": "POST /iam/verify-identity", "params": {{"user_id": "from_entities"}}}}],
  "sources": ["KB-001"],
  "reasoning": "Based on KB-001, password resets require identity verification first...",
  "risk_level": "Low",
  "estimated_duration_seconds": 120,
  "fallback_triggered": false,
  "clarification_needed": null
}}"""

    try:
        llm = get_llm()
        raw = llm.complete_json(prompt, model="smart")
        return ResolutionPlan(
            steps=raw.get("steps", []),
            api_actions=raw.get("api_actions", []),
            sources=raw.get("sources", []),
            reasoning=raw.get("reasoning", ""),
            risk_level=raw.get("risk_level", "Medium"),
            estimated_duration_seconds=int(raw.get("estimated_duration_seconds", 120)),
            fallback_triggered=bool(raw.get("fallback_triggered", False)),
            clarification_needed=raw.get("clarification_needed"),
        )
    except Exception as e:
        logger.error(f"Knowledge agent failed: {e}")
        return ResolutionPlan(
            steps=["Escalate to human support agent"],
            api_actions=[],
            sources=[],
            reasoning=f"Plan generation failed: {e}",
            risk_level="High",
            estimated_duration_seconds=0,
            fallback_triggered=True,
            clarification_needed=None,
        )


import json
from sqlalchemy.orm import Session
from database import LearningMemory

async def retrieve_and_plan(
    intent: str,
    entities: dict,
    priority: str,
    original_query: str,
    session_history: str = "",
    retry_diagnostic: Optional[str] = None,
    db: Optional[Session] = None,
) -> ResolutionPlan:
    """Full pipeline: retrieve KB docs → generate plan."""
    # Build a richer search query combining intent and user query
    search_query = f"{intent.replace('_', ' ')} {original_query}"
    rag_results = search(search_query)

    # Fetch previously successful healed paths for this intent
    historic_heals = []
    if db:
        memories = db.query(LearningMemory).filter_by(action_type=intent).all()
        for mem in memories:
            if mem.successful_path:
                try:
                    path_data = json.loads(mem.successful_path)
                    historic_heals.append(f"- Known healed endpoint: {path_data.get('endpoint')} for {mem.action_type}")
                except:
                    pass

    diagnostic_addon = retry_diagnostic or ""
    if historic_heals:
        diagnostic_addon += "\nSelf-Healing Knowledge:\n" + "\n".join(historic_heals)

    return await generate_plan(
        intent=intent,
        entities=entities,
        priority=priority,
        rag_results=rag_results,
        session_history=session_history,
        retry_diagnostic=diagnostic_addon if diagnostic_addon else None,
    )
