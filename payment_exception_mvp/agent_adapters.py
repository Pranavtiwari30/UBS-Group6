from __future__ import annotations

from importlib import import_module
from typing import Any


AGENT_MODULES = {
    "BeneficiaryAgent": "payment_exception_mvp.agents.beneficiary_agent",
    "DuplicatePaymentAgent": "payment_exception_mvp.agents.duplicate_payment_agent",
    "ComplianceAgent": "payment_exception_mvp.agents.compliance_agent",
    "NetworkAgent": "payment_exception_mvp.agents.network_agent",
}


class AgentInvocationError(RuntimeError):
    pass


def invoke(agent_name: str, agent_input: dict[str, Any], config: Any = None) -> dict[str, Any]:
    module_path = AGENT_MODULES.get(agent_name)
    if not module_path:
        raise AgentInvocationError(f"no module configured for {agent_name}")
    try:
        module = import_module(module_path)
        analyze = getattr(module, "analyze")
        output = analyze(agent_input, config)
    except Exception as exc:
        raise AgentInvocationError(f"{agent_name} failed: {exc}") from exc
    if not isinstance(output, dict):
        raise AgentInvocationError(f"{agent_name} returned {type(output).__name__}, expected dict")
    return output
