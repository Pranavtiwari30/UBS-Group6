from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from payment_exception_mvp.llm_config import LLMConfig
from payment_exception_mvp.llm_tools import LLMToolbox, tool_schemas
from payment_exception_mvp.schemas import AgentOutput, CanonicalPaymentException


class LLMReviewError(RuntimeError):
    """Raised when the LLM stage cannot produce a usable decision."""


@dataclass
class LLMReview:
    decision: AgentOutput
    selected_agent: str
    classification: str
    tool_calls: list[str] = field(default_factory=list)
    rerouted_to: list[str] = field(default_factory=list)
    iterations: int = 0


SYSTEM_PROMPT = """You are the final decision authority for a payment exception resolution \
orchestrator at a bank. A deterministic rule engine has already classified the exception, run a \
specialist subagent, and applied conservative safety fallbacks. Your job is to independently \
analyse the case using your read-only tools and then submit the final decision.

Operating rules:
- This system is recommendation-only. It never moves money, retries, cancels, repairs, releases \
holds, or contacts clients. You only recommend.
- Use the read-only tools to inspect the actual evidence before deciding. Do not assume facts \
that are not in the tool results.
- You MAY disagree with the rule-based routing. If the evidence points to a different exception \
type, call invoke_subagent to get that specialist's analysis, then decide.
- You may confirm the deterministic decision, make it MORE conservative, raise the risk level, \
add reason codes, or force MANUAL_REVIEW.
- HARD LIMITS you cannot escape (the orchestrator re-applies them after you): you cannot enable \
automation, you cannot release or downgrade a compliance hold/escalation, and any compliance \
signal forces ESCALATE_COMPLIANCE. When in doubt, choose the more conservative action.
- Call submit_decision exactly once when your analysis is complete."""


def _build_user_message(
    event: CanonicalPaymentException,
    classification: str,
    selected_agent: str,
    deterministic: AgentOutput,
) -> str:
    payload = {
        "rule_based_classification": classification,
        "rule_based_selected_agent": selected_agent,
        "deterministic_decision": {
            "action": deterministic.action,
            "confidence": deterministic.confidence,
            "risk_level": deterministic.risk_level,
            "reason_codes": deterministic.reason_codes,
            "fallbacks_triggered": deterministic.fallbacks_triggered,
            "explanation": deterministic.explanation,
        },
        "exception_code": event.exception.exception_code,
    }
    return (
        "Review this payment exception and submit the final decision.\n\n"
        + json.dumps(payload, indent=2, default=str)
        + "\n\nInspect the evidence with your tools, optionally re-route, then call submit_decision."
    )


def _assistant_message_to_dict(message: Any) -> dict[str, Any]:
    tool_calls = []
    for tc in message.tool_calls or []:
        tool_calls.append(
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
        )
    out: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if tool_calls:
        out["tool_calls"] = tool_calls
    return out


def _decision_from_submit(args: dict[str, Any], fallback_agent: str) -> tuple[AgentOutput, str, str]:
    selected_agent = str(args.get("selected_agent") or fallback_agent)
    classification = str(args.get("classification") or "")
    decision = AgentOutput(
        agent_name=selected_agent,
        classification=classification,
        action=str(args["action"]),
        automation_allowed=False,
        confidence=float(args["confidence"]),
        risk_level=args["risk_level"],
        reason_codes=[str(c) for c in args.get("reason_codes", [])],
        evidence=[str(e) for e in args.get("evidence", [])],
        fallbacks_triggered=["llm_final_decision"],
        explanation=str(args.get("explanation", "")),
        next_steps=[str(s) for s in args.get("next_steps", [])],
    )
    return decision, selected_agent, classification


def review_decision(
    *,
    config: LLMConfig,
    event: CanonicalPaymentException,
    classification: str,
    selected_agent: str,
    deterministic: AgentOutput,
    subagent_runner: Callable[[str], dict[str, Any]],
) -> LLMReview:
    """Run the OpenAI tool-calling loop and return the model's final decision.

    Raises LLMReviewError on any failure so the caller can keep the deterministic decision.
    """
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - exercised only without the SDK
        raise LLMReviewError(f"openai SDK unavailable: {exc}") from exc

    client = OpenAI(api_key=config.api_key, base_url=config.base_url)
    toolbox = LLMToolbox(event, subagent_runner)
    tools = tool_schemas()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_message(event, classification, selected_agent, deterministic)},
    ]
    tool_call_log: list[str] = []

    request_kwargs: dict[str, Any] = {"model": config.model, "tools": tools, "tool_choice": "auto"}
    if config.temperature is not None:
        request_kwargs["temperature"] = config.temperature

    for iteration in range(1, config.max_tool_iterations + 1):
        try:
            response = client.chat.completions.create(messages=messages, **request_kwargs)
        except Exception as exc:  # network, auth, rate limit, bad model id, etc.
            raise LLMReviewError(f"openai request failed: {exc}") from exc

        message = response.choices[0].message
        if not message.tool_calls:
            messages.append(_assistant_message_to_dict(message))
            messages.append(
                {"role": "user", "content": "Call submit_decision now with your final decision."}
            )
            continue

        messages.append(_assistant_message_to_dict(message))

        for tc in message.tool_calls:
            name = tc.function.name
            tool_call_log.append(name)
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError as exc:
                raise LLMReviewError(f"malformed tool arguments for {name}: {exc}") from exc

            if name == "submit_decision":
                try:
                    decision, agent, klass = _decision_from_submit(args, selected_agent)
                except Exception as exc:
                    raise LLMReviewError(f"invalid submit_decision payload: {exc}") from exc
                return LLMReview(
                    decision=decision,
                    selected_agent=agent,
                    classification=klass or classification,
                    tool_calls=tool_call_log,
                    rerouted_to=list(toolbox.invoked_agents),
                    iterations=iteration,
                )

            result = toolbox.dispatch(name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                }
            )

    raise LLMReviewError(f"no decision after {config.max_tool_iterations} tool iterations")
