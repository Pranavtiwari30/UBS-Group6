from __future__ import annotations

from typing import Any


def analyze(agent_input: dict[str, Any]) -> dict[str, Any]:
    context = agent_input["context"]
    status = context.get("status_evidence", {})
    network = context.get("network", {})
    return {
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
        "explanation": "Temporary network agent stub recommends hold and reconcile for network uncertainty.",
        "next_steps": ["Check rail acknowledgement and ledger state", "Do not retry until finality is known"],
    }
