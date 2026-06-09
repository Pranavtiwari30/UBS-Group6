from __future__ import annotations

from typing import Any

from payment_exception_mvp.agents import _specialist

_ROLE = (
    "You assess compliance and screening signals (sanctions, AML, holds). You fail closed: "
    "any genuine compliance signal must be escalated and never released or downgraded."
)


def analyze(agent_input: dict[str, Any], config: Any = None) -> dict[str, Any]:
    context = agent_input["context"]
    compliance = context.get("compliance", {})
    baseline = {
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
        "explanation": "Compliance agent fails closed and escalates compliance signals.",
        "next_steps": ["Escalate to compliance operations", "Do not release or retry payment in MVP"],
    }
    return _specialist.refine(config, agent_name="ComplianceAgent", role=_ROLE, context=context, baseline=baseline)
