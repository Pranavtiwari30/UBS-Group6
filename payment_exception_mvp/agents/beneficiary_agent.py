from __future__ import annotations

from typing import Any

from payment_exception_mvp.agents import _specialist

_ROLE = (
    "You assess whether a payment failed because of incorrect or invalid beneficiary "
    "details and whether the client must correct them before any retry."
)


def analyze(agent_input: dict[str, Any], config: Any = None) -> dict[str, Any]:
    context = agent_input["context"]
    validation = context.get("beneficiary_validation", {})
    failed_fields = validation.get("failed_fields", [])
    evidence = [
        f"beneficiary_validation.validation_status={validation.get('validation_status')}",
        f"beneficiary_validation.failed_fields={failed_fields}",
        f"payment_summary.funds_movement_status={context.get('payment_summary', {}).get('funds_movement_status')}",
    ]
    baseline = {
        "agent_name": "BeneficiaryAgent",
        "classification": "incorrect_beneficiary",
        "action": "REQUEST_CLIENT_CORRECTION",
        "automation_allowed": False,
        "confidence": validation.get("validation_confidence") or 0.85,
        "risk_level": "MEDIUM",
        "reason_codes": ["INVALID_BENEFICIARY", "CLIENT_INPUT_REQUIRED"],
        "evidence": evidence,
        "fallbacks_triggered": ["temporary_subagent_stub"],
        "explanation": "Beneficiary agent recommends client correction for invalid beneficiary evidence.",
        "next_steps": ["Ask client to confirm beneficiary details", "Do not retry until details are corrected"],
    }
    return _specialist.refine(config, agent_name="BeneficiaryAgent", role=_ROLE, context=context, baseline=baseline)
