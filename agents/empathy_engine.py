import logging
from pydantic import BaseModel
from llm_client import get_llm

logger = logging.getLogger(__name__)


class EmpathyResponse(BaseModel):
    acknowledgment: str          # Empathetic opening
    validation_statement: str    # Validates user's feeling
    transition: str              # Bridges to resolution
    full_response: str           # Complete empathetic message


def _get_stress_profile(stress_level: float) -> str:
    if stress_level >= 0.7:
        return "very frustrated and upset — use strong validation"
    elif stress_level >= 0.4:
        return "somewhat frustrated — acknowledge inconvenience"
    elif stress_level >= 0.2:
        return "mildly concerned — be warm but focused"
    else:
        return "calm — be professional and helpful"


async def generate_empathy_response(
    query: str,
    intent: str,
    priority: str,
    stress_level: float,
) -> EmpathyResponse:
    """
    Generate a validation-first empathetic response before technical resolution.
    Based on clinical validation therapy principles to reduce 'IVR rage'.
    """
    stress_profile = _get_stress_profile(stress_level)
    intent_readable = intent.replace("_", " ")

    prompt = f"""You are a compassionate enterprise support specialist trained in validation therapy.
Your role is to FIRST acknowledge and validate the customer's feelings BEFORE moving to technical resolution.

VALIDATION THERAPY PRINCIPLES:
- Acknowledge the person's experience as real and understandable
- Never dismiss, minimize, or immediately jump to solutions
- Use "I understand...", "That sounds incredibly frustrating...", "You're right to be concerned..."
- Validate the impact the issue has had on them
- Then gently transition to resolution

CUSTOMER SITUATION:
- Query: "{query}"
- Issue type: {intent_readable}
- Priority: {priority}
- Emotional state: {stress_profile} (stress level: {stress_level:.1f}/1.0)

Generate an empathetic response with these parts. Respond ONLY with valid JSON:
{{
  "acknowledgment": "I completely understand how frustrating it must be when...",
  "validation_statement": "Your feelings about this are completely valid because...",
  "transition": "I want to make this right for you. Let me...",
  "full_response": "Combined empathetic message (2-3 sentences max, warm but professional)"
}}

Rules:
- full_response must be natural, conversational, NOT robotic
- Do NOT mention the customer's stress level explicitly
- Do NOT promise specific timelines you cannot guarantee
- For Critical/security issues: be calm and reassuring, not alarming"""

    try:
        llm = get_llm()
        raw = llm.complete_json(prompt, model="fast")
        return EmpathyResponse(
            acknowledgment=raw.get("acknowledgment", ""),
            validation_statement=raw.get("validation_statement", ""),
            transition=raw.get("transition", ""),
            full_response=raw.get("full_response", "I understand your concern. Let me help you resolve this."),
        )
    except Exception as e:
        logger.error(f"Empathy engine failed: {e}")
        fallbacks = {
            "high": "I sincerely apologize for the trouble you're experiencing. That must be incredibly frustrating, and I want to resolve this for you right away.",
            "medium": "I understand this is inconvenient, and I appreciate your patience. Let me look into this for you.",
            "low": "Thank you for reaching out. I'm here to help you with this.",
        }
        level = "high" if stress_level >= 0.6 else ("medium" if stress_level >= 0.3 else "low")
        fallback_msg = fallbacks[level]
        return EmpathyResponse(
            acknowledgment=fallback_msg,
            validation_statement="",
            transition="Let me help you resolve this.",
            full_response=fallback_msg,
        )
