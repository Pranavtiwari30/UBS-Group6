"""
Agent response data model — updated to match the MVP orchestrator output schema.

This schema matches the orchestrator teammate's expected format exactly,
as defined in payment_exception_resolution_agent_mvp_plan.md Section 8.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class AgentResponse(BaseModel):
    # Core identity
    agent_name: str                        # e.g. "BeneficiaryAgent"
    classification: str                    # e.g. "incorrect_beneficiary"

    # Decision
    action: str                            # MVP action enum — see plan Section 8
    automation_allowed: bool = False       # Always False in MVP
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: str                        # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"

    # Evidence and explanation
    issue_detected: bool
    root_cause: str                        # Short technical root cause
    evidence: List[str]                    # Bullet list of supporting signals
    explanation: str                       # Human-readable explanation for the UI
    next_steps: List[str]                  # Ordered action list

    # Audit
    escalation_required: bool
    audit_notes: str                       # Full audit trail for logging

    def to_dict(self) -> dict:
        """Return plain dict — easy for the orchestrator to consume."""
        return self.model_dump()
