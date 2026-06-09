from __future__ import annotations

from typing import Any


def analyze(agent_input: dict[str, Any]) -> dict[str, Any]:
    context = agent_input["context"]
    duplicate_evidence = context.get("duplicate_evidence", {})
    candidates = duplicate_evidence.get("duplicate_candidates", [])
    return {
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
        "explanation": "Temporary duplicate payment agent stub recommends cancelling duplicate candidate as recommendation-only.",
        "next_steps": ["Review duplicate candidate", "Do not retry until duplicate status is reconciled"],
    }
