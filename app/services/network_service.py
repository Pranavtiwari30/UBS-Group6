"""
Network Service — deterministic checks for payment network failures.

Covers:
  - Timeout detection
  - Missing / incomplete acknowledgements
  - Ambiguous payment state (sent but not confirmed)
  - Retry storm detection (too many retries in short window)

All rules are deterministic — no AI involved.
"""

from typing import Tuple, List
from app.utils.logger import get_logger
from app.utils.helper import seconds_between

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# If the most recent retry was more than this many seconds ago → timeout
TIMEOUT_THRESHOLD_SECONDS = 300        # 5 minutes

# If there are this many or more retries → possible retry storm
MAX_ALLOWED_RETRIES = 5

# Acknowledgement statuses that are considered "confirmed"
CONFIRMED_ACK_STATUSES = {"ACK_RECEIVED", "CONFIRMED", "SETTLED", "SUCCESS"}

# Statuses that indicate the network is still uncertain
UNCERTAIN_ACK_STATUSES = {"PENDING", "IN_TRANSIT", "PARTIAL_ACK", "UNKNOWN"}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def check_missing_acknowledgement(
    network_acknowledgements: List[dict],
) -> Tuple[bool, str]:
    """
    Returns (issue_found, reason).
    An empty acknowledgement list or all-pending entries is a problem.
    """
    if not network_acknowledgements:
        return True, "No network acknowledgements received — payment state is unknown"

    statuses = [ack.get("status", "").upper() for ack in network_acknowledgements]
    confirmed = any(s in CONFIRMED_ACK_STATUSES for s in statuses)
    uncertain = any(s in UNCERTAIN_ACK_STATUSES for s in statuses)

    if not confirmed and uncertain:
        return True, f"All acknowledgements are in uncertain state: {statuses}"
    if not confirmed:
        return True, f"No confirmed acknowledgement found; statuses seen: {statuses}"
    return False, ""


def check_retry_overflow(prior_retry_events: List[dict]) -> Tuple[bool, str]:
    """Flag transactions with an excessive number of retry attempts."""
    count = len(prior_retry_events)
    if count >= MAX_ALLOWED_RETRIES:
        return True, (
            f"Transaction has been retried {count} times "
            f"(max allowed: {MAX_ALLOWED_RETRIES}) — possible retry storm"
        )
    return False, ""


def check_timeout(prior_retry_events: List[dict], submitted_timestamp: str) -> Tuple[bool, str]:
    """
    Detect timeout by checking elapsed time since the last retry (or submission).
    """
    if prior_retry_events:
        # Sort retries by timestamp and use the latest one
        sorted_retries = sorted(
            [e for e in prior_retry_events if e.get("timestamp")],
            key=lambda e: e["timestamp"],
        )
        last_event_ts = sorted_retries[-1]["timestamp"] if sorted_retries else submitted_timestamp
    else:
        last_event_ts = submitted_timestamp

    elapsed = seconds_between(last_event_ts, _now_iso_for_comparison())

    if elapsed is None:
        return False, "Could not determine elapsed time — timestamp parse error"

    if elapsed > TIMEOUT_THRESHOLD_SECONDS:
        return True, (
            f"No network response in {elapsed:.0f}s "
            f"(threshold: {TIMEOUT_THRESHOLD_SECONDS}s) — possible timeout"
        )
    return False, ""


def check_ambiguous_state(
    current_status: str, network_acknowledgements: List[dict]
) -> Tuple[bool, str]:
    """
    Detect the dangerous case where money may have left the bank but payment
    is not confirmed — e.g., PENDING status with a PARTIAL_ACK.
    """
    status_upper = (current_status or "").upper()
    ack_statuses = [ack.get("status", "").upper() for ack in network_acknowledgements]

    ambiguous = (
        status_upper in ("PENDING", "IN_TRANSIT", "HELD")
        and any(s in UNCERTAIN_ACK_STATUSES for s in ack_statuses)
    )
    if ambiguous:
        return True, (
            f"Transaction status is '{current_status}' with acknowledgements {ack_statuses} — "
            "funds may be in-flight without confirmation"
        )
    return False, ""


def analyze_network_issues(transaction: dict) -> dict:
    """
    Run all network checks and return a consolidated report.
    Called by the Network Failure Agent.
    """
    issues = []
    prior_retries = transaction.get("prior_retry_events", [])
    acks = transaction.get("network_acknowledgements", [])
    status = transaction.get("current_transaction_status", "")
    submitted_ts = transaction.get("submitted_timestamp", "")

    flagged, reason = check_missing_acknowledgement(acks)
    if flagged:
        issues.append({"check": "MISSING_ACK", "detail": reason})

    flagged, reason = check_retry_overflow(prior_retries)
    if flagged:
        issues.append({"check": "RETRY_OVERFLOW", "detail": reason})

    flagged, reason = check_timeout(prior_retries, submitted_ts)
    if flagged:
        issues.append({"check": "TIMEOUT", "detail": reason})

    flagged, reason = check_ambiguous_state(status, acks)
    if flagged:
        issues.append({"check": "AMBIGUOUS_STATE", "detail": reason})

    return {
        "network_issue_found": len(issues) > 0,
        "issues": issues,
        "retry_count": len(prior_retries),
    }


# ---------------------------------------------------------------------------
# Internal helper — using real UTC now for timeout comparisons
# ---------------------------------------------------------------------------
def _now_iso_for_comparison() -> str:
    from app.utils.helper import now_iso
    return now_iso()
