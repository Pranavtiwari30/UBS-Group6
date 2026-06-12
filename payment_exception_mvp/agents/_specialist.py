from __future__ import annotations

import json
from typing import Any

from payment_exception_mvp.schemas import ACCEPTED_ACTIONS

# Risk levels the subagent model is allowed to choose from.
_RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

# Fields the subagent model may adjust. agent_name/automation_allowed are never
# model-controlled: the agent identity stays fixed and automation stays disabled.
_REFINABLE_KEYS = (
    "classification",
    "action",
    "confidence",
    "risk_level",
    "reason_codes",
    "evidence",
    "explanation",
    "next_steps",
)


def _analysis_tool_schema() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "submit_analysis",
                "description": (
                    "Submit your specialist analysis for this payment exception. "
                    "Recommendation-only: never enable automation. Call exactly once."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "classification": {"type": "string"},
                        "action": {"type": "string", "enum": sorted(ACCEPTED_ACTIONS)},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "risk_level": {"type": "string", "enum": list(_RISK_LEVELS)},
                        "reason_codes": {"type": "array", "items": {"type": "string"}},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                        "explanation": {"type": "string"},
                        "next_steps": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["action", "confidence", "risk_level", "explanation"],
                    "additionalProperties": False,
                },
            },
        }
    ]


def _merge(baseline: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    refined = dict(baseline)
    for key in _REFINABLE_KEYS:
        if key in args and args[key] not in (None, ""):
            refined[key] = args[key]
    # Hard invariants the model can never override.
    refined["agent_name"] = baseline["agent_name"]
    refined["automation_allowed"] = False
    if refined.get("action") not in ACCEPTED_ACTIONS:
        refined["action"] = baseline["action"]
    if refined.get("risk_level") not in _RISK_LEVELS:
        refined["risk_level"] = baseline["risk_level"]
    fallbacks = list(baseline.get("fallbacks_triggered", []))
    fallbacks = [f for f in fallbacks if f != "temporary_subagent_stub"]
    fallbacks.append("llm_subagent")
    refined["fallbacks_triggered"] = fallbacks
    return refined


def refine(
    config: Any,
    *,
    agent_name: str,
    role: str,
    context: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """Refine a subagent's deterministic baseline with the configured subagent model.

    Uses ``config.subagent_model`` (gpt-5.4-mini by default). Returns the baseline
    unchanged whenever the LLM is disabled or anything goes wrong, so the subagent
    is always runnable without network access.
    """
    if config is None or not getattr(config, "enabled", False):
        return baseline
    model = getattr(config, "subagent_model", None)
    if not model:
        return baseline

    try:
        from openai import OpenAI
    except ImportError:
        return baseline

    try:
        client = OpenAI(api_key=getattr(config, "api_key", None), base_url=getattr(config, "base_url", None))
        system = (
            f"You are the {agent_name}, a specialist in a bank's payment exception "
            f"resolution orchestrator. {role} This system is recommendation-only: you never "
            "move money, retry, cancel, repair, release holds, or contact clients — you only "
            "recommend. A deterministic baseline analysis is provided; confirm it or make it "
            "more precise based strictly on the evidence. When uncertain, be conservative. "
            "Call submit_analysis exactly once."
        )
        user = (
            "Scoped evidence for this case:\n"
            + json.dumps(context, indent=2, default=str)
            + "\n\nDeterministic baseline:\n"
            + json.dumps({k: baseline.get(k) for k in _REFINABLE_KEYS}, indent=2, default=str)
            + "\n\nSubmit your analysis."
        )
        request_kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": _analysis_tool_schema(),
            "tool_choice": {"type": "function", "function": {"name": "submit_analysis"}},
        }
        temperature = getattr(config, "temperature", None)
        if temperature is not None:
            request_kwargs["temperature"] = temperature

        response = client.chat.completions.create(**request_kwargs)
        message = response.choices[0].message
        if not message.tool_calls:
            return baseline
        args = json.loads(message.tool_calls[0].function.arguments or "{}")
    except Exception:
        return baseline

    if not isinstance(args, dict):
        return baseline
    return _merge(baseline, args)
