import logging
from typing import List, Optional

from pydantic import BaseModel
from llm_client import get_llm
from rag.embeddings import embed, cosine_similarity

logger = logging.getLogger(__name__)

# ── Policy Definitions ─────────────────────────────────────────────────────────

POLICIES = [
    {
        "id": "POL-001",
        "rule": "Finance domain operations require human approval",
        "severity": "CRITICAL",
        "check": lambda intent, entities, steps: entities.get("domain") == "Finance",
    },
    {
        "id": "POL-002",
        "rule": "Access escalation requires human approval",
        "severity": "CRITICAL",
        "check": lambda intent, entities, steps: intent in ("access_escalation", "access_revoke"),
    },
    {
        "id": "POL-003",
        "rule": "Refunds over $5000 require Finance Director approval",
        "severity": "CRITICAL",
        "check": lambda intent, entities, steps: (
            intent in ("refund_request", "billing_dispute") and
            float(entities.get("amount", 0)) > 5000
        ),
    },
    {
        "id": "POL-004",
        "rule": "Security incidents require immediate human escalation",
        "severity": "CRITICAL",
        "check": lambda intent, entities, steps: intent == "security_incident",
    },
    {
        "id": "POL-005",
        "rule": "Destructive operations are forbidden",
        "severity": "CRITICAL",
        "check": lambda intent, entities, steps: any(
            any(kw in step.lower() for kw in [
                "delete all", "drop database", "rm -rf", "format disk",
                "wipe", "disable firewall", "bypass authentication",
            ])
            for step in steps
        ),
    },
    {
        "id": "POL-006",
        "rule": "Bulk user operations require admin approval",
        "severity": "HIGH",
        "check": lambda intent, entities, steps: any(
            kw in " ".join(steps).lower()
            for kw in ["all users", "bulk", "mass reset", "everyone"]
        ),
    },
]

ALLOWED_ENDPOINTS = {
    "POST /iam/verify-identity",
    "POST /iam/reset-password",
    "PUT /iam/unlock",
    "GET /iam/status",
    "PUT /access/grant",
    "PUT /access/revoke",
    "POST /access/request",
    "GET /ticket/status",
    "POST /ticket/create",
    "PUT /ticket/update",
    "PUT /ticket/close",
    "PUT /ticket/escalate",
    "PUT /ticket/assign",
    "GET /user/profile",
    "PUT /user/update",
    "POST /user/notify",
    "GET /system/health",
    "GET /system/status",
    "GET /billing/order",
    "GET /billing/invoice",
    "GET /billing/refund-eligibility",
    "POST /billing/refund",
    "POST /billing/dispute",
    "GET /knowledge/article",
}


class JudgeResult(BaseModel):
    confidence: int                    # 0-100
    violations: List[str]
    alignment_score: float
    llm_logic_valid: bool
    llm_logic_score: float
    recommendation: str
    diagnostic: Optional[str]
    safe_actions: List[dict]           # Filtered, whitelisted actions
    confidence_breakdown: dict


def _evaluate_policies(intent: str, entities: dict, steps: List[str]) -> List[str]:
    violations = []
    for policy in POLICIES:
        try:
            if policy["check"](intent, entities, steps):
                violations.append(f"{policy['severity']}: {policy['id']} — {policy['rule']}")
        except Exception:
            pass
    return violations


def _has_critical_violation(violations: List[str]) -> bool:
    return any(v.startswith("CRITICAL") for v in violations)


def _policy_compliance_score(violations: List[str]) -> float:
    if not violations:
        return 1.0
    if _has_critical_violation(violations):
        return 0.0
    return max(0.0, 1.0 - len(violations) * 0.3)


def _filter_actions(api_actions: List[dict]) -> List[dict]:
    safe = []
    for action in api_actions:
        endpoint = action.get("endpoint", "")
        if endpoint in ALLOWED_ENDPOINTS:
            safe.append(action)
        else:
            logger.warning(f"BLOCKED endpoint not in whitelist: {endpoint}")
    return safe


def _compute_alignment(query: str, steps: List[str]) -> float:
    if not steps or not query:
        return 0.0
    try:
        q_vec = embed(query)
        plan_vec = embed(" ".join(steps))
        return round(cosine_similarity(q_vec, plan_vec), 4)
    except Exception as e:
        logger.warning(f"Alignment score failed: {e}")
        return 0.5


def _compute_confidence(triage_conf: float, alignment: float, policy_compliance: float, llm_score: float) -> int:
    raw = (
        0.30 * triage_conf +
        0.25 * alignment +
        0.25 * policy_compliance +
        0.20 * llm_score
    ) * 100
    return max(0, min(100, int(round(raw))))


async def audit(
    query: str,
    intent: str,
    entities: dict,
    plan_steps: List[str],
    api_actions: List[dict],
    reasoning: str,
    sources: List[str],
    triage_confidence: float,
    risk_level: str,
) -> JudgeResult:
    """
    Audit agent: validate safety, alignment, and generate composite confidence score.
    Critical violations force immediate escalation — no LLM check needed.
    """
    # 1. Policy check
    violations = _evaluate_policies(intent, entities, plan_steps)

    # 2. Filter actions to whitelist
    safe_actions = _filter_actions(api_actions)

    # 3. Critical violation → immediate escalation
    if _has_critical_violation(violations):
        return JudgeResult(
            confidence=0,
            violations=violations,
            alignment_score=0.0,
            llm_logic_valid=False,
            llm_logic_score=0.0,
            recommendation="CRITICAL policy violation. Mandatory human escalation.",
            diagnostic="Critical policy violated — no automatic action permitted.",
            safe_actions=[],
            confidence_breakdown={
                "triage": triage_confidence,
                "alignment": 0.0,
                "policy": 0.0,
                "llm_logic": 0.0,
            },
        )

    # 4. Semantic alignment
    alignment = _compute_alignment(query, plan_steps)

    # 5. Policy compliance score
    policy_compliance = _policy_compliance_score(violations)

    # 6. LLM logic validation
    plan_numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(plan_steps))
    prompt = f"""You are an expert enterprise IT support plan auditor. Validate this resolution plan.

ORIGINAL QUERY: {query}
INTENT: {intent}
ENTITIES: {entities}
RISK LEVEL: {risk_level}

PROPOSED PLAN:
{plan_numbered}

REASONING:
{reasoning}

SOURCES: {", ".join(sources) if sources else "None"}

EVALUATE:
1. Does the plan directly address the user's query?
2. Are there logical gaps, missing steps, or unsafe assumptions?
3. Is every step grounded in the reasoning/sources, or are there hallucinated steps?
4. Is the risk assessment accurate?

Respond ONLY with valid JSON:
{{
  "llm_logic_valid": true,
  "llm_logic_score": 0.85,
  "recommendation": "Plan is complete and safe to execute.",
  "diagnostic": null
}}

- llm_logic_score: 0.0-1.0
- diagnostic: null if valid, otherwise specific reason for failure"""

    try:
        llm = get_llm()
        raw = llm.complete_json(prompt, model="smart")
        llm_logic_valid = bool(raw.get("llm_logic_valid", False))
        llm_logic_score = float(raw.get("llm_logic_score", 0.5))
        recommendation = raw.get("recommendation", "Review required.")
        diagnostic = raw.get("diagnostic")
    except Exception as e:
        logger.error(f"Judge LLM failed: {e}")
        llm_logic_valid = False
        llm_logic_score = 0.3
        recommendation = f"Auditor error — defaulting to ASSISTED mode."
        diagnostic = str(e)

    confidence = _compute_confidence(triage_confidence, alignment, policy_compliance, llm_logic_score)

    return JudgeResult(
        confidence=confidence,
        violations=violations,
        alignment_score=alignment,
        llm_logic_valid=llm_logic_valid,
        llm_logic_score=llm_logic_score,
        recommendation=recommendation,
        diagnostic=diagnostic,
        safe_actions=safe_actions,
        confidence_breakdown={
            "triage": round(triage_confidence, 3),
            "alignment": alignment,
            "policy": round(policy_compliance, 3),
            "llm_logic": round(llm_logic_score, 3),
        },
    )
