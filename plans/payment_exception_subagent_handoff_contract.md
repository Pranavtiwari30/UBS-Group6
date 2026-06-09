# Payment Exception Subagent Handoff Contract

This handoff is for the teammates building the four MVP subagents. The orchestrator owner will implement validation, deterministic classification, scoped input slicing, checkpointing, safety fallbacks, and final response assembly. Subagent owners only need to implement their domain investigation function and return the common output schema.

## 1. Integration deadline for 30-minute build

For the 30-minute orchestrator sprint, each subagent owner should provide the following as soon as possible:

1. Python module path.
2. Callable name.
3. One valid sample output.
4. Any agent-specific action codes they expect to return.
5. Confirmation that their agent does not perform side effects.

Default integration contract if no alternative is agreed:

```python
def analyze(agent_input: dict) -> dict:
    """Return the common subagent output schema as a JSON-serializable dict."""
```

Default file paths:

```text
payment_exception_mvp/agents/beneficiary_agent.py
payment_exception_mvp/agents/duplicate_payment_agent.py
payment_exception_mvp/agents/compliance_agent.py
payment_exception_mvp/agents/network_agent.py
```

If a subagent is not ready, the orchestrator will use a temporary adapter stub that returns `MANUAL_REVIEW` and marks `fallbacks_triggered=["agent_not_available"]`. This keeps the demo safe and lets each agent be plugged in later without changing orchestrator logic.

## 2. Shared input envelope

Every subagent receives a JSON-safe dict shaped like this:

```json
{
  "schema_version": "mvp-agent-1.0",
  "trace_id": "trace-evt-001",
  "case_id": "case-pay-001",
  "event_id": "evt-001",
  "payment_id": "pay-001",
  "agent_task_id": "task-beneficiary-pay-001",
  "agent_name": "BeneficiaryAgent",
  "created_at": "2026-06-09T06:00:02Z",
  "policy": {
    "automation_mode": "RECOMMENDATION_ONLY",
    "manual_review_threshold": 0.75
  },
  "context": {}
}
```

Rules:

- Do not require access to the original canonical event.
- Do not mutate the input object in place.
- Do not return Pydantic objects, dataclasses, or custom classes. Return a plain dict.
- Do not call payment execution, retry, cancellation, repair, hold release, or notification systems.
- Keep `automation_allowed` as `false` for all MVP financial actions.

## 3. Required output schema

Every subagent must return the same output shape:

```json
{
  "agent_name": "BeneficiaryAgent",
  "classification": "incorrect_beneficiary",
  "action": "REQUEST_CLIENT_CORRECTION",
  "automation_allowed": false,
  "confidence": 0.88,
  "risk_level": "MEDIUM",
  "reason_codes": ["INVALID_BENEFICIARY", "CLIENT_INPUT_REQUIRED"],
  "evidence": [
    "beneficiary_validation.validation_status=FAILED"
  ],
  "fallbacks_triggered": [],
  "explanation": "Plain-English rationale for the recommendation.",
  "next_steps": [
    "Operational follow-up step"
  ]
}
```

Validation rules:

- `confidence` must be between `0.0` and `1.0`.
- `risk_level` must be `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`.
- `automation_allowed` must be `false` for MVP.
- `reason_codes`, `evidence`, and `next_steps` must be lists of strings.
- The `agent_name` must match the selected agent.
- Invalid or missing fields cause orchestrator fallback to `MANUAL_REVIEW`.

## 4. Action codes the orchestrator will accept

Recommended common action codes:

| Action | Meaning |
|---|---|
| `REQUEST_CLIENT_CORRECTION` | Client or ops must correct beneficiary details before resubmission |
| `RECOMMEND_REPAIR` | Data appears repairable, but MVP still recommends only |
| `CANCEL_DUPLICATE` | Candidate appears to be a duplicate that should not proceed |
| `HOLD_AND_RECONCILE` | Hold action pending status, ledger, or network reconciliation |
| `ESCALATE_COMPLIANCE` | Compliance or sanctions review required |
| `MANUAL_REVIEW` | Safe fallback for uncertainty, invalid evidence, or unsupported cases |
| `NO_ACTION_MONITOR` | Watch state because no safe immediate operation is available |

Any new action code must be shared with the orchestrator owner before integration. Unknown action codes will be treated as `MANUAL_REVIEW` unless added to the validation enum.

## 5. Beneficiary Agent handoff

Owner deliverable:

```text
module: payment_exception_mvp/agents/beneficiary_agent.py
callable: analyze(agent_input: dict) -> dict
agent_name: BeneficiaryAgent
```

The orchestrator will provide context fields:

- `payment_summary.client_id`
- `payment_summary.payment_rail`
- `payment_summary.amount`
- `payment_summary.currency`
- `payment_summary.current_transaction_status`
- `payment_summary.funds_movement_status`
- `exception.exception_code`
- `exception.description`
- `beneficiary.*`
- `beneficiary_validation.*`
- `client_contact_history`

Expected MVP behavior:

- Missing or invalid beneficiary details should return `REQUEST_CLIENT_CORRECTION`.
- Deterministic correction with high confidence can return `RECOMMEND_REPAIR`.
- Unknown funds movement should return `MANUAL_REVIEW` or another conservative action.

## 6. Duplicate Payment Agent handoff

Owner deliverable:

```text
module: payment_exception_mvp/agents/duplicate_payment_agent.py
callable: analyze(agent_input: dict) -> dict
agent_name: DuplicatePaymentAgent
```

The orchestrator will provide context fields:

- `payment_summary.client_id`
- `payment_summary.client_reference`
- `payment_summary.amount`
- `payment_summary.currency`
- `payment_summary.submitted_timestamp`
- `payment_summary.current_transaction_status`
- `payment_summary.funds_movement_status`
- `beneficiary_fingerprint`
- `duplicate_evidence.payment_fingerprint`
- `duplicate_evidence.duplicate_candidates`
- `prior_retry_events`

Expected MVP behavior:

- Confirmed duplicate candidate should return `CANCEL_DUPLICATE` as a recommendation only.
- Unclear duplicate status should return `HOLD_AND_RECONCILE` or `MANUAL_REVIEW`.
- Never recommend retry when duplicate candidates exist.

## 7. Compliance Agent handoff

Owner deliverable:

```text
module: payment_exception_mvp/agents/compliance_agent.py
callable: analyze(agent_input: dict) -> dict
agent_name: ComplianceAgent
```

The orchestrator will provide context fields:

- `payment_summary.client_id`
- `payment_summary.amount`
- `payment_summary.currency`
- `payment_summary.payment_rail`
- `payment_summary.current_transaction_status`
- `exception.exception_code`
- `exception.description`
- `compliance.compliance_hold_status`
- `compliance.screening_result`
- `compliance.screening_reference`
- `compliance.risk_flags`

Expected MVP behavior:

- Any active compliance hold, sanctions hit, AML flag, or policy flag should return `ESCALATE_COMPLIANCE`.
- Compliance must fail closed. If evidence is missing or uncertain, return `ESCALATE_COMPLIANCE` or `MANUAL_REVIEW`.
- Never recommend release of a hold in the MVP.

## 8. Network Agent handoff

Owner deliverable:

```text
module: payment_exception_mvp/agents/network_agent.py
callable: analyze(agent_input: dict) -> dict
agent_name: NetworkAgent
```

The orchestrator will provide context fields:

- `payment_summary.payment_rail`
- `payment_summary.amount`
- `payment_summary.currency`
- `payment_summary.current_transaction_status`
- `status_evidence.funds_movement_status`
- `status_evidence.ledger_debit_status`
- `status_evidence.network_finality`
- `network.network_acknowledgements`
- `network.rail_health_status`
- `network.rail_incident_id`
- `prior_retry_events`

Expected MVP behavior:

- Timeout, missing ACK, or rail incident should normally return `HOLD_AND_RECONCILE`.
- Only return retry-like recommendations if funds did not move and network finality is final failed. The orchestrator will still keep automation disabled.
- Unknown finality or unknown funds movement must be conservative.

## 9. Handoff acceptance checklist

A subagent is ready to integrate when:

- It exposes the default callable or tells the orchestrator owner the exact adapter needed.
- It accepts only the scoped envelope and does not require canonical event access.
- It returns the required common output schema.
- It has one sample input and one sample output checked into the repo or shared in chat.
- It can handle missing optional fields without crashing.
- It returns within 5 seconds for fixture data.

## 10. Orchestrator owner commitments

The orchestrator will:

- Validate the canonical event before routing.
- Apply deterministic priority classification from the MVP plan.
- Slice the canonical payload into exactly one subagent context.
- Validate the selected subagent input envelope before invocation.
- Catch subagent exceptions and timeouts.
- Validate subagent output.
- Apply safety fallbacks after every subagent response.
- Return the final orchestrator response schema with checkpoints and evidence.
