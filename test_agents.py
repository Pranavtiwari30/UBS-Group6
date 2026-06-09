"""
Smoke test — validates all 3 rule-based agents against the MVP plan schema.
Run: $env:PYTHONIOENCODING="utf-8"; python test_agents.py

Validates:
  - Correct MVP action names (REQUEST_CLIENT_CORRECTION, CANCEL_DUPLICATE, etc.)
  - New output fields: classification, action, automation_allowed, risk_level,
    evidence, explanation, next_steps
  - Orchestrator plan rule compliance (Section 9.1 – 9.4)
  - Both 'ifsc' and 'ifsc_code' field names
  - client_contact_history handling
  - Uncertain status -> MANUAL_REVIEW
  - Sanctions pre-screening
"""

import sys

# ---------------------------------------------------------------------------
# Agent imports
# ---------------------------------------------------------------------------
from app.agents.beneficiary_agent import analyze as ba
from app.agents.duplicate_payment_agent import analyze as da
from app.agents.network_failure_agent import analyze as na
from app.services.sanctions_service import run_sanctions_screening, check_high_value
from app.utils.helper import parse_timestamp, seconds_between, normalize_string, safe_get

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []


def check(label, condition, got=None):
    icon = PASS if condition else FAIL
    msg = f"  {icon}  {label}"
    if not condition and got is not None:
        msg += f"\n         Got: {got}"
    print(msg)
    results.append(condition)


def section(title):
    print(f"\n{'-' * 62}")
    print(f"  {title}")
    print(f"{'-' * 62}")


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

TX_BAD_IFSC = {
    "payment_id": "T-001", "client_id": "CLT-1",
    "payment_rail": "NEFT", "amount": 15000.0, "currency": "INR",
    "beneficiary_details": {"name": "Test User", "account_number": "12345678901", "ifsc_code": "BADIFSC999"},
    "submitted_timestamp": "2024-01-15T10:00:00+00:00",
    "exception_code": "INVALID_BENEFICIARY", "current_transaction_status": "FAILED",
    "prior_retry_events": [], "compliance_hold_status": "NONE",
    "network_acknowledgements": [], "client_contact_history": [],
}

TX_BAD_IFSC_MVP_FIELD = {  # Uses 'ifsc' (MVP canonical) instead of 'ifsc_code'
    "payment_id": "T-002", "client_id": "CLT-2",
    "payment_rail": "NEFT", "amount": 5000.0, "currency": "INR",
    "beneficiary_details": {"name": "MVP User", "account_number": "12345678901", "ifsc": "BADIFSXXX"},
    "submitted_timestamp": "2024-01-15T10:00:00+00:00",
    "exception_code": "INVALID_BENEFICIARY", "current_transaction_status": "FAILED",
    "prior_retry_events": [], "compliance_hold_status": "NONE",
    "network_acknowledgements": [], "client_contact_history": [],
}

TX_GOOD_IFSC = {
    "payment_id": "T-003", "client_id": "CLT-3",
    "payment_rail": "NEFT", "amount": 5000.0, "currency": "INR",
    "beneficiary_details": {"name": "Good User", "account_number": "12345678901", "ifsc_code": "HDFC0001234"},
    "submitted_timestamp": "2024-01-15T10:00:00+00:00",
    "exception_code": "NONE", "current_transaction_status": "FAILED",
    "prior_retry_events": [], "compliance_hold_status": "NONE",
    "network_acknowledgements": [], "client_contact_history": [],
}

TX_GOOD_UPI = {
    "payment_id": "T-004", "client_id": "CLT-4",
    "payment_rail": "UPI", "amount": 500.0, "currency": "INR",
    "beneficiary_details": {"name": "Asha Rao", "upi_id": "asha@upi"},
    "submitted_timestamp": "2024-01-15T10:00:00+00:00",
    "exception_code": "NONE", "current_transaction_status": "FAILED",
    "prior_retry_events": [], "compliance_hold_status": "NONE",
    "network_acknowledgements": [], "client_contact_history": [],
}

TX_BAD_UPI = {
    "payment_id": "T-005", "client_id": "CLT-5",
    "payment_rail": "UPI", "amount": 500.0, "currency": "INR",
    "beneficiary_details": {"name": "UPI User", "upi_id": "not_valid_upi"},
    "submitted_timestamp": "2024-01-15T10:00:00+00:00",
    "exception_code": "INVALID_BENEFICIARY", "current_transaction_status": "FAILED",
    "prior_retry_events": [], "compliance_hold_status": "NONE",
    "network_acknowledgements": [], "client_contact_history": [],
}

TX_PENDING_STATUS = {  # Rule: PENDING status -> MANUAL_REVIEW
    "payment_id": "T-006", "client_id": "CLT-6",
    "payment_rail": "NEFT", "amount": 5000.0, "currency": "INR",
    "beneficiary_details": {"name": "User", "account_number": "12345678901", "ifsc_code": "BADIFSC999"},
    "submitted_timestamp": "2024-01-15T10:00:00+00:00",
    "exception_code": "INVALID_BENEFICIARY", "current_transaction_status": "PENDING",
    "prior_retry_events": [], "compliance_hold_status": "NONE",
    "network_acknowledgements": [], "client_contact_history": [],
}

TX_PRIOR_CONTACT = {  # Rule: prior open contact -> MANUAL_REVIEW
    "payment_id": "T-007", "client_id": "CLT-7",
    "payment_rail": "UPI", "amount": 500.0, "currency": "INR",
    "beneficiary_details": {"name": "User", "upi_id": "bad_upi"},
    "submitted_timestamp": "2024-01-15T10:00:00+00:00",
    "exception_code": "INVALID_BENEFICIARY", "current_transaction_status": "FAILED",
    "prior_retry_events": [], "compliance_hold_status": "NONE",
    "network_acknowledgements": [],
    "client_contact_history": [{"status": "OPEN", "created_at": "2024-01-14T10:00:00+00:00"}],
}

TX_DUPLICATE = {
    "payment_id": "T-008", "client_id": "CLT-8",
    "payment_rail": "UPI", "amount": 2500.0, "currency": "INR",
    "beneficiary_details": {"name": "Sneha Reddy", "upi_id": "sneha@okicici"},
    "submitted_timestamp": "2024-01-15T11:00:00+00:00",
    "exception_code": "DUPLICATE_PAYMENT", "current_transaction_status": "FAILED",
    "prior_retry_events": [
        {"retry_id": "R1", "timestamp": "2024-01-15T11:01:00+00:00", "status": "RETRIED"},
        {"retry_id": "R2", "timestamp": "2024-01-15T11:01:10+00:00", "status": "RETRIED"},
        {"retry_id": "R3", "timestamp": "2024-01-15T11:01:20+00:00", "status": "RETRIED"},
    ],
    "compliance_hold_status": "NONE", "network_acknowledgements": [],
}

TX_DUPLICATE_UNKNOWN_STATUS = {  # Rule: UNKNOWN status + duplicate -> HOLD_AND_RECONCILE
    "payment_id": "T-009", "client_id": "CLT-9",
    "payment_rail": "UPI", "amount": 2500.0, "currency": "INR",
    "beneficiary_details": {"name": "Sneha Reddy", "upi_id": "sneha@okicici"},
    "submitted_timestamp": "2024-01-15T11:00:00+00:00",
    "exception_code": "DUPLICATE_PAYMENT", "current_transaction_status": "UNKNOWN",
    "prior_retry_events": [
        {"retry_id": "R1", "timestamp": "2024-01-15T11:01:00+00:00", "status": "RETRIED"},
        {"retry_id": "R2", "timestamp": "2024-01-15T11:01:10+00:00", "status": "RETRIED"},
    ],
    "compliance_hold_status": "NONE", "network_acknowledgements": [],
}

TX_DUPLICATE_MISSING_FIELDS = {  # Rule: missing fields -> MANUAL_REVIEW
    "payment_id": "T-010",
    "payment_rail": "UPI",
    "exception_code": "DUPLICATE_PAYMENT", "current_transaction_status": "FAILED",
    # Missing: amount, client_id, beneficiary_details, submitted_timestamp
}

TX_RETRY_STORM = {  # Rule: 5+ retries -> MANUAL_REVIEW
    "payment_id": "T-011", "client_id": "CLT-11",
    "payment_rail": "IMPS", "amount": 10000.0, "currency": "INR",
    "beneficiary_details": {"name": "Corp Ltd", "account_number": "55566677788", "ifsc_code": "AXIS0001234"},
    "submitted_timestamp": "2024-01-15T14:00:00+00:00",
    "exception_code": "NETWORK_TIMEOUT", "current_transaction_status": "PENDING",
    "prior_retry_events": [
        {"retry_id": f"R{i}", "timestamp": f"2024-01-15T14:0{i}:00+00:00", "status": "TIMEOUT"}
        for i in range(1, 6)
    ],
    "compliance_hold_status": "NONE", "network_acknowledgements": [],
}

TX_RAIL_OUTAGE = {  # Rule: RAIL_UNAVAILABLE -> WAIT_FOR_NETWORK_RECOVERY
    "payment_id": "T-012", "client_id": "CLT-12",
    "payment_rail": "RTGS", "amount": 50000.0, "currency": "INR",
    "beneficiary_details": {"name": "Infra Corp", "account_number": "11223344556", "ifsc_code": "SBIN0001234"},
    "submitted_timestamp": "2024-01-15T08:00:00+00:00",
    "exception_code": "RAIL_UNAVAILABLE", "current_transaction_status": "FAILED",
    "prior_retry_events": [],
    "compliance_hold_status": "NONE", "network_acknowledgements": [],
}

TX_NO_ACK_PENDING = {  # Rule: No ACK + PENDING -> HOLD_AND_RECONCILE
    "payment_id": "T-013", "client_id": "CLT-13",
    "payment_rail": "NEFT", "amount": 10000.0, "currency": "INR",
    "beneficiary_details": {"name": "Test", "account_number": "11223344556", "ifsc_code": "SBIN0001234"},
    "submitted_timestamp": "2024-01-15T08:00:00+00:00",
    "exception_code": "NETWORK_TIMEOUT", "current_transaction_status": "PENDING",
    "prior_retry_events": [],
    "compliance_hold_status": "NONE", "network_acknowledgements": [],
}

TX_CONFIRMED_FAILURE = {  # Rule: definitive failure ACK, 0 retries -> RECOMMEND_SAFE_RETRY
    "payment_id": "T-014", "client_id": "CLT-14",
    "payment_rail": "NEFT", "amount": 10000.0, "currency": "INR",
    "beneficiary_details": {"name": "Test", "account_number": "11223344556", "ifsc_code": "SBIN0001234"},
    "submitted_timestamp": "2024-01-15T08:00:00+00:00",
    "exception_code": "NETWORK_TIMEOUT", "current_transaction_status": "FAILED",
    "prior_retry_events": [],
    "compliance_hold_status": "NONE",
    "network_acknowledgements": [{"status": "REJECTED", "timestamp": "2024-01-15T08:01:00+00:00"}],
}

TX_UNCERTAIN_RETRY = {  # Rule: uncertain retry status -> HOLD_AND_RECONCILE
    "payment_id": "T-015", "client_id": "CLT-15",
    "payment_rail": "NEFT", "amount": 10000.0, "currency": "INR",
    "beneficiary_details": {"name": "Test", "account_number": "11223344556", "ifsc_code": "SBIN0001234"},
    "submitted_timestamp": "2024-01-15T08:00:00+00:00",
    "exception_code": "NETWORK_TIMEOUT", "current_transaction_status": "FAILED",
    "prior_retry_events": [
        {"retry_id": "R1", "timestamp": "2024-01-15T08:02:00+00:00", "status": "TIMEOUT"},
    ],
    "compliance_hold_status": "NONE",
    "network_acknowledgements": [{"status": "REJECTED", "timestamp": "2024-01-15T08:01:00+00:00"}],
}

TX_IRAN_SANCTIONS = {
    "payment_id": "T-016", "client_id": "CLT-16",
    "payment_rail": "SWIFT", "amount": 75000.0, "currency": "USD",
    "beneficiary_details": {"name": "Tehran Bank International", "country": "IR", "swift_code": "TEHRIR22XXX"},
    "submitted_timestamp": "2024-01-15T12:00:00+00:00",
    "exception_code": "SANCTION_HIT", "current_transaction_status": "HELD",
    "prior_retry_events": [], "compliance_hold_status": "SANCTION_HOLD",
    "network_acknowledgements": [],
}


# ===========================================================================
# 1. BENEFICIARY AGENT
# ===========================================================================
section("1. BeneficiaryAgent — field validation")

r = ba(TX_BAD_IFSC)
check("Bad ifsc_code -> issue_detected=True",         r["issue_detected"] is True,                   r)
check("Bad ifsc_code -> action=REQUEST_CLIENT_CORRECTION",
      r["action"] == "REQUEST_CLIENT_CORRECTION",                                                     r["action"])
check("Bad ifsc_code -> confidence==1.0",             r["confidence"] == 1.0,                         r["confidence"])
check("Output has 'classification' field",            "classification" in r,                           list(r.keys()))
check("Output has 'evidence' list",                   isinstance(r.get("evidence"), list),             r.get("evidence"))
check("Output has 'next_steps' list",                 isinstance(r.get("next_steps"), list),           r.get("next_steps"))
check("Output has 'explanation' string",              isinstance(r.get("explanation"), str),           r.get("explanation"))
check("automation_allowed=False",                     r["automation_allowed"] is False,                r["automation_allowed"])

r = ba(TX_BAD_IFSC_MVP_FIELD)
check("MVP 'ifsc' field name (not ifsc_code) -> caught",
      r["issue_detected"] is True,                                                                     r)

r = ba(TX_GOOD_IFSC)
check("Good IFSC -> issue_detected=False",            r["issue_detected"] is False,                   r)
check("Good IFSC -> action=PROCEED",                  r["action"] == "PROCEED",                       r["action"])

r = ba(TX_GOOD_UPI)
check("Good UPI -> issue_detected=False",             r["issue_detected"] is False,                   r)

r = ba(TX_BAD_UPI)
check("Bad UPI -> REQUEST_CLIENT_CORRECTION",         r["action"] == "REQUEST_CLIENT_CORRECTION",     r["action"])

section("1b. BeneficiaryAgent — plan-specific rules")

r = ba(TX_PENDING_STATUS)
check("PENDING status -> action=MANUAL_REVIEW",       r["action"] == "MANUAL_REVIEW",                 r["action"])
check("PENDING status -> escalation_required=True",   r["escalation_required"] is True,               r)

r = ba(TX_PRIOR_CONTACT)
check("Prior open contact -> action=MANUAL_REVIEW",   r["action"] == "MANUAL_REVIEW",                 r["action"])
check("Prior contact -> issue_detected=True",         r["issue_detected"] is True,                    r)


# ===========================================================================
# 2. DUPLICATE PAYMENT AGENT
# ===========================================================================
section("2. DuplicatePaymentAgent — core detection")

r = da(TX_DUPLICATE)
check("Confirmed duplicate -> issue_detected=True",   r["issue_detected"] is True,                   r)
check("Confirmed duplicate -> action=CANCEL_DUPLICATE",
      r["action"] == "CANCEL_DUPLICATE",                                                              r["action"])
check("Output has 'classification'",                  "classification" in r,                          r)
check("Output has 'evidence' list",                   isinstance(r.get("evidence"), list),            r)
check("automation_allowed=False",                     r["automation_allowed"] is False,               r)
check("risk_level present",                           r.get("risk_level") in ("LOW", "MEDIUM", "HIGH", "CRITICAL"), r.get("risk_level"))

section("2b. DuplicatePaymentAgent — plan-specific rules")

r = da(TX_DUPLICATE_UNKNOWN_STATUS)
check("UNKNOWN status + duplicate -> HOLD_AND_RECONCILE",
      r["action"] == "HOLD_AND_RECONCILE",                                                            r["action"])
check("UNKNOWN status -> escalation_required=True",   r["escalation_required"] is True,              r)

r = da(TX_DUPLICATE_MISSING_FIELDS)
check("Missing fields -> action=MANUAL_REVIEW",       r["action"] == "MANUAL_REVIEW",                r["action"])
check("Missing fields -> issue_detected=True",        r["issue_detected"] is True,                   r)


# ===========================================================================
# 3. NETWORK FAILURE AGENT
# ===========================================================================
section("3. NetworkAgent — plan decision rules")

r = na(TX_RAIL_OUTAGE)
check("RAIL_UNAVAILABLE -> WAIT_FOR_NETWORK_RECOVERY",
      r["action"] == "WAIT_FOR_NETWORK_RECOVERY",                                                     r["action"])
check("Rail outage -> escalation_required=True",      r["escalation_required"] is True,              r)
check("Output has 'classification'",                  "classification" in r,                          r)
check("Output has 'next_steps'",                      isinstance(r.get("next_steps"), list),          r)

r = na(TX_NO_ACK_PENDING)
check("No ACK + PENDING -> HOLD_AND_RECONCILE",       r["action"] == "HOLD_AND_RECONCILE",           r["action"])
check("No ACK -> issue_detected=True",                r["issue_detected"] is True,                   r)

r = na(TX_UNCERTAIN_RETRY)
check("Uncertain retry -> HOLD_AND_RECONCILE",        r["action"] == "HOLD_AND_RECONCILE",           r["action"])

r = na(TX_CONFIRMED_FAILURE)
check("Confirmed failure + 0 retries -> RECOMMEND_SAFE_RETRY",
      r["action"] == "RECOMMEND_SAFE_RETRY",                                                          r["action"])
check("Safe retry -> confidence >= 0.90",             r["confidence"] >= 0.90,                       r["confidence"])
check("Safe retry -> automation_allowed=False",       r["automation_allowed"] is False,               r)

r = na(TX_RETRY_STORM)
check("5 retries -> MANUAL_REVIEW",                   r["action"] == "MANUAL_REVIEW",                r["action"])
check("Retry storm -> escalation_required=True",      r["escalation_required"] is True,              r)


# ===========================================================================
# 4. SANCTIONS SERVICE (pre-screening layer)
# ===========================================================================
section("4. SanctionsService — deterministic pre-screening")

r = run_sanctions_screening(TX_IRAN_SANCTIONS)
check("Iran SWIFT -> sanctions_hit=True",             r["sanctions_hit"] is True,                    r)
check("Iran -> SANCTIONED_COUNTRY hit",
      any(h["check"] == "SANCTIONED_COUNTRY" for h in r["hits"]),                                    r["hits"])
check("Tehran Bank -> SANCTIONED_ENTITY hit",
      any(h["check"] == "SANCTIONED_ENTITY" for h in r["hits"]),                                     r["hits"])

flagged, _ = check_high_value(9500, "USD")
check("USD 9,500 -> structuring flag",                flagged is True,                               "")
flagged, _ = check_high_value(10001, "USD")
check("USD 10,001 -> high-value flag",                flagged is True,                               "")
flagged, _ = check_high_value(100, "USD")
check("USD 100 -> no flag",                           flagged is False,                              "")


# ===========================================================================
# 5. UTILITY FUNCTIONS
# ===========================================================================
section("5. Utility functions")

ts = parse_timestamp("2024-01-15T10:00:00+00:00")
check("parse_timestamp -> not None",                  ts is not None,                                ts)
secs = seconds_between("2024-01-15T10:00:00+00:00", "2024-01-15T10:05:00+00:00")
check("seconds_between -> 300.0",                     secs == 300.0,                                 secs)
check("normalize_string",                             normalize_string("  hdfc0001234  ") == "HDFC0001234", "")
check("safe_get nested",                              safe_get({"a": {"b": 42}}, "a", "b") == 42,   "")
check("safe_get missing -> default",                  safe_get({}, "x", "y", default="Z") == "Z",   "")


# ===========================================================================
# SUMMARY
# ===========================================================================
total = len(results)
passed = sum(results)
failed = total - passed

print(f"\n{'=' * 62}")
print(f"  RESULTS: {passed}/{total} passed", end="")
if failed:
    print(f"  <-- {failed} FAILED")
else:
    print("  ALL PASSED")
print(f"{'=' * 62}\n")

sys.exit(0 if failed == 0 else 1)
