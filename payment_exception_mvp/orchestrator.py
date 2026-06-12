from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from payment_exception_mvp import agent_adapters
from payment_exception_mvp.agent_adapters import AgentInvocationError
from payment_exception_mvp.checkpoints import CheckpointRecorder
from payment_exception_mvp.classifiers import ClassificationResult, classify_exception
from payment_exception_mvp.llm_config import LLMConfig
from payment_exception_mvp.llm_reviewer import LLMReview, LLMReviewError, review_decision
from payment_exception_mvp.safety import apply_safety_fallbacks, manual_review_output
from payment_exception_mvp.schemas import (
    AgentOutput,
    CanonicalPaymentException,
    FinalDecision,
    FinalResponse,
    validate_agent_output,
)
from payment_exception_mvp.slicers import build_agent_input


def orchestrate(payload: dict[str, Any], llm_config: LLMConfig | None = None) -> dict[str, Any]:
    config = llm_config or LLMConfig.from_env()
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

    selected_agent = classification.selected_agent
    classification_label = classification.classification

    if selected_agent == "ManualReviewFallback":
        agent_output = manual_review_output(
            agent_name="ManualReviewFallback",
            classification=classification_label,
            reason_code="UNSUPPORTED_EXCEPTION_TYPE",
            explanation="The exception did not match any supported MVP routing rule.",
            fallback="unsupported_exception_type",
            evidence=[f"exception.exception_code={event.exception.exception_code}"],
        )
    else:
        agent_output = _run_subagent(
            event, selected_agent, classification_label, trace_id, case_id, checkpoints, config, record=True
        )

    deterministic_output = apply_safety_fallbacks(event, agent_output)
    checkpoints.add("safety_fallbacks_evaluated")

    final_output = deterministic_output
    final_agent = selected_agent
    final_classification = classification_label

    if config.enabled:
        review = _run_llm_review(
            config, event, classification_label, selected_agent, deterministic_output, trace_id, case_id, checkpoints
        )
        if review is not None:
            # Re-apply the deterministic safety floor ON TOP of the LLM decision so the model
            # can tighten or re-route but never loosen compliance/automation limits.
            final_output = apply_safety_fallbacks(event, review.decision)
            final_agent = review.selected_agent
            final_classification = review.classification or classification_label
            checkpoints.add("safety_floor_reapplied")

    return _final_response(event, trace_id, case_id, final_classification, final_agent, final_output, checkpoints)


def _run_subagent(
    event: CanonicalPaymentException,
    agent_name: str,
    classification_label: str,
    trace_id: str,
    case_id: str,
    checkpoints: CheckpointRecorder,
    config: LLMConfig,
    record: bool,
) -> AgentOutput:
    """Slice, invoke, and validate one subagent. Failures become a manual-review AgentOutput."""
    try:
        agent_input = build_agent_input(event, agent_name, trace_id, case_id)
        agent_input_dict = agent_input.model_dump()
        if record:
            checkpoints.add("agent_input_sliced")
            checkpoints.add(
                "agent_input_schema_validated",
                details=f"{agent_name} input uses scoped context keys: {sorted(agent_input.context.keys())}",
            )
    except Exception as exc:
        if record:
            checkpoints.add("agent_input_schema_validated", "failed", str(exc))
        return manual_review_output(
            agent_name=agent_name,
            classification=classification_label,
            reason_code="AGENT_INPUT_INVALID",
            explanation="The orchestrator could not build a valid scoped subagent input.",
            fallback="agent_input_invalid",
        )

    try:
        if record:
            checkpoints.add("agent_invocation_started")
        raw_output = agent_adapters.invoke(agent_name, agent_input_dict, config)
        if record:
            checkpoints.add("agent_completed")
    except AgentInvocationError as exc:
        if record:
            checkpoints.add("agent_failed", "failed", str(exc))
        return manual_review_output(
            agent_name=agent_name,
            classification=classification_label,
            reason_code="AGENT_FAILED",
            explanation="The selected subagent was unavailable or failed, so the orchestrator returned manual review.",
            fallback="agent_not_available",
        )

    try:
        validated_output = validate_agent_output(raw_output, agent_name)
        if record:
            checkpoints.add("agent_output_validated")
    except ValidationError as exc:
        if record:
            checkpoints.add("agent_output_validated", "failed", str(exc.errors()[:3]))
        return manual_review_output(
            agent_name=agent_name,
            classification=classification_label,
            reason_code="AGENT_OUTPUT_INVALID",
            explanation="The selected subagent returned an invalid output schema.",
            fallback="agent_output_invalid",
        )

    return validated_output


def _run_llm_review(
    config: LLMConfig,
    event: CanonicalPaymentException,
    classification_label: str,
    selected_agent: str,
    deterministic_output: AgentOutput,
    trace_id: str,
    case_id: str,
    checkpoints: CheckpointRecorder,
) -> LLMReview | None:
    """Run the OpenAI final-decision stage. Returns None and records a checkpoint on any failure."""

    def subagent_runner(agent_name: str) -> dict[str, Any]:
        output = _run_subagent(
            event, agent_name, classification_label, trace_id, case_id, checkpoints, config, record=False
        )
        return output.model_dump()

    checkpoints.add("llm_review_started", details=f"model={config.model}")
    try:
        review = review_decision(
            config=config,
            event=event,
            classification=classification_label,
            selected_agent=selected_agent,
            deterministic=deterministic_output,
            subagent_runner=subagent_runner,
        )
    except LLMReviewError as exc:
        checkpoints.add(
            "llm_review_completed",
            "failed",
            f"LLM stage failed, keeping deterministic decision: {exc}",
        )
        return None

    details = f"tools={review.tool_calls}; iterations={review.iterations}"
    if review.rerouted_to:
        checkpoints.add("llm_rerouted", details=f"{selected_agent} -> {review.selected_agent} via {review.rerouted_to}")
    checkpoints.add("llm_review_completed", details=details)
    return review


def _final_response(
    event: CanonicalPaymentException,
    trace_id: str,
    case_id: str,
    classification: str,
    selected_agent: str,
    agent_output: AgentOutput,
    checkpoints: CheckpointRecorder,
) -> dict[str, Any]:
    checkpoints.add("final_decision_created")
    response = FinalResponse(
        trace_id=trace_id,
        case_id=case_id,
        event_id=event.event_id,
        payment_id=event.payment.payment_id,
        classification=classification,
        selected_agent=selected_agent,
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
