import pytest
from agents.network_agent import analyze, AgentAction, RiskLevel

# Helper function to generate a valid base flat payload
def make_base_payload():
    return {
        "payment_id": "PMT-TC-100",
        "payment_rail": "SWIFT",
        "network_acknowledgements": [],
        "current_transaction_status": "FAILED",
        "prior_retry_events": [],
        "submitted_timestamp": "2026-06-09T10:00:00Z",
        "exception_code": "CONNECTION_REFUSED"
    }

def test_priority_1_no_ack_unknown_status():
    payload = make_base_payload()
    payload["network_acknowledgements"] = []
    payload["current_transaction_status"] = "UNKNOWN"
    res = analyze(payload)
    assert res["action"] == AgentAction.HOLD_AND_RECONCILE.value
    assert res["risk_level"] == RiskLevel.HIGH.value
    assert res["confidence"] == 0.90
    assert res["automation_allowed"] is False

def test_priority_2_outage_exception():
    payload = make_base_payload()
    payload["exception_code"] = "GATEWAY_TIMEOUT"
    res = analyze(payload)
    assert res["action"] == AgentAction.WAIT_FOR_NETWORK_RECOVERY.value
    assert res["risk_level"] == RiskLevel.MEDIUM.value
    assert res["confidence"] == 0.85
    assert res["automation_allowed"] is True

def test_priority_3_failure_ack_no_retry():
    payload = make_base_payload()
    payload["network_acknowledgements"] = [
        {"status": "NACK", "code": "RJCT", "message": "Formatting error"}
    ]
    payload["current_transaction_status"] = "FAILED"
    res = analyze(payload)
    assert res["action"] == AgentAction.RECOMMEND_SAFE_RETRY.value
    assert res["risk_level"] == RiskLevel.LOW.value
    assert res["confidence"] == 0.95
    assert res["automation_allowed"] is True

def test_priority_4_retry_exists_uncertain_status():
    payload = make_base_payload()
    payload["prior_retry_events"] = [{"attempt": 1}]
    payload["current_transaction_status"] = "SENT" # uncertain
    res = analyze(payload)
    assert res["action"] == AgentAction.HOLD_AND_RECONCILE.value
    assert res["risk_level"] == RiskLevel.HIGH.value
    assert res["confidence"] == 0.95
    assert res["automation_allowed"] is False

def test_priority_5_validation_failure():
    # Missing required field
    payload = {
        "payment_id": "PMT-TC-100",
        "payment_rail": "SWIFT"
    }
    res = analyze(payload)
    assert res["action"] == AgentAction.MANUAL_REVIEW.value
    assert res["risk_level"] == RiskLevel.HIGH.value
    assert res["confidence"] == 1.00
    assert res["automation_allowed"] is False

def test_fallback_manual_review():
    # Valid payload, status FAILED (certain), prior retries exist (so Rule 3 is false),
    # no outage keywords (Rule 2 is false), some ACKs exist (so Rule 1 is false).
    payload = make_base_payload()
    payload["network_acknowledgements"] = [
        {"status": "RECEIVED", "code": "AC01", "message": "Pending"}
    ]
    payload["prior_retry_events"] = [{"attempt": 1}]
    res = analyze(payload)
    assert res["action"] == AgentAction.MANUAL_REVIEW.value
    assert res["risk_level"] == RiskLevel.HIGH.value
    assert res["confidence"] == 0.70
    assert res["automation_allowed"] is False
