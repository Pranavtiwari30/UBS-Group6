import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "payment_exception_mvp" / "fixtures"

EXPECTED_FIXTURES = {
    "beneficiary_invalid.json": {
        "code_contains": "BENEFICIARY",
        "selected_agent": "BeneficiaryAgent",
        "allowed_actions": {"REQUEST_CLIENT_CORRECTION", "MANUAL_REVIEW"},
    },
    "duplicate_submission.json": {
        "code_contains": "DUPLICATE",
        "selected_agent": "DuplicatePaymentAgent",
        "allowed_actions": {"CANCEL_DUPLICATE", "HOLD_AND_RECONCILE", "MANUAL_REVIEW"},
    },
    "compliance_hold.json": {
        "code_contains": "SANCTIONS",
        "selected_agent": "ComplianceAgent",
        "allowed_actions": {"ESCALATE_COMPLIANCE"},
    },
    "network_failure.json": {
        "code_contains": "NETWORK",
        "selected_agent": "NetworkAgent",
        "allowed_actions": {"HOLD_AND_RECONCILE", "WAIT_FOR_NETWORK_RECOVERY", "MANUAL_REVIEW"},
    },
    "unknown_exception.json": {
        "code_contains": "UNMAPPED",
        "selected_agent": "ManualReviewFallback",
        "allowed_actions": {"MANUAL_REVIEW"},
    },
}

REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "event_id",
    "event_timestamp",
    "source_system",
    "payment",
    "beneficiary",
    "exception",
    "status_evidence",
    "beneficiary_validation",
    "duplicate_evidence",
    "compliance",
    "network",
    "history",
    "policy",
}

REQUIRED_RESPONSE_KEYS = {
    "trace_id",
    "case_id",
    "event_id",
    "payment_id",
    "classification",
    "selected_agent",
    "decision",
    "evidence",
    "checkpoints",
    "fallbacks_triggered",
    "explanation",
    "next_steps",
}

REQUIRED_CHECKPOINTS = {
    "request_received",
    "canonical_schema_validated",
    "classification_completed",
    "final_decision_created",
    "response_emitted",
}


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


@pytest.mark.parametrize("fixture_name,expectation", EXPECTED_FIXTURES.items())
def test_fixture_is_canonical_and_targets_expected_route(fixture_name, expectation):
    payload = load_fixture(fixture_name)

    assert REQUIRED_TOP_LEVEL_KEYS <= payload.keys()
    assert payload["schema_version"] == "mvp-1.0"
    assert payload["policy"]["automation_mode"] == "RECOMMENDATION_ONLY"
    assert expectation["code_contains"] in payload["exception"]["exception_code"]

    if expectation["selected_agent"] == "DuplicatePaymentAgent":
        assert payload["duplicate_evidence"]["duplicate_candidates"]
    if expectation["selected_agent"] == "ComplianceAgent":
        assert payload["compliance"]["compliance_hold_status"] != "NONE"
    if expectation["selected_agent"] == "NetworkAgent":
        assert payload["status_evidence"]["funds_movement_status"] == "UNKNOWN"
    if expectation["selected_agent"] == "ManualReviewFallback":
        assert not payload["duplicate_evidence"]["duplicate_candidates"]
        assert payload["compliance"]["compliance_hold_status"] == "NONE"


@pytest.mark.parametrize("fixture_name,expectation", EXPECTED_FIXTURES.items())
def test_orchestrator_smoke_routes_fixtures_safely(fixture_name, expectation):
    orchestrator = pytest.importorskip("payment_exception_mvp.orchestrator")
    payload = load_fixture(fixture_name)

    response = orchestrator.orchestrate(payload)

    assert REQUIRED_RESPONSE_KEYS <= response.keys()
    assert response["event_id"] == payload["event_id"]
    assert response["payment_id"] == payload["payment"]["payment_id"]
    assert response["selected_agent"] == expectation["selected_agent"]

    decision = response["decision"]
    assert decision["action"] in expectation["allowed_actions"]
    assert decision["automation_allowed"] is False
    assert 0.0 <= decision["confidence"] <= 1.0
    assert decision["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert isinstance(decision["reason_codes"], list)

    checkpoint_names = {checkpoint["name"] for checkpoint in response["checkpoints"]}
    assert REQUIRED_CHECKPOINTS <= checkpoint_names
    assert isinstance(response["evidence"], list)
    assert isinstance(response["fallbacks_triggered"], list)
    assert response["explanation"]
    assert isinstance(response["next_steps"], list)


@pytest.mark.parametrize("fixture_name", EXPECTED_FIXTURES)
def test_orchestrator_never_allows_automation_for_mvp_fixtures(fixture_name):
    orchestrator = pytest.importorskip("payment_exception_mvp.orchestrator")
    response = orchestrator.orchestrate(load_fixture(fixture_name))

    assert response["decision"]["automation_allowed"] is False


def test_missing_subagent_fails_closed_if_adapter_mapping_is_available(monkeypatch):
    orchestrator = pytest.importorskip("payment_exception_mvp.orchestrator")
    adapters = pytest.importorskip("payment_exception_mvp.agent_adapters")

    agent_modules = getattr(adapters, "AGENT_MODULES", None)
    if not isinstance(agent_modules, dict) or "BeneficiaryAgent" not in agent_modules:
        pytest.skip("agent adapter module mapping is not exposed")

    patched_modules = dict(agent_modules)
    patched_modules["BeneficiaryAgent"] = "payment_exception_mvp.agents.not_available_for_smoke_test"
    monkeypatch.setattr(adapters, "AGENT_MODULES", patched_modules)

    response = orchestrator.orchestrate(load_fixture("beneficiary_invalid.json"))

    assert response["selected_agent"] in {"BeneficiaryAgent", "ManualReviewFallback"}
    assert response["decision"]["action"] == "MANUAL_REVIEW"
    assert response["decision"]["automation_allowed"] is False

    checkpoint_names = {checkpoint["name"] for checkpoint in response["checkpoints"]}
    fallback_markers = set(response["fallbacks_triggered"])
    assert "agent_failed" in checkpoint_names or "agent_not_available" in fallback_markers
