from __future__ import annotations

from typing import Any

from payment_exception_mvp.agents import _specialist

_ROLE = (
    "You assess whether a payment is a duplicate of another submission and whether the "
    "duplicate candidate should be recommended for cancellation or needs reconciliation."
)


def analyze(agent_input: dict[str, Any], config: Any = None) -> dict[str, Any]:
    context = agent_input["context"]
    duplicate_evidence = context.get("duplicate_evidence", {})
    candidates = duplicate_evidence.get("duplicate_candidates", [])
    baseline = {
        "agent_name": "DuplicatePaymentAgent",
        "classification": "duplicate_payment",
        "action": "CANCEL_DUPLICATE" if candidates else "MANUAL_REVIEW",
        "automation_allowed": False,
        "confidence": 0.96 if candidates else 0.5,
        "risk_level": "HIGH" if candidates else "MEDIUM",
        "reason_codes": ["DUPLICATE_CANDIDATE_FOUND"] if candidates else ["DUPLICATE_UNCONFIRMED"],
        "evidence": [
            f"duplicate_evidence.payment_fingerprint={duplicate_evidence.get('payment_fingerprint')}",
            f"duplicate_evidence.duplicate_candidates.count={len(candidates)}",
        ],
        "fallbacks_triggered": ["temporary_subagent_stub"],
        "explanation": "Duplicate payment agent recommends cancelling duplicate candidate as recommendation-only.",
        "next_steps": ["Review duplicate candidate", "Do not retry until duplicate status is reconciled"],
    }
    return _specialist.refine(config, agent_name="DuplicatePaymentAgent", role=_ROLE, context=context, baseline=baseline)
