from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
MOCK_SERVER = ROOT / "mock_server"
sys.path.insert(0, str(MOCK_SERVER))

from canonical_adapter import canonicalize_exception, load_mock_data  # noqa: E402
from payment_exception_mvp.orchestrator import orchestrate  # noqa: E402
from payment_exception_mvp.schemas import CanonicalPaymentException  # noqa: E402


EXPECTED_AGENT_BY_EXCEPTION_TYPE = {
    "COMPLIANCE_HOLD": "ComplianceAgent",
    "DUPLICATE_PAYMENT": "DuplicatePaymentAgent",
    "INVALID_BENEFICIARY": "BeneficiaryAgent",
    "NETWORK_FAILURE": "NetworkAgent",
    "INSUFFICIENT_FUNDS": "ManualReviewFallback",
}


def test_mock_api_canonical_payloads_validate_and_route_to_expected_agents():
    exceptions, _, _ = load_mock_data()
    assert exceptions, "run mock_server/generate_data.py before adapter validation"

    seen_exception_types = set()
    mismatches = []

    for exception in exceptions:
        seen_exception_types.add(exception["exception_type"])
        canonical = canonicalize_exception(exception)
        CanonicalPaymentException.model_validate(canonical)

        response = orchestrate(canonical)
        expected_agent = EXPECTED_AGENT_BY_EXCEPTION_TYPE[exception["exception_type"]]
        if response["selected_agent"] != expected_agent:
            mismatches.append(
                {
                    "case_id": exception["case_id"],
                    "exception_type": exception["exception_type"],
                    "expected_agent": expected_agent,
                    "actual_agent": response["selected_agent"],
                }
            )

    assert seen_exception_types == set(EXPECTED_AGENT_BY_EXCEPTION_TYPE)
    assert not mismatches
