import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pydantic import BaseModel
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ActionResult(BaseModel):
    success: bool
    executed_actions: List[dict]
    failed_action: Optional[dict]
    failure_reason: Optional[str]
    needs_self_healing: bool
    outputs: Dict[str, Any]


# ── Mock CRM Simulator ─────────────────────────────────────────────────────────
# In production, replace with real CRM/ERP HTTP calls.

MOCK_CRM_RESPONSES = {
    "POST /iam/verify-identity": {"status": "verified", "confidence": 0.95},
    "POST /iam/reset-password": {"status": "reset_link_sent", "expires_in": "24h"},
    "PUT /iam/unlock": {"status": "unlocked", "timestamp": "now"},
    "POST /access/request": {"ticket_id": "ACC-AUTO-001", "status": "submitted"},
    "POST /user/notify": {"status": "notified", "channel": "email"},
    "GET /billing/order": {"order_id": "ORD-001", "amount": 299.99, "date": "2024-01-15"},
    "GET /billing/refund-eligibility": {"eligible": True, "reason": "within_30_days"},
    "POST /billing/refund": {"refund_id": "REF-001", "status": "processing", "eta_days": 5},
    "POST /billing/dispute": {"dispute_id": "DSP-001", "status": "under_review"},
    "GET /billing/invoice": {"invoice_id": "INV-001", "amount": 150.00, "due_date": "2024-02-01"},
    "POST /ticket/create": {"ticket_id": "TKT-AUTO-001", "status": "open"},
    "PUT /ticket/assign": {"ticket_id": "TKT-AUTO-001", "assignee": "auto-agent"},
    "GET /iam/status": {"status": "active", "last_login": "2024-01-15"},
    "GET /user/profile": {"name": "User", "email": "user@company.com", "department": "IT"},
}

# Simulate occasional failures for self-healing testing
_FAILURE_SIMULATION: dict = {}


async def _execute_single_action(
    action: dict,
    context: dict,
    timeout: float = 10.0,
) -> Tuple[bool, Any, Optional[str]]:
    """
    Execute a single API action against the CRM.
    Returns (success, response_data, error_message).
    """
    endpoint = action.get("endpoint", "")
    params = action.get("params", {})

    # Resolve template variables from context
    resolved_params = {}
    for k, v in params.items():
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            param_key = v[1:-1]
            resolved_params[k] = context.get(param_key, v)
        else:
            resolved_params[k] = v

    # Check failure simulation
    if _FAILURE_SIMULATION.get(endpoint):
        _FAILURE_SIMULATION[endpoint] -= 1
        return False, None, f"Endpoint {endpoint} temporarily unavailable (simulated drift)"

    # Use real CRM if configured, otherwise mock
    if settings.CRM_BASE_URL and not settings.CRM_BASE_URL.endswith("mock-crm"):
        return await _call_real_crm(endpoint, resolved_params, timeout)

    # Mock CRM response
    if endpoint in MOCK_CRM_RESPONSES:
        await asyncio.sleep(0.1)  # Simulate network latency
        return True, MOCK_CRM_RESPONSES[endpoint], None
    else:
        return False, None, f"Unknown endpoint: {endpoint}"


async def _call_real_crm(endpoint: str, params: dict, timeout: float) -> Tuple[bool, Any, Optional[str]]:
    """Execute against a real CRM endpoint."""
    method, path = endpoint.split(" ", 1)
    url = f"{settings.CRM_BASE_URL}{path}"
    headers = {}
    if settings.CRM_API_KEY:
        headers["Authorization"] = f"Bearer {settings.CRM_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(url, params=params, headers=headers)
            elif method == "POST":
                resp = await client.post(url, json=params, headers=headers)
            elif method == "PUT":
                resp = await client.put(url, json=params, headers=headers)
            else:
                return False, None, f"Unsupported method: {method}"

            if resp.status_code < 300:
                return True, resp.json(), None
            else:
                return False, None, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except httpx.TimeoutException:
        return False, None, f"Timeout calling {endpoint}"
    except Exception as e:
        return False, None, str(e)


async def execute_plan(
    actions: List[dict],
    context: dict,
) -> ActionResult:
    """
    Execute a list of approved API actions sequentially.
    Stops on first failure and returns failure info for the learner agent.
    """
    executed = []
    outputs = {}

    for action in actions:
        action_name = action.get("action", "unknown")
        endpoint = action.get("endpoint", "")

        logger.info(f"Executing action: {action_name} → {endpoint}")
        success, data, error = await _execute_single_action(action, context)

        if success:
            executed.append({**action, "status": "success", "response": data})
            outputs[action_name] = data
            # Pass outputs forward as context for subsequent actions
            if data and isinstance(data, dict):
                context.update(data)
        else:
            logger.warning(f"Action failed: {action_name} → {error}")
            return ActionResult(
                success=False,
                executed_actions=executed,
                failed_action={**action, "error": error},
                failure_reason=error,
                needs_self_healing=True,
                outputs=outputs,
            )

    return ActionResult(
        success=True,
        executed_actions=executed,
        failed_action=None,
        failure_reason=None,
        needs_self_healing=False,
        outputs=outputs,
    )


def simulate_endpoint_failure(endpoint: str, count: int = 1) -> None:
    """
    Test hook: simulate endpoint failures to trigger self-healing.
    """
    _FAILURE_SIMULATION[endpoint] = count
