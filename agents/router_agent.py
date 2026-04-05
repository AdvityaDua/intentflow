import logging
from typing import Optional

from pydantic import BaseModel
from llm_client import get_llm

logger = logging.getLogger(__name__)

STRESS_KEYWORDS = [
    "frustrated", "angry", "furious", "unacceptable", "terrible", "horrible",
    "disgusted", "outraged", "furious", "worst", "useless", "incompetent",
    "disgusting", "absurd", "ridiculous", "lawsuit", "cancel", "quit",
    "never again", "disaster", "nightmare", "pathetic", "scam",
]

CRITICAL_KEYWORDS = [
    "outage", "data breach", "production down", "system failure", "security incident",
    "ransomware", "compromised", "ddos", "zero-day", "hacked", "stolen data",
    "service down", "emergency", "urgent", "critical failure",
]

INTENT_TAXONOMY = {
    "password_reset": "User cannot log in or needs to reset their password",
    "account_unlock": "Account is locked due to failed attempts",
    "access_request": "New system or resource access is needed",
    "access_revoke": "Access needs to be removed",
    "billing_dispute": "Incorrect charge, billing error, or refund needed",
    "refund_request": "Customer is requesting a refund",
    "technical_issue": "Software, hardware, or network problem",
    "vpn_issue": "VPN connection problem",
    "email_issue": "Email not working or configuration needed",
    "sap_issue": "SAP system access or functionality problem",
    "hardware_request": "New or replacement hardware needed",
    "software_request": "New software installation or license request",
    "security_incident": "Suspected security breach or attack",
    "data_recovery": "Files or data lost and recovery needed",
    "general_inquiry": "General question or information request",
    "unknown": "Cannot be classified from the provided information",
}


class TriageResult(BaseModel):
    intent: str
    intent_description: str
    priority: str
    stress_level: float
    entities: dict
    needs_clarification: bool
    clarification_question: Optional[str]
    secondary_intent: Optional[str]
    confidence: float


def _detect_stress(text: str) -> float:
    """Rule-based stress detection — quick pre-filter before LLM."""
    text_lower = text.lower()
    stress_count = sum(1 for kw in STRESS_KEYWORDS if kw in text_lower)
    # Caps at 1.0, each keyword adds ~0.2
    return min(1.0, stress_count * 0.2)


def _has_critical_keywords(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in CRITICAL_KEYWORDS)


async def triage(query: str, session_history: str = "") -> TriageResult:
    """
    Classify intent, extract entities, detect stress and priority.
    """
    if len(query.strip()) < 3:
        return TriageResult(
            intent="unknown",
            intent_description="Query too short",
            priority="Low",
            stress_level=0.0,
            entities={},
            needs_clarification=True,
            clarification_question="Could you describe your issue in more detail?",
            secondary_intent=None,
            confidence=0.0,
        )

    rule_stress = _detect_stress(query)
    force_critical = _has_critical_keywords(query)

    taxonomy_text = "\n".join(f"- {k}: {v}" for k, v in INTENT_TAXONOMY.items())

    prompt = f"""You are an enterprise IT support triage specialist. Analyze the user's query and respond ONLY with valid JSON.

INTENT TAXONOMY:
{taxonomy_text}

SESSION HISTORY (for context):
{session_history or "None"}

USER QUERY:
{query}

ANALYZE:
1. Classify the primary intent (use exact key from taxonomy).
2. Extract entities: user_id, email, system, module, error_code, order_id, amount, device_type, etc.
3. Assign priority: "Critical" (security/outage), "High" (blocking work), "Medium" (inconvenient), "Low" (informational).
4. Estimate stress_level 0.0-1.0 based on emotional tone.
5. If you cannot classify with >50% confidence, set needs_clarification=true.
6. If a secondary intent exists, name it.

Respond with ONLY this JSON (no markdown, no explanation):
{{
  "intent": "password_reset",
  "priority": "High",
  "stress_level": 0.3,
  "entities": {{}},
  "needs_clarification": false,
  "clarification_question": null,
  "secondary_intent": null,
  "confidence": 0.9
}}"""

    try:
        llm = get_llm()
        raw = llm.complete_json(prompt, model="fast")
    except Exception as e:
        logger.error(f"Triage LLM failed: {e}")
        return TriageResult(
            intent="unknown",
            intent_description="Triage error",
            priority="Medium",
            stress_level=rule_stress,
            entities={},
            needs_clarification=True,
            clarification_question="I had trouble processing your request. Could you rephrase it?",
            secondary_intent=None,
            confidence=0.0,
        )

    intent = raw.get("intent", "unknown")
    if intent not in INTENT_TAXONOMY:
        intent = "unknown"

    stress = max(rule_stress, float(raw.get("stress_level", 0.0)))
    priority = "Critical" if force_critical else raw.get("priority", "Medium")

    return TriageResult(
        intent=intent,
        intent_description=INTENT_TAXONOMY.get(intent, ""),
        priority=priority,
        stress_level=round(stress, 2),
        entities=raw.get("entities", {}),
        needs_clarification=bool(raw.get("needs_clarification", False)),
        clarification_question=raw.get("clarification_question"),
        secondary_intent=raw.get("secondary_intent"),
        confidence=float(raw.get("confidence", 0.5)),
    )
