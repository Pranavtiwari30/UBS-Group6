"""
Network Failure Agent — DETERMINISTIC / RULE-BASED

Handles payment exceptions caused by network or infrastructure failures.

Input schema (orchestrator slices to these fields only):
  payment_id, payment_rail, network_acknowledgements,
  current_transaction_status, prior_retry_events,
  submitted_timestamp, exception_code

MVP decision rules (Section 9.4 of orchestrator plan):
  1. No ACK + status UNKNOWN/PENDING     -> HOLD_AND_RECONCILE
  2. Exception code indicates rail outage -> WAIT_FOR_NETWORK_RECOVERY
  3. ACK confirms failure + no prior retry + no compliance signal
                                         -> RECOMMEND_SAFE_RETRY (confidence 0.90)
  4. Any uncertain prior retry            -> HOLD_AND_RECONCILE

MVP Actions:
  - HOLD_AND_RECONCILE         -> status or retry unclear, hold and reconcile
  - WAIT_FOR_NETWORK_RECOVERY  -> known rail/network outage in progress
  - RECOMMEND_SAFE_RETRY       -> confirmed failure, safe to retry once
  - MANUAL_REVIEW              -> ambiguous, excessive retries

NO AI / LLM used. All decisions are deterministic.
"""

from app.services.network_service import analyze_network_issues
from app.utils.logger import get_logger
from app.utils.helper import now_iso

logger = get_logger(__name__)

# Exception codes that indicate a known rail/network outage
RAIL_OUTAGE_CODES = {
    "RAIL_UNAVAILABLE", "RAIL_OUTAGE", "DOWNSTREAM_UNAVAILABLE",
    "NETWORK_OUTAGE", "GATEWAY_DOWN", "SETTLEMENT_SUSPENDED",
}

# ACK statuses that confirm the payment definitively failed
FAILED_ACK_STATUSES = {"REJECTED", "FAILED", "RETURNED", "DECLINED", "ERROR"}

# Statuses where we cannot safely retry
UNCERTAIN_STATUSES = {"UNKNOWN", "PENDING", "IN_TRANSIT", "PARTIAL"}

# Retry count beyond which we escalate regardless of other signals
MAX_SAFE_RETRIES = 5


def _is_rail_outage(exception_code: str) -> bool:
    """Check if the exception code indicates a known network/rail outage."""
    return exception_code.strip().upper() in RAIL_OUTAGE_CODES


def _ack_confirms_failure(network_acknowledgements: list) -> bool:
    """
    Returns True only if at least one ACK definitively confirms payment failed
    AND there are no uncertain/pending ACKs alongside it.
    """
    if not network_acknowledgements:
        return False
    statuses = {ack.get("status", "").upper() for ack in network_acknowledgements}
    has_confirmed_failure = bool(statuses & FAILED_ACK_STATUSES)
    has_uncertainty = bool(statuses & {"PENDING", "UNKNOWN", "PARTIAL_ACK"})
    return has_confirmed_failure and not has_uncertainty


def _has_uncertain_retries(prior_retry_events: list) -> bool:
    """
    Returns True if any prior retry has an uncertain outcome
    (e.g., we don't know if it went through).
    """
    uncertain_retry_statuses = {"UNKNOWN", "TIMEOUT", "PENDING", "PARTIAL"}
    for retry in prior_retry_events:
        status = str(retry.get("status", "")).upper()
        if status in uncertain_retry_statuses:
            return True
    return False


def analyze(transaction: dict) -> dict:
    """
    Analyze a transaction for network failure exceptions.

    Args:
        transaction: Agent-sliced dict with allowed fields only.

    Returns:
        MVP-compliant agent response dict.
    """
    payment_id = transaction.get("payment_id", "UNKNOWN")
    payment_rail = transaction.get("payment_rail", "")
    exception_code = (transaction.get("exception_code") or "").upper()
    current_status = (transaction.get("current_transaction_status") or "").upper()
    prior_retries = transaction.get("prior_retry_events") or []
    acks = transaction.get("network_acknowledgements") or []

    logger.info(f"[NetworkAgent] Analyzing transaction: {payment_id}")

    # ------------------------------------------------------------------
    # Rule 1: Rail outage — wait for recovery, don't retry blindly
    # ------------------------------------------------------------------
    if _is_rail_outage(exception_code):
        logger.warning(f"[NetworkAgent] {payment_id} — Rail outage detected: {exception_code}")
        return {
            "agent_name": "NetworkAgent",
            "classification": "rail_outage",
            "issue_detected": True,
            "root_cause": f"Payment rail '{payment_rail}' is unavailable: {exception_code}",
            "action": "WAIT_FOR_NETWORK_RECOVERY",
            "automation_allowed": False,
            "confidence": 0.95,
            "risk_level": "HIGH",
            "evidence": [
                f"exception_code={exception_code}",
                f"payment_rail={payment_rail}",
                f"current_transaction_status={current_status}",
            ],
            "explanation": (
                f"The payment rail '{payment_rail}' is currently experiencing an outage. "
                "Retrying now would fail again. Wait for network recovery before resubmitting."
            ),
            "next_steps": [
                f"Monitor the '{payment_rail}' network status dashboard",
                "Hold the transaction until the rail confirms recovery",
                "Do not retry until a successful ACK from the network is received",
                "Notify operations team of the rail outage",
            ],
            "escalation_required": True,
            "audit_notes": (
                f"Analyzed at {now_iso()} | Payment: {payment_id} | "
                f"Rail: {payment_rail} | Exception: {exception_code} | "
                "Action: WAIT_FOR_NETWORK_RECOVERY"
            ),
        }

    # ------------------------------------------------------------------
    # Rule 2: Excessive retries -> escalate to operations
    # ------------------------------------------------------------------
    if len(prior_retries) >= MAX_SAFE_RETRIES:
        return {
            "agent_name": "NetworkAgent",
            "classification": "retry_storm",
            "issue_detected": True,
            "root_cause": f"Transaction retried {len(prior_retries)} times — possible retry storm",
            "action": "MANUAL_REVIEW",
            "automation_allowed": False,
            "confidence": 0.90,
            "risk_level": "HIGH",
            "evidence": [
                f"prior_retry_events={len(prior_retries)} (max safe: {MAX_SAFE_RETRIES})",
                f"current_transaction_status={current_status}",
                f"exception_code={exception_code}",
            ],
            "explanation": (
                f"The payment has been retried {len(prior_retries)} times. "
                "This suggests a system retry loop. Manual intervention is required."
            ),
            "next_steps": [
                "Stop all automated retries immediately",
                "Investigate the root cause of the retry loop",
                "Escalate to the operations and engineering team",
                "Do not resume processing until root cause is identified",
            ],
            "escalation_required": True,
            "audit_notes": (
                f"Analyzed at {now_iso()} | Payment: {payment_id} | "
                f"Rail: {payment_rail} | Retries: {len(prior_retries)} | Action: MANUAL_REVIEW"
            ),
        }

    # ------------------------------------------------------------------
    # Rule 3: No ACK + uncertain status -> HOLD_AND_RECONCILE
    # Funds may be in-flight — never retry without confirmation
    # ------------------------------------------------------------------
    no_acks = len(acks) == 0
    status_uncertain = current_status in UNCERTAIN_STATUSES

    if no_acks and status_uncertain:
        logger.warning(f"[NetworkAgent] {payment_id} — No ACK + uncertain status -> HOLD_AND_RECONCILE")
        return {
            "agent_name": "NetworkAgent",
            "classification": "missing_acknowledgement",
            "issue_detected": True,
            "root_cause": (
                f"No network acknowledgements received and transaction status is '{current_status}' "
                "— payment outcome is unknown"
            ),
            "action": "HOLD_AND_RECONCILE",
            "automation_allowed": False,
            "confidence": 0.90,
            "risk_level": "HIGH",
            "evidence": [
                "network_acknowledgements=[]",
                f"current_transaction_status={current_status}",
                f"prior_retry_events={len(prior_retries)}",
                f"exception_code={exception_code}",
            ],
            "explanation": (
                "No acknowledgement has been received from the payment network and the "
                "transaction status is uncertain. Retrying now risks creating a duplicate debit."
            ),
            "next_steps": [
                "Query the payment network directly for the transaction outcome",
                "Hold this transaction in suspense pending network confirmation",
                "Do not retry until a definitive ACK (success or failure) is received",
                "Escalate to operations if no response within 30 minutes",
            ],
            "escalation_required": True,
            "audit_notes": (
                f"Analyzed at {now_iso()} | Payment: {payment_id} | "
                f"Rail: {payment_rail} | Status: {current_status} | "
                f"ACKs: 0 | Retries: {len(prior_retries)} | Action: HOLD_AND_RECONCILE"
            ),
        }

    # ------------------------------------------------------------------
    # Rule 4: Uncertain prior retries -> HOLD_AND_RECONCILE
    # One of the retries may have gone through without confirmation
    # ------------------------------------------------------------------
    if _has_uncertain_retries(prior_retries):
        logger.warning(f"[NetworkAgent] {payment_id} — Uncertain retries -> HOLD_AND_RECONCILE")
        ack_statuses = [a.get("status") for a in acks]
        return {
            "agent_name": "NetworkAgent",
            "classification": "uncertain_retry_state",
            "issue_detected": True,
            "root_cause": (
                f"{len(prior_retries)} prior retry/retries with uncertain outcomes — "
                "cannot confirm whether a previous attempt succeeded"
            ),
            "action": "HOLD_AND_RECONCILE",
            "automation_allowed": False,
            "confidence": 0.85,
            "risk_level": "HIGH",
            "evidence": [
                f"prior_retry_events={len(prior_retries)}",
                "uncertain_retry_statuses detected (TIMEOUT/UNKNOWN)",
                f"network_acknowledgements={ack_statuses}",
                f"current_transaction_status={current_status}",
            ],
            "explanation": (
                "One or more prior retry attempts have uncertain outcomes. "
                "Retrying again risks a duplicate payment. Reconcile all prior attempts first."
            ),
            "next_steps": [
                "Reconcile each prior retry attempt with the payment network",
                "Confirm which attempts (if any) succeeded",
                "Hold the payment until reconciliation is complete",
                "Only retry if all prior attempts are confirmed as failed",
            ],
            "escalation_required": True,
            "audit_notes": (
                f"Analyzed at {now_iso()} | Payment: {payment_id} | "
                f"Rail: {payment_rail} | Retries: {len(prior_retries)} | "
                f"ACKs: {ack_statuses} | Action: HOLD_AND_RECONCILE"
            ),
        }

    # ------------------------------------------------------------------
    # Rule 5: ACK confirms definitive failure + clean retry history
    # -> RECOMMEND_SAFE_RETRY
    # ------------------------------------------------------------------
    if _ack_confirms_failure(acks) and len(prior_retries) == 0:
        ack_statuses = [a.get("status") for a in acks]
        logger.info(f"[NetworkAgent] {payment_id} — Confirmed failure, no retries -> RECOMMEND_SAFE_RETRY")
        return {
            "agent_name": "NetworkAgent",
            "classification": "confirmed_network_failure",
            "issue_detected": True,
            "root_cause": (
                f"Payment network returned a definitive failure ACK: {ack_statuses}. "
                "No prior retries. A single retry is safe."
            ),
            "action": "RECOMMEND_SAFE_RETRY",
            "automation_allowed": False,   # MVP recommends only — never auto-executes
            "confidence": 0.90,
            "risk_level": "MEDIUM",
            "evidence": [
                f"network_acknowledgements={ack_statuses}",
                "prior_retry_events=0 (no prior retries)",
                f"current_transaction_status={current_status}",
                f"payment_rail={payment_rail}",
            ],
            "explanation": (
                "The payment network has definitively rejected this transaction. "
                "There are no prior retry attempts, so a single retry is considered safe."
            ),
            "next_steps": [
                "Confirm the network ACK is a definitive rejection (not a timeout)",
                "Initiate a single retry of the payment",
                "Monitor the retry for a final ACK within the SLA window",
                "Escalate if the retry also fails",
            ],
            "escalation_required": False,
            "audit_notes": (
                f"Analyzed at {now_iso()} | Payment: {payment_id} | "
                f"Rail: {payment_rail} | ACKs: {ack_statuses} | "
                f"Retries: 0 | Action: RECOMMEND_SAFE_RETRY"
            ),
        }

    # ------------------------------------------------------------------
    # Default fallback: any remaining ambiguity -> HOLD_AND_RECONCILE
    # ------------------------------------------------------------------
    network_report = analyze_network_issues(transaction)
    ack_statuses = [a.get("status") for a in acks]
    all_issues = " | ".join(i["detail"] for i in network_report.get("issues", []))

    logger.warning(f"[NetworkAgent] {payment_id} — Fallback HOLD_AND_RECONCILE: {all_issues}")
    return {
        "agent_name": "NetworkAgent",
        "classification": "network_failure_ambiguous",
        "issue_detected": True,
        "root_cause": f"Network failure with ambiguous state: {all_issues or exception_code}",
        "action": "HOLD_AND_RECONCILE",
        "automation_allowed": False,
        "confidence": 0.80,
        "risk_level": "HIGH",
        "evidence": [
            f"exception_code={exception_code}",
            f"current_transaction_status={current_status}",
            f"network_acknowledgements={ack_statuses}",
            f"prior_retry_events={len(prior_retries)}",
        ],
        "explanation": (
            "The network failure cannot be definitively classified. "
            "Holding for reconciliation is the safest action."
        ),
        "next_steps": [
            "Query the payment network for the current transaction status",
            "Hold the payment until a definitive outcome is available",
            "Escalate to operations team for manual reconciliation",
        ],
        "escalation_required": True,
        "audit_notes": (
            f"Analyzed at {now_iso()} | Payment: {payment_id} | "
            f"Rail: {payment_rail} | Status: {current_status} | "
            f"ACKs: {ack_statuses} | Action: HOLD_AND_RECONCILE"
        ),
    }
