from __future__ import annotations

from dataclasses import dataclass

from payment_exception_mvp.schemas import CanonicalPaymentException


@dataclass(frozen=True)
class ClassificationResult:
    classification: str
    selected_agent: str
    reason: str


def _contains_any(value: str | None, tokens: tuple[str, ...]) -> bool:
    normalized = (value or "").upper()
    return any(token in normalized for token in tokens)


def classify_exception(event: CanonicalPaymentException) -> ClassificationResult:
    code = event.exception.exception_code
    compliance_status = (event.compliance.compliance_hold_status or "NONE").upper()

    if compliance_status != "NONE" or _contains_any(code, ("COMPLIANCE", "SANCTIONS", "AML", "POLICY")):
        return ClassificationResult("compliance_hold", "ComplianceAgent", "compliance signal has highest priority")

    if _contains_any(code, ("DUPLICATE",)) or bool(event.duplicate_evidence.duplicate_candidates):
        return ClassificationResult("duplicate_payment", "DuplicatePaymentAgent", "duplicate code or candidate evidence found")

    if _contains_any(code, ("BENEFICIARY", "INVALID_ACCOUNT", "INVALID_IFSC", "INVALID_UPI", "NAME_MISMATCH")):
        return ClassificationResult("incorrect_beneficiary", "BeneficiaryAgent", "beneficiary exception code matched")

    if _contains_any(code, ("NETWORK", "TIMEOUT", "NO_ACK", "RAIL_UNAVAILABLE", "DOWNSTREAM")):
        return ClassificationResult("network_failure", "NetworkAgent", "network exception code matched")

    return ClassificationResult("manual_review", "ManualReviewFallback", "unsupported exception type")
