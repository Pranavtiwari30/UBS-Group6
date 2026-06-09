# app/agents/__init__.py
# Expose all agent analyze() functions for convenient import by the orchestrator.

from app.agents.beneficiary_agent import analyze as analyze_beneficiary
from app.agents.duplicate_payment_agent import analyze as analyze_duplicate
from app.agents.compliance_agent import analyze as analyze_compliance
from app.agents.network_failure_agent import analyze as analyze_network

__all__ = [
    "analyze_beneficiary",
    "analyze_duplicate",
    "analyze_compliance",
    "analyze_network",
]
