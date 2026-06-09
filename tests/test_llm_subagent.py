import json
import sys
import types
from types import SimpleNamespace

from payment_exception_mvp.agents import beneficiary_agent
from payment_exception_mvp.llm_config import LLMConfig


def _config(enabled=True, subagent_model="gpt-5.4-mini"):
    return LLMConfig(
        enabled=enabled,
        api_key="test-key" if enabled else None,
        model="gpt-5.4",
        base_url=None,
        max_tool_iterations=8,
        temperature=None,
        subagent_model=subagent_model,
    )


def _agent_input():
    return {
        "context": {
            "beneficiary_validation": {
                "validation_status": "FAILED",
                "failed_fields": ["account_number"],
                "validation_confidence": 0.6,
            },
            "payment_summary": {"funds_movement_status": "NOT_STARTED"},
        }
    }


def install_submit_analysis(monkeypatch, args, *, expect_model="gpt-5.4-mini"):
    captured = {}

    class _Completions:
        def create(self, **kwargs):
            captured["model"] = kwargs.get("model")
            tc = SimpleNamespace(
                id="c1",
                type="function",
                function=SimpleNamespace(name="submit_analysis", arguments=json.dumps(args)),
            )
            message = SimpleNamespace(content="", tool_calls=[tc])
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class _Client:
        def __init__(self, *a, **k):
            self.chat = SimpleNamespace(completions=_Completions())

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    return captured


def test_subagent_uses_mini_model_and_refines(monkeypatch):
    captured = install_submit_analysis(
        monkeypatch,
        {
            "classification": "incorrect_beneficiary",
            "action": "REQUEST_CLIENT_CORRECTION",
            "confidence": 0.7,
            "risk_level": "HIGH",
            "reason_codes": ["MINI_REVIEWED"],
            "explanation": "mini specialist confirmed invalid beneficiary",
            "next_steps": ["Contact client"],
        },
    )

    out = beneficiary_agent.analyze(_agent_input(), _config())

    assert captured["model"] == "gpt-5.4-mini"
    assert out["agent_name"] == "BeneficiaryAgent"  # identity is never model-controlled
    assert out["automation_allowed"] is False
    assert out["risk_level"] == "HIGH"
    assert "MINI_REVIEWED" in out["reason_codes"]
    assert "llm_subagent" in out["fallbacks_triggered"]
    assert "temporary_subagent_stub" not in out["fallbacks_triggered"]


def test_subagent_invalid_action_falls_back_to_baseline(monkeypatch):
    install_submit_analysis(
        monkeypatch,
        {
            "action": "WIRE_THE_MONEY",  # not in ACCEPTED_ACTIONS
            "confidence": 0.9,
            "risk_level": "LOW",
            "explanation": "bogus",
        },
    )

    out = beneficiary_agent.analyze(_agent_input(), _config())

    assert out["action"] == "REQUEST_CLIENT_CORRECTION"  # baseline action survives


def test_subagent_deterministic_when_disabled():
    out = beneficiary_agent.analyze(_agent_input(), _config(enabled=False))

    assert out["fallbacks_triggered"] == ["temporary_subagent_stub"]


def test_subagent_deterministic_when_no_config():
    out = beneficiary_agent.analyze(_agent_input())

    assert out["fallbacks_triggered"] == ["temporary_subagent_stub"]
