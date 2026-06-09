import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from payment_exception_mvp.llm_config import LLMConfig
from payment_exception_mvp.orchestrator import orchestrate

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "payment_exception_mvp" / "fixtures"


def load_fixture(name: str) -> dict:
    with (FIXTURE_DIR / name).open() as handle:
        return json.load(handle)


def llm_config() -> LLMConfig:
    return LLMConfig(
        enabled=True,
        api_key="test-key",
        model="gpt-5.4",
        base_url=None,
        max_tool_iterations=8,
        temperature=None,
    )


# --- scripted fake OpenAI client -----------------------------------------------


def _tool_call(call_id: str, name: str, arguments: dict):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def _completion(tool_calls=None, content=""):
    message = SimpleNamespace(content=content, tool_calls=tool_calls or None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def install_fake_openai(monkeypatch, script):
    """script is a list where each item is a FakeCompletion or an Exception to raise."""

    class _Completions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            # Subagent (mini) calls are not part of the reviewer script; let them fall
            # back to the deterministic baseline by returning no tool_calls.
            if "mini" in str(kwargs.get("model", "")):
                return _completion()
            step = script[self.calls]
            self.calls += 1
            if isinstance(step, Exception):
                raise step
            return step

    class _Client:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=_Completions())

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake_module)


def submit(**kwargs):
    payload = {
        "action": "REQUEST_CLIENT_CORRECTION",
        "classification": "incorrect_beneficiary",
        "selected_agent": "BeneficiaryAgent",
        "confidence": 0.9,
        "risk_level": "MEDIUM",
        "reason_codes": ["LLM_REVIEWED"],
        "evidence": ["llm inspected beneficiary_validation"],
        "explanation": "LLM confirmed client correction.",
        "next_steps": ["Contact client"],
    }
    payload.update(kwargs)
    return _tool_call("call-submit", "submit_decision", payload)


# --- tests ---------------------------------------------------------------------


def test_llm_decision_replaces_deterministic(monkeypatch):
    script = [
        _completion([_tool_call("c1", "get_beneficiary_validation", {})]),
        _completion([submit(confidence=0.91, risk_level="LOW")]),
    ]
    install_fake_openai(monkeypatch, script)

    response = orchestrate(load_fixture("beneficiary_invalid.json"), llm_config())

    assert response["decision"]["action"] == "REQUEST_CLIENT_CORRECTION"
    assert "LLM_REVIEWED" in response["decision"]["reason_codes"]
    assert "llm_final_decision" in response["fallbacks_triggered"]
    names = [c["name"] for c in response["checkpoints"]]
    assert "llm_review_started" in names
    assert "llm_review_completed" in names
    assert "safety_floor_reapplied" in names


def test_hard_floor_overrides_llm_on_compliance(monkeypatch):
    # LLM tries to be lenient on a sanctions case; the floor must force ESCALATE_COMPLIANCE.
    script = [
        _completion([submit(action="NO_ACTION_MONITOR", classification="compliance_hold",
                            selected_agent="ComplianceAgent", risk_level="LOW")]),
    ]
    install_fake_openai(monkeypatch, script)

    response = orchestrate(load_fixture("compliance_hold.json"), llm_config())

    assert response["decision"]["action"] == "ESCALATE_COMPLIANCE"
    assert response["decision"]["automation_allowed"] is False
    assert "compliance_signal_detected" in response["fallbacks_triggered"]


def test_llm_reroute_changes_selected_agent(monkeypatch):
    # Rules pick BeneficiaryAgent; the LLM re-routes to DuplicatePaymentAgent.
    script = [
        _completion([_tool_call("c1", "invoke_subagent", {"agent_name": "DuplicatePaymentAgent"})]),
        _completion([submit(action="HOLD_AND_RECONCILE", classification="duplicate_payment",
                            selected_agent="DuplicatePaymentAgent", risk_level="HIGH")]),
    ]
    install_fake_openai(monkeypatch, script)

    response = orchestrate(load_fixture("beneficiary_invalid.json"), llm_config())

    assert response["selected_agent"] == "DuplicatePaymentAgent"
    assert response["classification"] == "duplicate_payment"
    names = [c["name"] for c in response["checkpoints"]]
    assert "llm_rerouted" in names


def test_llm_failure_keeps_deterministic_decision(monkeypatch):
    script = [RuntimeError("simulated openai outage")]
    install_fake_openai(monkeypatch, script)

    response = orchestrate(load_fixture("beneficiary_invalid.json"), llm_config())

    # Deterministic stub decision survives; no LLM markers.
    assert response["selected_agent"] == "BeneficiaryAgent"
    assert "llm_final_decision" not in response["fallbacks_triggered"]
    completed = [c for c in response["checkpoints"] if c["name"] == "llm_review_completed"]
    assert completed and completed[0]["status"] == "failed"


def test_llm_disabled_when_no_key():
    config = LLMConfig(enabled=False, api_key=None, model="gpt-5.4", base_url=None,
                       max_tool_iterations=8, temperature=None)
    response = orchestrate(load_fixture("beneficiary_invalid.json"), config)
    names = [c["name"] for c in response["checkpoints"]]
    assert "llm_review_started" not in names
