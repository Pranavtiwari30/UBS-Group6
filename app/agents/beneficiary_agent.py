"""
Beneficiary Details Agent — DETERMINISTIC / RULE-BASED

Validates all beneficiary-related fields for a payment transaction.

Input schema (orchestrator slices to these fields only):
  payment_id, beneficiary_details, payment_rail, exception_code,
  current_transaction_status, client_contact_history

Checks:
  - Missing required fields (name, routing identifier)
  - Invalid IFSC code format  [handles both 'ifsc' and 'ifsc_code']
  - Invalid UPI ID format
  - Invalid account number
  - Invalid SWIFT/BIC code
  - Uncertain transaction status -> MANUAL_REVIEW
  - Prior unresolved client contact -> MANUAL_REVIEW

MVP Actions (Section 8 of orchestrator plan):
  - REQUEST_CLIENT_CORRECTION   -> fixable by customer providing correct details
  - MANUAL_REVIEW               -> status unclear or prior contact unresolved

NO AI / LLM used here. All checks are regex + rule based.
"""

from app.services.validation_service import validate_beneficiary_fields
from app.utils.logger import get_logger
from app.utils.helper import now_iso

logger = get_logger(__name__)

# Statuses where we cannot safely request correction because funds may be moving
UNSAFE_STATUSES = {"UNKNOWN", "PENDING", "IN_TRANSIT"}


def _has_unresolved_contact(client_contact_history: list) -> bool:
    """Return True if there is a prior contact attempt still unresolved."""
    if not client_contact_history:
        return False
    for contact in client_contact_history:
        status = str(contact.get("status", "")).upper()
        if status in ("OPEN", "PENDING", "UNRESOLVED", "AWAITING_RESPONSE"):
            return True
    return False


def analyze(transaction: dict) -> dict:
    """
    Analyze a transaction for beneficiary detail exceptions.

    Args:
        transaction: Agent-sliced dict with allowed fields only.

    Returns:
        MVP-compliant agent response dict.
    """
    payment_id = transaction.get("payment_id", "UNKNOWN")
    payment_rail = transaction.get("payment_rail", "")
    beneficiary = transaction.get("beneficiary_details", {}) or {}
    current_status = (transaction.get("current_transaction_status") or "").upper()
    client_contact_history = transaction.get("client_contact_history") or []
    exception_code = transaction.get("exception_code", "")
    beneficiary_name = beneficiary.get("name", "Unknown")

    logger.info(f"[BeneficiaryAgent] Analyzing transaction: {payment_id}")

    # ------------------------------------------------------------------
    # Guard: uncertain transaction status — never request correction if
    # funds are in an unknown or in-flight state
    # ------------------------------------------------------------------
    if current_status in UNSAFE_STATUSES:
        logger.warning(f"[BeneficiaryAgent] {payment_id} — Unsafe status '{current_status}' -> MANUAL_REVIEW")
        return {
            "agent_name": "BeneficiaryAgent",
            "classification": "uncertain_transaction_status",
            "issue_detected": True,
            "root_cause": f"Transaction status '{current_status}' is uncertain — cannot safely request correction",
            "action": "MANUAL_REVIEW",
            "automation_allowed": False,
            "confidence": 0.90,
            "risk_level": "HIGH",
            "evidence": [
                f"current_transaction_status={current_status}",
                "Funds movement is unclear — unsafe to proceed with correction",
            ],
            "explanation": (
                "The transaction is in an uncertain state. Requesting client correction "
                "before confirming the payment outcome risks data inconsistency."
            ),
            "next_steps": [
                "Confirm final transaction status with the payment network",
                "Do not request client re-input until status is FAILED or REJECTED",
                "Escalate to operations if status does not resolve within 30 minutes",
            ],
            "escalation_required": True,
            "audit_notes": (
                f"Analyzed at {now_iso()} | Payment: {payment_id} | "
                f"Rail: {payment_rail} | Status: {current_status} | "
                "Routed to MANUAL_REVIEW due to unsafe transaction status"
            ),
        }

    # ------------------------------------------------------------------
    # Guard: prior unresolved client contact
    # ------------------------------------------------------------------
    if _has_unresolved_contact(client_contact_history):
        logger.warning(f"[BeneficiaryAgent] {payment_id} — Prior unresolved contact -> MANUAL_REVIEW")
        return {
            "agent_name": "BeneficiaryAgent",
            "classification": "prior_contact_unresolved",
            "issue_detected": True,
            "root_cause": "A prior client contact attempt is unresolved — duplicate outreach would confuse the client",
            "action": "MANUAL_REVIEW",
            "automation_allowed": False,
            "confidence": 0.85,
            "risk_level": "MEDIUM",
            "evidence": [
                f"client_contact_history contains {len(client_contact_history)} entry/entries",
                "At least one prior contact is in OPEN or PENDING status",
            ],
            "explanation": (
                "A previous outreach request to the client is still open. "
                "Sending another correction request before this resolves may cause confusion."
            ),
            "next_steps": [
                "Follow up on the existing open client contact",
                "Do not open a new outreach task until the prior one is closed",
                "Escalate to operations if the contact is overdue",
            ],
            "escalation_required": False,
            "audit_notes": (
                f"Analyzed at {now_iso()} | Payment: {payment_id} | "
                f"Rail: {payment_rail} | Prior contacts: {len(client_contact_history)} | "
                "Routed to MANUAL_REVIEW due to unresolved client contact"
            ),
        }

    # ------------------------------------------------------------------
    # Run all field validations via the validation service
    # ------------------------------------------------------------------
    all_valid, errors = validate_beneficiary_fields(beneficiary, payment_rail)

    if all_valid:
        logger.info(f"[BeneficiaryAgent] {payment_id} — No beneficiary issues detected")
        return {
            "agent_name": "BeneficiaryAgent",
            "classification": "beneficiary_valid",
            "issue_detected": False,
            "root_cause": "All beneficiary details passed validation",
            "action": "PROCEED",
            "automation_allowed": False,
            "confidence": 1.0,
            "risk_level": "LOW",
            "evidence": [
                f"payment_rail={payment_rail}",
                f"exception_code={exception_code}",
                "All field format checks passed",
            ],
            "explanation": "Beneficiary details are valid for the given payment rail. No correction required.",
            "next_steps": ["Proceed with normal payment processing"],
            "escalation_required": False,
            "audit_notes": (
                f"Analyzed at {now_iso()} | Payment: {payment_id} | "
                f"Rail: {payment_rail} | Status: {current_status} | All checks passed"
            ),
        }

    # ------------------------------------------------------------------
    # Validation failed — build structured response
    # ------------------------------------------------------------------
    error_summary = "; ".join(errors)
    logger.warning(f"[BeneficiaryAgent] {payment_id} — Issues: {error_summary}")

    # Confidence: 1.0 for known rails (regex is exact), 0.85 for unknown
    confidence = 1.0 if payment_rail.upper() in ("NEFT", "RTGS", "IMPS", "UPI", "SWIFT") else 0.85

    # Build evidence list from individual errors
    evidence = [f"exception_code={exception_code}"] + [f"validation_error: {e}" for e in errors]

    return {
        "agent_name": "BeneficiaryAgent",
        "classification": "incorrect_beneficiary",
        "issue_detected": True,
        "root_cause": f"Beneficiary validation failed ({len(errors)} error(s)): {error_summary}",
        "action": "REQUEST_CLIENT_CORRECTION",
        "automation_allowed": False,
        "confidence": confidence,
        "risk_level": "MEDIUM",
        "evidence": evidence,
        "explanation": (
            f"Beneficiary details for this {payment_rail} payment are invalid or incomplete. "
            "The client must provide corrected details before the payment can be resubmitted."
        ),
        "next_steps": [
            "Open a client outreach task requesting corrected beneficiary details",
            f"Specify which fields need correction: {', '.join(errors)}",
            "Do not retry the payment until corrected details are received and validated",
            "Hold the transaction in FAILED status pending client response",
        ],
        "escalation_required": False,
        "audit_notes": (
            f"Analyzed at {now_iso()} | Payment: {payment_id} | "
            f"Rail: {payment_rail} | Status: {current_status} | "
            f"Errors ({len(errors)}): {error_summary} | Action: REQUEST_CLIENT_CORRECTION"
        ),
    }
