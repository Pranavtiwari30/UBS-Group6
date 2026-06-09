from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from payment_exception_mvp.schemas import AgentInputEnvelope, CanonicalPaymentException


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _payment_summary(event: CanonicalPaymentException) -> dict[str, Any]:
    return {
        "client_id": event.payment.client_id,
        "client_reference": event.payment.client_reference,
        "payment_rail": event.payment.payment_rail,
        "amount": event.payment.amount,
        "currency": event.payment.currency,
        "submitted_timestamp": event.payment.submitted_timestamp,
        "current_transaction_status": event.payment.current_transaction_status,
        "funds_movement_status": event.status_evidence.funds_movement_status,
    }


def _policy(event: CanonicalPaymentException, agent_name: str) -> dict[str, Any]:
    policy = {
        "automation_mode": event.policy.automation_mode,
        "manual_review_threshold": event.policy.manual_review_threshold,
    }
    if agent_name == "BeneficiaryAgent":
        policy["beneficiary_repair_threshold"] = event.policy.beneficiary_repair_threshold
    if agent_name == "DuplicatePaymentAgent":
        policy["duplicate_cancel_threshold"] = event.policy.duplicate_cancel_threshold
    if agent_name == "NetworkAgent":
        policy["safe_retry_threshold"] = event.policy.safe_retry_threshold
    return policy


def build_agent_input(event: CanonicalPaymentException, agent_name: str, trace_id: str, case_id: str) -> AgentInputEnvelope:
    context_builders = {
        "BeneficiaryAgent": _beneficiary_context,
        "DuplicatePaymentAgent": _duplicate_context,
        "ComplianceAgent": _compliance_context,
        "NetworkAgent": _network_context,
    }
    if agent_name not in context_builders:
        raise ValueError(f"cannot slice input for {agent_name}")

    envelope = AgentInputEnvelope(
        schema_version="mvp-agent-1.0",
        trace_id=trace_id,
        case_id=case_id,
        event_id=event.event_id,
        payment_id=event.payment.payment_id,
        agent_task_id=f"task-{agent_name.replace('Agent', '').lower()}-{event.payment.payment_id}",
        agent_name=agent_name,
        created_at=_now_iso(),
        policy=_policy(event, agent_name),
        context=context_builders[agent_name](event),
    )
    return envelope


def _beneficiary_context(event: CanonicalPaymentException) -> dict[str, Any]:
    return {
        "payment_summary": _payment_summary(event),
        "exception": event.exception.model_dump(),
        "beneficiary": event.beneficiary.model_dump(),
        "beneficiary_validation": event.beneficiary_validation.model_dump(),
        "client_contact_history": event.history.client_contact_history,
    }


def _duplicate_context(event: CanonicalPaymentException) -> dict[str, Any]:
    return {
        "payment_summary": _payment_summary(event),
        "beneficiary_fingerprint": event.beneficiary.beneficiary_fingerprint,
        "duplicate_evidence": event.duplicate_evidence.model_dump(),
        "prior_retry_events": event.history.prior_retry_events,
    }


def _compliance_context(event: CanonicalPaymentException) -> dict[str, Any]:
    payment = _payment_summary(event)
    return {
        "payment_summary": {
            "client_id": payment["client_id"],
            "amount": payment["amount"],
            "currency": payment["currency"],
            "payment_rail": payment["payment_rail"],
            "current_transaction_status": payment["current_transaction_status"],
        },
        "exception": event.exception.model_dump(),
        "compliance": event.compliance.model_dump(),
    }


def _network_context(event: CanonicalPaymentException) -> dict[str, Any]:
    payment = _payment_summary(event)
    return {
        "payment_summary": {
            "payment_rail": payment["payment_rail"],
            "amount": payment["amount"],
            "currency": payment["currency"],
            "current_transaction_status": payment["current_transaction_status"],
        },
        "status_evidence": event.status_evidence.model_dump(),
        "network": event.network.model_dump(),
        "prior_retry_events": event.history.prior_retry_events,
    }
