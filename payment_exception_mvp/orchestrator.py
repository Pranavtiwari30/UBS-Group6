from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from payment_exception_mvp import agent_adapters
from payment_exception_mvp.agent_adapters import AgentInvocationError
from payment_exception_mvp.checkpoints import CheckpointRecorder
from payment_exception_mvp.classifiers import ClassificationResult, classify_exception
from payment_exception_mvp.safety import apply_safety_fallbacks, manual_review_output
from payment_exception_mvp.schemas import (
    AgentOutput,
    CanonicalPaymentException,
    FinalDecision,
    FinalResponse,
    validate_agent_output,
)
from payment_exception_mvp.slicers import build_agent_input


def orchestrate(payload: dict[str, Any]) -> dict[str, Any]:
    checkpoints = CheckpointRecorder()
    checkpoints.add("request_received")

    try:
        event = CanonicalPaymentException.model_validate(payload)
        checkpoints.add("canonical_schema_validated")
    except ValidationError as exc:
        checkpoints.add("canonical_schema_validated", "failed", str(exc.errors()[:3]))
        response = _validation_failure_response(payload, checkpoints)
        response["checkpoints"].append({"name": "response_emitted", "status": "passed"})
        return response

    checkpoints.add("payload_normalized")
    trace_id = f"trace-{event.event_id}"
    case_id = f"case-{event.payment.payment_id}"
    checkpoints.add("idempotency_key_created", details=f"{event.event_id}:{event.payment.payment_id}")

    checkpoints.add("classification_started")
    classification = classify_exception(event)
    checkpoints.add("classification_completed", details=classification.reason)
    checkpoints.add("agent_selected", details=classification.selected_agent)

    if classification.selected_agent == "ManualReviewFallback":
        agent_output = manual_review_output(
            agent_name="ManualReviewFallback",
            classification=classification.classification,
            reason_code="UNSUPPORTED_EXCEPTION_TYPE",
            explanation="The exception did not match any supported MVP routing rule.",
            fallback="unsupported_exception_type",
            evidence=[f"exception.exception_code={event.exception.exception_code}"],
        )
        checkpoints.add("safety_fallbacks_evaluated")
        return _final_response(event, trace_id, case_id, classification, agent_output, checkpoints)

    try:
        agent_input = build_agent_input(event, classification.selected_agent, trace_id, case_id)
        checkpoints.add("agent_input_sliced")
        agent_input_dict = agent_input.model_dump()
        checkpoints.add(
            "agent_input_schema_validated",
            details=f"{classification.selected_agent} input uses scoped context keys: {sorted(agent_input.context.keys())}",
        )
    except Exception as exc:
        checkpoints.add("agent_input_schema_validated", "failed", str(exc))
        agent_output = manual_review_output(
            agent_name=classification.selected_agent,
            classification=classification.classification,
            reason_code="AGENT_INPUT_INVALID",
            explanation="The orchestrator could not build a valid scoped subagent input.",
            fallback="agent_input_invalid",
        )
        return _final_response(event, trace_id, case_id, classification, agent_output, checkpoints)

    try:
        checkpoints.add("agent_invocation_started")
        raw_output = agent_adapters.invoke(classification.selected_agent, agent_input_dict)
        checkpoints.add("agent_completed")
    except AgentInvocationError as exc:
        checkpoints.add("agent_failed", "failed", str(exc))
        agent_output = manual_review_output(
            agent_name=classification.selected_agent,
            classification=classification.classification,
            reason_code="AGENT_FAILED",
            explanation="The selected subagent was unavailable or failed, so the orchestrator returned manual review.",
            fallback="agent_not_available",
        )
        return _final_response(event, trace_id, case_id, classification, agent_output, checkpoints)

    try:
        validated_output = validate_agent_output(raw_output, classification.selected_agent)
        checkpoints.add("agent_output_validated")
    except ValidationError as exc:
        checkpoints.add("agent_output_validated", "failed", str(exc.errors()[:3]))
        validated_output = manual_review_output(
            agent_name=classification.selected_agent,
            classification=classification.classification,
            reason_code="AGENT_OUTPUT_INVALID",
            explanation="The selected subagent returned an invalid output schema.",
            fallback="agent_output_invalid",
        )

    safe_output = apply_safety_fallbacks(event, validated_output)
    checkpoints.add("safety_fallbacks_evaluated")
    return _final_response(event, trace_id, case_id, classification, safe_output, checkpoints)


def _final_response(
    event: CanonicalPaymentException,
    trace_id: str,
    case_id: str,
    classification: ClassificationResult,
    agent_output: AgentOutput,
    checkpoints: CheckpointRecorder,
) -> dict[str, Any]:
    checkpoints.add("final_decision_created")
    response = FinalResponse(
        trace_id=trace_id,
        case_id=case_id,
        event_id=event.event_id,
        payment_id=event.payment.payment_id,
        classification=classification.classification,
        selected_agent=classification.selected_agent,
        decision=FinalDecision(
            action=agent_output.action,
            automation_allowed=False,
            confidence=agent_output.confidence,
            risk_level=agent_output.risk_level,
            reason_codes=agent_output.reason_codes,
        ),
        evidence=agent_output.evidence,
        checkpoints=checkpoints.as_list(),
        fallbacks_triggered=agent_output.fallbacks_triggered,
        explanation=agent_output.explanation,
        next_steps=agent_output.next_steps,
    )
    response_dict = response.model_dump()
    response_dict["checkpoints"].append({"name": "response_emitted", "status": "passed"})
    return response_dict


def _validation_failure_response(payload: dict[str, Any], checkpoints: CheckpointRecorder) -> dict[str, Any]:
    event_id = str(payload.get("event_id", "unknown-event")) if isinstance(payload, dict) else "unknown-event"
    payment = payload.get("payment", {}) if isinstance(payload, dict) else {}
    payment_id = str(payment.get("payment_id", "unknown-payment")) if isinstance(payment, dict) else "unknown-payment"
    trace_id = f"trace-{event_id}"
    case_id = f"case-{payment_id}"
    checkpoints.add("final_decision_created")
    return {
        "trace_id": trace_id,
        "case_id": case_id,
        "event_id": event_id,
        "payment_id": payment_id,
        "classification": "manual_review",
        "selected_agent": "ManualReviewFallback",
        "decision": {
            "action": "MANUAL_REVIEW",
            "automation_allowed": False,
            "confidence": 0.0,
            "risk_level": "HIGH",
            "reason_codes": ["CANONICAL_SCHEMA_INVALID"],
        },
        "evidence": ["canonical payload failed validation"],
        "checkpoints": checkpoints.as_list(),
        "fallbacks_triggered": ["canonical_schema_invalid"],
        "explanation": "The canonical payment exception payload is invalid, so the case requires manual review.",
        "next_steps": ["Fix the mock API payload", "Route to manual review until valid data is available"],
    }
