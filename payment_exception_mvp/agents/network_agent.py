from __future__ import annotations

from typing import Any

from payment_exception_mvp.agents import _specialist

_ROLE = (
    "You assess payment-rail and network failures and whether funds finality is uncertain, "
    "recommending hold-and-reconcile until the ledger and rail state are confirmed."
)


def analyze(agent_input: dict[str, Any], config: Any = None) -> dict[str, Any]:
    context = agent_input["context"]
    status = context.get("status_evidence", {})
    network = context.get("network", {})
    baseline = {
        "agent_name": "NetworkAgent",
        "classification": "network_failure",
        "action": "HOLD_AND_RECONCILE",
        "automation_allowed": False,
        "confidence": 0.9,
        "risk_level": "HIGH",
        "reason_codes": ["NETWORK_FAILURE", "RECONCILIATION_REQUIRED"],
        "evidence": [
            f"status_evidence.funds_movement_status={status.get('funds_movement_status')}",
            f"status_evidence.network_finality={status.get('network_finality')}",
            f"network.rail_health_status={network.get('rail_health_status')}",
        ],
        "fallbacks_triggered": ["temporary_subagent_stub"],
        "explanation": "Network agent recommends hold and reconcile for network uncertainty.",
        "next_steps": ["Check rail acknowledgement and ledger state", "Do not retry until finality is known"],
    }
    return _specialist.refine(config, agent_name="NetworkAgent", role=_ROLE, context=context, baseline=baseline)
