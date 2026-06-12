from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

ACCEPTED_ACTIONS = {
    "REQUEST_CLIENT_CORRECTION",
    "RECOMMEND_REPAIR",
    "CANCEL_DUPLICATE",
    "HOLD_AND_RECONCILE",
    "ESCALATE_COMPLIANCE",
    "MANUAL_REVIEW",
    "NO_ACTION_MONITOR",
    "RECOMMEND_RETRY",
}


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Payment(StrictBaseModel):
    payment_id: str
    client_id: str
    client_reference: str | None = None
    account_id: str | None = None
    payment_rail: str | None = None
    payment_type: str | None = None
    amount: float
    currency: str
    submitted_timestamp: str | None = None
    current_transaction_status: str


class Beneficiary(StrictBaseModel):
    beneficiary_id: str | None = None
    name: str | None = None
    account_number_masked: str | None = None
    ifsc: str | None = None
    upi_id: str | None = None
    country: str | None = None
    beneficiary_fingerprint: str | None = None


class ExceptionInfo(StrictBaseModel):
    exception_code: str | None = None
    exception_type_hint: str | None = None
    description: str | None = None
    severity: str | None = None


class StatusEvidence(StrictBaseModel):
    funds_movement_status: str | None = "UNKNOWN"
    ledger_debit_status: str | None = "UNKNOWN"
    network_finality: str | None = "UNKNOWN"


class BeneficiaryValidation(StrictBaseModel):
    validation_status: str | None = None
    failed_fields: list[str] = Field(default_factory=list)
    suggested_correction: Any = None
    validation_confidence: float | None = None


class DuplicateEvidence(StrictBaseModel):
    duplicate_candidates: list[dict[str, Any]] = Field(default_factory=list)
    payment_fingerprint: str | None = None


class Compliance(StrictBaseModel):
    compliance_hold_status: str | None = "NONE"
    screening_result: str | None = "UNKNOWN"
    screening_reference: str | None = None
    risk_flags: list[str] = Field(default_factory=list)


class Network(StrictBaseModel):
    network_acknowledgements: list[dict[str, Any]] = Field(default_factory=list)
    rail_health_status: str | None = "UNKNOWN"
    rail_incident_id: str | None = None


class History(StrictBaseModel):
    prior_retry_events: list[dict[str, Any]] = Field(default_factory=list)
    client_contact_history: list[dict[str, Any]] = Field(default_factory=list)


class Policy(StrictBaseModel):
    automation_mode: str = "RECOMMENDATION_ONLY"
    manual_review_threshold: float = 0.75
    safe_retry_threshold: float = 0.97
    duplicate_cancel_threshold: float = 0.95
    beneficiary_repair_threshold: float = 0.98


class CanonicalPaymentException(StrictBaseModel):
    schema_version: str = "mvp-1.0"
    event_id: str
    event_timestamp: str | None = None
    source_system: str | None = None
    payment: Payment
    beneficiary: Beneficiary = Field(default_factory=Beneficiary)
    exception: ExceptionInfo
    status_evidence: StatusEvidence = Field(default_factory=StatusEvidence)
    beneficiary_validation: BeneficiaryValidation = Field(default_factory=BeneficiaryValidation)
    duplicate_evidence: DuplicateEvidence = Field(default_factory=DuplicateEvidence)
    compliance: Compliance = Field(default_factory=Compliance)
    network: Network = Field(default_factory=Network)
    history: History = Field(default_factory=History)
    policy: Policy = Field(default_factory=Policy)


class AgentInputEnvelope(StrictBaseModel):
    schema_version: str = "mvp-agent-1.0"
    trace_id: str
    case_id: str
    event_id: str
    payment_id: str
    agent_task_id: str
    agent_name: str
    created_at: str
    policy: dict[str, Any]
    context: dict[str, Any]


class AgentOutput(StrictBaseModel):
    agent_name: str
    classification: str
    action: str
    automation_allowed: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    reason_codes: list[str]
    evidence: list[str]
    fallbacks_triggered: list[str] = Field(default_factory=list)
    explanation: str
    next_steps: list[str]

    @field_validator("action")
    @classmethod
    def action_must_be_known(cls, value: str) -> str:
        if value not in ACCEPTED_ACTIONS:
            raise ValueError(f"unsupported action: {value}")
        return value

    @field_validator("automation_allowed")
    @classmethod
    def automation_disabled_for_mvp(cls, value: bool) -> bool:
        if value:
            raise ValueError("automation_allowed must be false for MVP")
        return value


class FinalDecision(BaseModel):
    action: str
    automation_allowed: bool
    confidence: float
    risk_level: RiskLevel
    reason_codes: list[str]


class FinalResponse(BaseModel):
    trace_id: str
    case_id: str
    event_id: str
    payment_id: str
    classification: str
    selected_agent: str
    decision: FinalDecision
    evidence: list[str]
    checkpoints: list[dict[str, Any]]
    fallbacks_triggered: list[str]
    explanation: str
    next_steps: list[str]


def validate_agent_output(raw_output: dict[str, Any], expected_agent_name: str) -> AgentOutput:
    output = AgentOutput.model_validate(raw_output)
    if output.agent_name != expected_agent_name:
        raise ValidationError.from_exception_data(
            "AgentOutput",
            [
                {
                    "type": "value_error",
                    "loc": ("agent_name",),
                    "msg": "agent_name does not match selected agent",
                    "input": output.agent_name,
                    "ctx": {"error": ValueError("agent_name does not match selected agent")},
                }
            ],
        )
    return output
