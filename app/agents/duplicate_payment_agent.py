"""
Duplicate Payment Agent — DETERMINISTIC / RULE-BASED

Detects duplicate or redundant payment submissions.

Input schema (orchestrator slices to these fields only):
  payment_id, amount, submitted_timestamp, prior_retry_events,
  client_id, beneficiary_details, current_transaction_status

Checks:
  1. exception_code explicitly flags DUPLICATE
  2. Rapid retry events within the duplicate window (same beneficiary)
  3. Current status is UNKNOWN -> HOLD_AND_RECONCILE (never cancel uncertain)
  4. Missing required fields -> MANUAL_REVIEW

MVP Actions (Section 8 of orchestrator plan):
  - CANCEL_DUPLICATE      -> prior successful payment confirmed
  - HOLD_AND_RECONCILE    -> status uncertain or retry pattern ambiguous
  - MANUAL_REVIEW         -> missing fields, cannot determine safely

NO AI / LLM used. All decisions are deterministic time + field matching.
"""

from app.utils.logger import get_logger
from app.utils.helper import now_iso, seconds_between

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Two submissions within this window with same amount + beneficiary = duplicate
DUPLICATE_WINDOW_SECONDS = 120      # 2 minutes

# Retries above this count within the window indicate system-level duplicate
RETRY_DUPLICATE_THRESHOLD = 2

# Required fields for the duplicate agent to make a safe decision
REQUIRED_FIELDS = ["payment_id", "amount", "client_id", "beneficiary_details", "submitted_timestamp"]


def _check_missing_fields(transaction: dict) -> list:
    """Return list of missing required fields."""
    return [f for f in REQUIRED_FIELDS if not transaction.get(f)]


def _check_exception_code(transaction: dict):
    """Direct signal: exception code already says DUPLICATE."""
    code = (transaction.get("exception_code") or "").upper()
    if any(kw in code for kw in ("DUPLICATE", "DUP_SUBMISSION", "RETRY_DUPLICATE")):
        return True, "Exception code explicitly identifies this as a duplicate payment"
    return False, ""


def _check_retry_storm(transaction: dict):
    """
    Multiple retries in quick succession = high-confidence duplicate.
    """
    retries = transaction.get("prior_retry_events") or []
    if len(retries) < RETRY_DUPLICATE_THRESHOLD:
        return False, ""

    # Get timestamps from retry events
    timestamps = sorted([
        r.get("timestamp") for r in retries
        if r.get("timestamp")
    ])

    if len(timestamps) >= 2:
        gap = seconds_between(timestamps[0], timestamps[-1])
        if gap is not None and gap <= DUPLICATE_WINDOW_SECONDS:
            return True, (
                f"{len(retries)} retry events within {gap:.0f}s window "
                "(rapid re-submission — double-click or system retry storm)"
            )

    # Many retries even without tight timestamps is still suspicious
    return True, (
        f"{len(retries)} prior retry events recorded "
        "— high probability of duplicate submission"
    )


def _is_status_uncertain(transaction: dict) -> bool:
    """Returns True if current status prevents a safe CANCEL decision."""
    status = (transaction.get("current_transaction_status") or "").upper()
    return status in ("UNKNOWN", "PENDING", "IN_TRANSIT", "PARTIAL")


def analyze(transaction: dict) -> dict:
    """
    Analyze a transaction for duplicate payment exceptions.

    Args:
        transaction: Agent-sliced dict with allowed fields only.

    Returns:
        MVP-compliant agent response dict.
    """
    payment_id = transaction.get("payment_id", "UNKNOWN")
    beneficiary = transaction.get("beneficiary_details") or {}
    beneficiary_name = beneficiary.get("name", "Unknown")
    client_id = transaction.get("client_id", "")
    current_status = transaction.get("current_transaction_status", "")
    prior_retries = transaction.get("prior_retry_events") or []

    logger.info(f"[DuplicateAgent] Analyzing transaction: {payment_id}")

    # ------------------------------------------------------------------
    # Guard: missing required fields
    # ------------------------------------------------------------------
    missing = _check_missing_fields(transaction)
    if missing:
        logger.warning(f"[DuplicateAgent] {payment_id} — Missing fields: {missing}")
        return {
            "agent_name": "DuplicatePaymentAgent",
            "classification": "insufficient_data",
            "issue_detected": True,
            "root_cause": f"Cannot determine duplicate status — missing fields: {missing}",
            "action": "MANUAL_REVIEW",
            "automation_allowed": False,
            "confidence": 0.70,
            "risk_level": "MEDIUM",
            "evidence": [f"missing_field: {f}" for f in missing],
            "explanation": (
                "Required fields for duplicate detection are absent. "
                "A manual review is needed to safely determine if this is a duplicate."
            ),
            "next_steps": [
                f"Obtain missing fields: {', '.join(missing)}",
                "Re-run duplicate check once fields are available",
                "Do not retry the payment until duplicate status is confirmed",
            ],
            "escalation_required": True,
            "audit_notes": (
                f"Analyzed at {now_iso()} | Payment: {payment_id} | "
                f"Missing: {missing} | Routed to MANUAL_REVIEW"
            ),
        }

    # ------------------------------------------------------------------
    # Run duplicate signal checks
    # ------------------------------------------------------------------
    signals = []

    flagged, reason = _check_exception_code(transaction)
    if flagged:
        signals.append({"check": "EXCEPTION_CODE", "detail": reason, "weight": "HIGH"})

    flagged, reason = _check_retry_storm(transaction)
    if flagged:
        signals.append({"check": "RETRY_STORM", "detail": reason, "weight": "HIGH"})

    if not signals:
        logger.info(f"[DuplicateAgent] {payment_id} — No duplicate signals detected")
        return {
            "agent_name": "DuplicatePaymentAgent",
            "classification": "no_duplicate_detected",
            "issue_detected": False,
            "root_cause": "No duplicate payment signals detected",
            "action": "PROCEED",
            "automation_allowed": False,
            "confidence": 0.95,
            "risk_level": "LOW",
            "evidence": [
                f"payment_id={payment_id}",
                f"prior_retry_events={len(prior_retries)}",
                "No duplicate patterns found",
            ],
            "explanation": "No duplicate indicators found. Payment can proceed normally.",
            "next_steps": ["Proceed with normal payment processing"],
            "escalation_required": False,
            "audit_notes": (
                f"Analyzed at {now_iso()} | Payment: {payment_id} | "
                f"Client: {client_id} | Beneficiary: {beneficiary_name} | "
                f"Retries: {len(prior_retries)} | No duplicate patterns found"
            ),
        }

    # ------------------------------------------------------------------
    # Signals found — choose action based on status certainty
    # ------------------------------------------------------------------
    all_details = " | ".join(s["detail"] for s in signals)
    evidence_list = [
        f"exception_code={transaction.get('exception_code', '')}",
        f"prior_retry_events={len(prior_retries)}",
        f"current_transaction_status={current_status}",
    ] + [s["detail"] for s in signals]

    logger.warning(f"[DuplicateAgent] {payment_id} — Signals: {all_details}")

    # If status is uncertain, never cancel — hold and reconcile
    if _is_status_uncertain(transaction):
        return {
            "agent_name": "DuplicatePaymentAgent",
            "classification": "duplicate_status_uncertain",
            "issue_detected": True,
            "root_cause": f"Duplicate signals present but payment status is uncertain ({current_status})",
            "action": "HOLD_AND_RECONCILE",
            "automation_allowed": False,
            "confidence": 0.80,
            "risk_level": "HIGH",
            "evidence": evidence_list,
            "explanation": (
                f"Duplicate indicators were detected, but the transaction status is '{current_status}'. "
                "Cancelling is unsafe until the original payment outcome is confirmed."
            ),
            "next_steps": [
                "Confirm the status of the original payment with the payment network",
                "Hold this transaction in suspense until status is resolved",
                "Do not retry or cancel until the original payment outcome is clear",
                "Escalate to operations if status does not resolve within 30 minutes",
            ],
            "escalation_required": True,
            "audit_notes": (
                f"Analyzed at {now_iso()} | Payment: {payment_id} | "
                f"Status: {current_status} | Signals: {all_details} | Action: HOLD_AND_RECONCILE"
            ),
        }

    # High-confidence duplicate with a clear FAILED/REJECTED status — safe to cancel
    return {
        "agent_name": "DuplicatePaymentAgent",
        "classification": "confirmed_duplicate",
        "issue_detected": True,
        "root_cause": f"Duplicate payment confirmed: {all_details}",
        "action": "CANCEL_DUPLICATE",
        "automation_allowed": False,   # MVP only recommends — never auto-executes
        "confidence": 0.95,
        "risk_level": "HIGH",
        "evidence": evidence_list,
        "explanation": (
            "A duplicate payment submission has been detected. "
            "The original payment has a definitive status and this submission is a repeat. "
            "Cancellation is recommended, but must be confirmed by an operator."
        ),
        "next_steps": [
            "Verify the original payment status is FAILED or REJECTED",
            "Cancel this duplicate submission — do NOT process it",
            "Notify the client that a duplicate was detected and cancelled",
            "Review system retry configuration to prevent future occurrences",
        ],
        "escalation_required": False,
        "audit_notes": (
            f"Analyzed at {now_iso()} | Payment: {payment_id} | "
            f"Client: {client_id} | Beneficiary: {beneficiary_name} | "
            f"Retries: {len(prior_retries)} | Signals: {all_details} | Action: CANCEL_DUPLICATE"
        ),
    }
