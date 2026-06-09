from __future__ import annotations

from typing import Any


def analyze(agent_input: dict[str, Any]) -> dict[str, Any]:
    context = agent_input["context"]
    compliance = context.get("compliance", {})
    return {
        "agent_name": "ComplianceAgent",
        "classification": "compliance_hold",
        "action": "ESCALATE_COMPLIANCE",
        "automation_allowed": False,
        "confidence": 1.0,
        "risk_level": "CRITICAL",
        "reason_codes": ["COMPLIANCE_HOLD", "FAIL_CLOSED"],
        "evidence": [
            f"compliance.compliance_hold_status={compliance.get('compliance_hold_status')}",
            f"compliance.screening_result={compliance.get('screening_result')}",
            f"compliance.risk_flags={compliance.get('risk_flags')}",
        ],
        "fallbacks_triggered": ["temporary_subagent_stub"],
        "explanation": "Temporary compliance agent stub fails closed and escalates compliance signals.",
        "next_steps": ["Escalate to compliance operations", "Do not release or retry payment in MVP"],
    }
