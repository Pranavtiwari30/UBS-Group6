import logging
import re
from enum import Enum
from typing import Dict, Any, List, Tuple
from pydantic import BaseModel, Field, field_validator
from typing_extensions import Literal

# Configure logging
logger = logging.getLogger("agents.network_agent")

# =====================================================================
# 1. Domain Enums
# =====================================================================

class AgentAction(str, Enum):
    HOLD_AND_RECONCILE = "HOLD_AND_RECONCILE"
    WAIT_FOR_NETWORK_RECOVERY = "WAIT_FOR_NETWORK_RECOVERY"
    RECOMMEND_SAFE_RETRY = "RECOMMEND_SAFE_RETRY"
    MANUAL_REVIEW = "MANUAL_REVIEW"

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

# =====================================================================
# 2. Input/Output Schemas
# =====================================================================

class AgentInput(BaseModel):
    payment_id: str = Field(..., min_length=1)
    payment_rail: str = Field(..., min_length=1)
    network_acknowledgements: List[Dict[str, Any]] = Field(default_factory=list)
    current_transaction_status: str = Field(..., min_length=1)
    prior_retry_events: List[Dict[str, Any]] = Field(default_factory=list)
    submitted_timestamp: str = Field(..., min_length=1)
    exception_code: str = Field(..., min_length=1)

    @field_validator("submitted_timestamp")
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        iso_pattern = re.compile(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
        )
        if not iso_pattern.match(v):
            raise ValueError("submitted_timestamp must be in a valid ISO 8601 format (e.g., YYYY-MM-DDTHH:MM:SSZ)")
        return v

class AgentOutput(BaseModel):
    agent_name: Literal["NetworkAgent"] = "NetworkAgent"
    classification: Literal["network_failure"] = "network_failure"
    action: AgentAction
    automation_allowed: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    risk_level: RiskLevel
    evidence: List[str] = Field(default_factory=list)
    explanation: str
    next_steps: List[str] = Field(default_factory=list)

# =====================================================================
# 3. Core Processing Components
# =====================================================================

class EvidenceAnalyzer:
    """
    Analyzes transaction details and compiles an evolutionary list of audit evidence.
    """
    def __init__(self) -> None:
        self.logger = logging.getLogger("agents.network_agent.EvidenceAnalyzer")
        self.outage_keywords = {"NETWORK", "TIMEOUT", "NO_ACK", "RAIL_UNAVAILABLE", "DOWNSTREAM"}
        self.negative_keywords = {"NACK", "REJECTED", "RETURNED", "DECLINED", "ERROR", "FAILED", "RJCT", "RJCT_LOST"}

    def analyze(self, data: AgentInput) -> Dict[str, Any]:
        self.logger.debug(f"Starting evidence analysis for payment ID: {data.payment_id}")
        
        status = data.current_transaction_status.upper()
        exc_code = data.exception_code.upper()
        retries = len(data.prior_retry_events)
        acks = data.network_acknowledgements
        no_acks = len(acks) == 0

        # Scan for outage indicators in exception code
        is_outage_exception = any(kw in exc_code for kw in self.outage_keywords)

        # Scan for failure confirmation in acknowledgements
        has_failure_ack = False
        for ack in acks:
            combined = f"{str(ack.get('status', ''))} {str(ack.get('code', ''))} {str(ack.get('message', ''))}".upper()
            words = set(re.findall(r'[A-Z0-9_]+', combined))
            if self.negative_keywords.intersection(words):
                has_failure_ack = True
                break

        # Compile evidence logs
        evidence_list = [
            f"Payment ID: {data.payment_id}",
            f"Payment Rail: {data.payment_rail}",
            f"Current status: '{status}'",
            f"Exception code: '{exc_code}'",
            f"Prior retry attempts: {retries}",
            f"No network acknowledgements: {no_acks}",
            f"Negative ACK found: {has_failure_ack}",
            f"Outage exception matched: {is_outage_exception}"
        ]

        analysis_result = {
            "payment_id": data.payment_id,
            "payment_rail": data.payment_rail,
            "status": status,
            "exception_code": exc_code,
            "retries": retries,
            "no_acks": no_acks,
            "has_failure_ack": has_failure_ack,
            "is_outage_exception": is_outage_exception,
            "evidence": evidence_list
        }
        
        self.logger.info("Evidence compilation completed successfully.")
        return analysis_result


class DecisionEngine:
    """
    Determines the resolution Action based on deterministic priority rules.
    """
    def __init__(self) -> None:
        self.logger = logging.getLogger("agents.network_agent.DecisionEngine")

    def evaluate(self, analysis: Dict[str, Any]) -> Tuple[AgentAction, str, List[str]]:
        self.logger.debug("Evaluating decision engine rules.")
        
        status = analysis["status"]
        retries = analysis["retries"]
        no_acks = analysis["no_acks"]
        has_failure_ack = analysis["has_failure_ack"]
        is_outage_exception = analysis["is_outage_exception"]

        # Priority Rule 1: No acknowledgement exists AND status is UNKNOWN or PENDING
        status_is_unknown_or_pending = status in {"UNKNOWN", "PENDING"}
        if no_acks and status_is_unknown_or_pending:
            self.logger.info("Rule Priority 1 Match: No ACK & UNKNOWN/PENDING status.")
            return (
                AgentAction.HOLD_AND_RECONCILE,
                "No network acknowledgement exists and the transaction status is unresolved. Hold and reconcile is required to check if the rail received the payment.",
                [
                    "Place payment on hold.",
                    "Verify payment state directly with target clearing gateway."
                ]
            )

        # Priority Rule 2: Exception code contains outage keywords
        if is_outage_exception:
            self.logger.info("Rule Priority 2 Match: Outage exception code.")
            return (
                AgentAction.WAIT_FOR_NETWORK_RECOVERY,
                "Exception code indicates a temporary network outage or timeout. Wait for network recovery before retrying.",
                [
                    "Schedule automated retry after a backoff period.",
                    "Ping network rail endpoint to monitor recovery."
                ]
            )

        # Priority Rule 3: Acknowledgement confirms failure AND no prior retry exists
        has_prior_retries = retries > 0
        if has_failure_ack and not has_prior_retries:
            self.logger.info("Rule Priority 3 Match: Failure ACK without prior retry history.")
            return (
                AgentAction.RECOMMEND_SAFE_RETRY,
                "The payment rail explicitly rejected the transaction and no prior retry attempt exists. It is safe to retry.",
                [
                    "Initiate safe automated retry with same details.",
                    "Ensure payment fields match rail validation schema."
                ]
            )

        # Priority Rule 4: Retry history exists AND status remains uncertain
        is_uncertain_outcome = status in {"PENDING", "UNKNOWN", "SENT", "PROCESSING"}
        if has_prior_retries and is_uncertain_outcome:
            self.logger.info("Rule Priority 4 Match: Retries exist but outcome remains uncertain.")
            return (
                AgentAction.HOLD_AND_RECONCILE,
                "Prior retry history exists and the transaction outcome remains uncertain. Hold and reconcile is required to prevent double billing.",
                [
                    "Place payment on absolute hold.",
                    "Initiate manual ledger reconciliation against clearing reports.",
                    "Check the clearing bank statement."
                ]
            )

        # Priority Rule 5 / Fallback: Incomplete evidence or unmatched state
        self.logger.warning("Unmatched payment exception state. Defaulting to L2 operations review.")
        return (
            AgentAction.MANUAL_REVIEW,
            "The payment exception state did not match any automated deterministic rules.",
            [
                "Escalate payment transaction to Payment Operations L2 support."
            ]
        )


class RiskAssessmentEngine:
    """
    Assesses the risk level and calculates assessment confidence.
    """
    def __init__(self) -> None:
        self.logger = logging.getLogger("agents.network_agent.RiskAssessmentEngine")

    def assess(self, action: AgentAction, analysis: Dict[str, Any]) -> Tuple[RiskLevel, float]:
        self.logger.debug(f"Assessing risk levels for action: {action.value}")
        
        retries = analysis["retries"]
        
        if action == AgentAction.HOLD_AND_RECONCILE:
            risk = RiskLevel.HIGH
            # Rule 4 vs Rule 1
            confidence = 0.95 if retries > 0 else 0.90
        elif action == AgentAction.WAIT_FOR_NETWORK_RECOVERY:
            risk = RiskLevel.MEDIUM
            confidence = 0.85  # Rule 2
        elif action == AgentAction.RECOMMEND_SAFE_RETRY:
            risk = RiskLevel.LOW
            confidence = 0.95  # Rule 3
        else:
            # MANUAL_REVIEW
            risk = RiskLevel.HIGH
            # If we scored 1.0 already for validation, preserve it, else default to 0.70
            confidence = 0.70

        self.logger.info(f"Risk Assessment: {risk.value}, Confidence: {confidence}")
        return risk, confidence


class ResponseBuilder:
    """
    Constructs the final response payload matching the required output schema.
    """
    def __init__(self) -> None:
        self.logger = logging.getLogger("agents.network_agent.ResponseBuilder")

    def build(
        self,
        action: AgentAction,
        risk_level: RiskLevel,
        confidence: float,
        evidence: List[str],
        explanation: str,
        next_steps: List[str]
    ) -> Dict[str, Any]:
        
        # automation_allowed is only True for safe-to-retry and outage-polling actions
        automation_allowed = action in {AgentAction.RECOMMEND_SAFE_RETRY, AgentAction.WAIT_FOR_NETWORK_RECOVERY}
        
        output = AgentOutput(
            agent_name="NetworkAgent",
            classification="network_failure",
            action=action,
            automation_allowed=automation_allowed,
            confidence=confidence,
            risk_level=risk_level,
            evidence=evidence,
            explanation=explanation,
            next_steps=next_steps
        )
        
        return output.model_dump()

# =====================================================================
# 4. Exposed Entrypoint
# =====================================================================

def analyze(agent_input: dict) -> dict:
    """
    Analyzes payment network failure exception events.
    Receives a raw dictionary representing the input schema,
    and returns a structured action recommendation.
    """
    logger.info("Executing network agent analysis.")

    # Instantiate component layers
    analyzer = EvidenceAnalyzer()
    decision_engine = DecisionEngine()
    risk_engine = RiskAssessmentEngine()
    response_builder = ResponseBuilder()

    # Rule Priority 5: If evidence is incomplete (validation failure)
    try:
        input_model = AgentInput(**agent_input)
    except Exception as e:
        logger.error(f"Rule Priority 5 Triggered (Evidence Incomplete / Schema Mismatch): {e}", exc_info=True)
        err_msg = f"Input validation failed: {str(e)}"
        
        output = AgentOutput(
            agent_name="NetworkAgent",
            classification="network_failure",
            action=AgentAction.MANUAL_REVIEW,
            automation_allowed=False,
            confidence=1.00,
            risk_level=RiskLevel.HIGH,
            evidence=[err_msg],
            explanation="Required evidence is missing or invalid. Manual review is required.",
            next_steps=[
                "Verify orchestrator schema format.",
                "Manually verify payment details in core ledger."
            ]
        )
        return output.model_dump()

    # Step 2: Compile facts
    analysis = analyzer.analyze(input_model)

    # Step 3: Run rules
    action, explanation, next_steps = decision_engine.evaluate(analysis)

    # Step 4: Run risk and confidence scoring
    risk_level, confidence = risk_engine.assess(action, analysis)

    # Step 5: Format response
    return response_builder.build(
        action=action,
        risk_level=risk_level,
        confidence=confidence,
        evidence=analysis["evidence"],
        explanation=explanation,
        next_steps=next_steps
    )
