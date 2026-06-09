import os
import json
from typing import Any

from fastapi import HTTPException


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def load_json_file(filename: str) -> list[dict[str, Any]]:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def load_mock_data() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    exceptions = load_json_file("exceptions.json")
    payments = {payment["payment_id"]: payment for payment in load_json_file("payments.json")}
    compliance = {record["user_id"]: record for record in load_json_file("compliance.json")}
    return exceptions, payments, compliance


def get_exception_by_case_id(case_id: str) -> dict[str, Any]:
    exceptions, _, _ = load_mock_data()
    for exception in exceptions:
        if exception["case_id"] == case_id:
            return exception
    raise HTTPException(status_code=404, detail="Exception case not found")


def normalize_compliance_hold_status(raw_status: str | None, exception_type: str | None) -> str:
    """Map mock payment statuses into orchestrator compliance semantics.

    The orchestrator treats any compliance_hold_status other than NONE as a live
    compliance signal. The mock generator assigns compliance statuses randomly,
    so the canonical adapter makes the exception scenario authoritative.
    """
    if exception_type != "COMPLIANCE_HOLD":
        return "NONE"

    status = (raw_status or "").upper()
    if status in {"", "CLEARED", "NONE"}:
        return "PENDING_REVIEW"
    return status


def canonicalize_exception(exception: dict[str, Any]) -> dict[str, Any]:
    _, payments, compliance_records = load_mock_data()
    payment = payments.get(exception["payment_id"])
    if payment is None:
        raise HTTPException(status_code=422, detail="Exception references missing payment")

    compliance = compliance_records.get(exception["user_id"], {})
    exception_type = exception.get("exception_type")
    compliance_hold_status = normalize_compliance_hold_status(
        payment.get("compliance_hold_status"),
        exception_type,
    )

    return {
        "schema_version": "mvp-1.0",
        "event_id": exception["case_id"],
        "event_timestamp": None,
        "source_system": "mock-api",
        "payment": {
            "payment_id": payment["payment_id"],
            "client_id": payment.get("client_id") or payment.get("user_id"),
            "client_reference": None,
            "account_id": payment.get("user_id"),
            "payment_rail": payment.get("payment_rail"),
            "payment_type": None,
            "amount": payment["amount"],
            "currency": payment.get("currency", "USD"),
            "submitted_timestamp": payment.get("submitted_timestamp"),
            "current_transaction_status": payment.get("current_transaction_status") or payment.get("status"),
        },
        "beneficiary": {
            "beneficiary_id": payment.get("beneficiary"),
            "name": payment.get("beneficiary_details"),
            "account_number_masked": None,
            "ifsc": None,
            "upi_id": None,
            "country": None,
            "beneficiary_fingerprint": payment.get("beneficiary"),
        },
        "exception": {
            "exception_code": exception_type or exception.get("exception_code"),
            "exception_type_hint": exception_type,
            "description": exception.get("description"),
            "severity": exception.get("severity"),
        },
        "status_evidence": {
            "funds_movement_status": "UNKNOWN",
            "ledger_debit_status": "UNKNOWN",
            "network_finality": "UNKNOWN",
        },
        "beneficiary_validation": {
            "validation_status": "INVALID" if exception_type == "INVALID_BENEFICIARY" else None,
            "failed_fields": ["beneficiary"] if exception_type == "INVALID_BENEFICIARY" else [],
            "suggested_correction": None,
            "validation_confidence": 0.85 if exception_type == "INVALID_BENEFICIARY" else None,
        },
        "duplicate_evidence": {
            "duplicate_candidates": [
                {
                    "payment_id": payment["payment_id"],
                    "match_reason": "mock duplicate exception scenario",
                }
            ]
            if exception_type == "DUPLICATE_PAYMENT"
            else [],
            "payment_fingerprint": f"{payment.get('user_id')}:{payment.get('beneficiary')}:{payment.get('amount')}:{payment.get('currency')}",
        },
        "compliance": {
            "compliance_hold_status": compliance_hold_status,
            "screening_result": "HIT" if compliance.get("sanctions_flag") else "UNKNOWN",
            "screening_reference": None,
            "risk_flags": [key for key, value in compliance.items() if isinstance(value, bool) and value],
        },
        "network": {
            "network_acknowledgements": [{"ack": ack} for ack in payment.get("network_acknowledgements", [])],
            "rail_health_status": "DEGRADED" if exception_type == "NETWORK_FAILURE" else "UNKNOWN",
            "rail_incident_id": None,
        },
        "history": {
            "prior_retry_events": [{"event": event} for event in payment.get("prior_retry_events", [])],
            "client_contact_history": [{"event": event} for event in payment.get("client_contact_history", [])],
        },
        "policy": {
            "automation_mode": "RECOMMENDATION_ONLY",
            "manual_review_threshold": 0.75,
            "safe_retry_threshold": 0.97,
            "duplicate_cancel_threshold": 0.95,
            "beneficiary_repair_threshold": 0.98,
        },
    }
