from __future__ import annotations

from typing import Any

from payment_exception_mvp.schemas import AgentOutput, CanonicalPaymentException


CONSERVATIVE_ACTIONS = {"HOLD_AND_RECONCILE", "ESCALATE_COMPLIANCE", "MANUAL_REVIEW"}
RETRY_ACTIONS = {"RECOMMEND_RETRY"}


def has_compliance_signal(event: CanonicalPaymentException) -> bool:
    code = (event.exception.exception_code or "").upper()
    hold_status = (event.compliance.compliance_hold_status or "NONE").upper()
    return hold_status != "NONE" or any(token in code for token in ("COMPLIANCE", "SANCTIONS", "AML", "POLICY"))


def apply_safety_fallbacks(event: CanonicalPaymentException, output: AgentOutput) -> AgentOutput:
    data = output.model_dump()
    fallbacks = list(data.get("fallbacks_triggered", []))

    def force(action: str, fallback: str, explanation: str, risk_level: str = "HIGH") -> None:
        if fallback not in fallbacks:
            fallbacks.append(fallback)
        data["action"] = action
        data["automation_allowed"] = False
        data["risk_level"] = risk_level
        if fallback not in data["reason_codes"]:
            data["reason_codes"].append(fallback.upper())
        data["explanation"] = explanation

    if has_compliance_signal(event):
        force(
            "ESCALATE_COMPLIANCE",
            "compliance_signal_detected",
            "Compliance signal exists, so the orchestrator forced compliance escalation.",
            "CRITICAL",
        )
    elif output.confidence < event.policy.manual_review_threshold and output.action not in CONSERVATIVE_ACTIONS:
        force(
            "MANUAL_REVIEW",
            "confidence_below_manual_review_threshold",
            "Agent confidence is below the manual review threshold, so the case requires manual review.",
        )

    if data["action"] in RETRY_ACTIONS and event.duplicate_evidence.duplicate_candidates:
        force(
            "HOLD_AND_RECONCILE",
            "retry_blocked_by_duplicate_evidence",
            "Duplicate evidence exists, so retry is blocked pending reconciliation.",
        )

    funds_status = (event.status_evidence.funds_movement_status or "UNKNOWN").upper()
    if data["action"] in RETRY_ACTIONS and funds_status == "UNKNOWN":
        force(
            "HOLD_AND_RECONCILE",
            "retry_blocked_by_unknown_funds_movement",
            "Funds movement is unknown, so retry is blocked pending reconciliation.",
        )

    validation_confidence = event.beneficiary_validation.validation_confidence
    if data["action"] == "RECOMMEND_REPAIR" and (
        validation_confidence is None or validation_confidence < event.policy.beneficiary_repair_threshold
    ):
        force(
            "REQUEST_CLIENT_CORRECTION",
            "repair_blocked_by_low_beneficiary_confidence",
            "Beneficiary validation confidence is too low for a repair recommendation.",
            "MEDIUM",
        )

    data["fallbacks_triggered"] = fallbacks
    data["automation_allowed"] = False
    return AgentOutput.model_validate(data)


def manual_review_output(
    *,
    agent_name: str,
    classification: str,
    reason_code: str,
    explanation: str,
    fallback: str | None = None,
    evidence: list[str] | None = None,
) -> AgentOutput:
    return AgentOutput(
        agent_name=agent_name,
        classification=classification,
        action="MANUAL_REVIEW",
        automation_allowed=False,
        confidence=0.0,
        risk_level="HIGH",
        reason_codes=[reason_code],
        evidence=evidence or [],
        fallbacks_triggered=[fallback] if fallback else [],
        explanation=explanation,
        next_steps=["Route case to operations manual review", "Do not perform financial side effects from the MVP"],
    )
