# Payment Exception Orchestrator MVP 30-Minute Implementation Plan

This plan is for implementing the orchestrator only, using the schema and safety rules from `plans/payment_exception_resolution_agent_mvp_plan.md`. Other teammates are building the four subagents, so this plan treats subagents as external collaborators behind a small adapter contract.

## 1. Objective

Build a runnable orchestrator that can:

1. Accept the canonical MVP payment exception payload.
2. Validate required canonical fields.
3. Create trace, case, idempotency, and checkpoint metadata.
4. Classify the exception deterministically into one selected agent or manual review.
5. Slice the canonical event into the selected agent's scoped input envelope.
6. Invoke exactly one subagent through a stable adapter interface.
7. Validate the subagent output.
8. Apply safety fallback rules.
9. Emit the final orchestrator response schema.

The orchestrator must stay recommendation-only. It must not move money, retry payments, cancel payments, repair beneficiaries, release holds, or contact clients.

## 2. Environment

Conda environment created:

```bash
conda activate payment-exception-orchestrator
python --version
```

Expected Python version:

```text
Python 3.10.x
```

Recreate the environment from the repo:

```bash
conda env create -f environment.yml
conda activate payment-exception-orchestrator
```

Core dependencies:

- `pydantic`: schema validation.
- `pytest`: smoke tests.
- `rich`: readable CLI/demo output.

## 3. Scope for the 30-minute sprint

### In scope

- Orchestrator core flow.
- Pydantic schema models or equivalent validation.
- Deterministic classification rules.
- Agent input slicing.
- Adapter interface for subagent calls.
- Temporary manual-review stubs when a subagent is unavailable.
- Safety fallback rules.
- CLI fixture runner.
- Five smoke fixtures or fixture expectations.

### Out of scope

- Subagent internal business logic.
- FastAPI server unless the CLI finishes early.
- Persistent storage.
- Real payment rails, notifications, or compliance system calls.
- LLM-based classification.
- Any financial side effects.

## 4. Proposed implementation structure

```text
payment_exception_mvp/
  __init__.py
  app.py                         # CLI entrypoint for fixture execution
  orchestrator.py                # Main orchestrate(payload) flow
  schemas.py                     # Pydantic models for canonical, agent input, agent output, final response
  classifiers.py                 # Deterministic priority classifier
  slicers.py                     # Canonical payload to scoped agent input mapping
  checkpoints.py                 # Checkpoint helper
  safety.py                      # Safety fallback layer
  agent_adapters.py              # Imports or stubs each subagent
  fixtures/
    beneficiary_invalid.json
    duplicate_submission.json
    compliance_hold.json
    network_failure.json
    unknown_exception.json
  agents/
    __init__.py
    beneficiary_agent.py         # Built by teammate or temporary stub
    duplicate_payment_agent.py   # Built by teammate or temporary stub
    compliance_agent.py          # Built by teammate or temporary stub
    network_agent.py             # Built by teammate or temporary stub
tests/
  test_orchestrator_smoke.py
```

Fastest path: implement CLI first, then add FastAPI only if there is extra time.

## 5. Phased 30-minute plan

| Phase | Timebox | Owner | Deliverable | Verification |
|---|---:|---|---|---|
| 0. Environment and alignment | 0-3 min | Orchestrator owner | Activate `payment-exception-orchestrator`, confirm Python 3.10, share handoff contract | `python --version` shows 3.10 |
| 1. File skeleton | 3-5 min | Orchestrator owner | Create package folders, CLI entrypoint, empty modules, fixture folder | Imports do not fail |
| 2. Schema models | 5-10 min | Orchestrator owner | Canonical input, agent envelope, agent output, final response, checkpoint models | Invalid fixture returns validation failure or manual review |
| 3. Deterministic classifier | 10-14 min | Orchestrator owner | Priority classifier from MVP plan | Five fixture payloads map to expected selected agent |
| 4. Agent input slicing | 14-19 min | Orchestrator owner | One slicer per selected agent, no full canonical payload leakage | Sliced payload includes only selected scoped context |
| 5. Adapter and subagent integration | 19-23 min | Orchestrator owner plus subagent owners | `agent_adapters.invoke(agent_name, agent_input)` calls teammate module or safe stub | Missing agent falls back to `MANUAL_REVIEW` |
| 6. Safety fallback layer | 23-26 min | Orchestrator owner | Rules override unsafe retry, duplicate, compliance, low confidence, invalid output | Unsafe sample response gets overridden |
| 7. Final response and CLI demo | 26-29 min | Orchestrator owner | Final schema response with checkpoints, evidence, selected agent, decision, fallbacks | CLI prints structured response |
| 8. Smoke test and handoff | 29-30 min | Orchestrator owner | Run smoke tests and share integration blockers | All ready fixtures pass or unavailable agents are explicitly stubbed |

## 6. Orchestrator flow

```text
orchestrate(canonical_payload)
  -> add checkpoint request_received
  -> validate canonical schema
  -> normalize missing optional sections to empty defaults where safe
  -> create trace_id, case_id, idempotency key
  -> classify using deterministic priority rules
  -> if ManualReviewFallback, build manual-review response
  -> slice selected agent input
  -> validate agent input envelope
  -> invoke selected subagent through adapter
  -> catch timeout, import error, crash, or invalid output
  -> validate common subagent output
  -> apply safety fallback rules
  -> build final response
  -> emit response with checkpoints
```

## 7. Deterministic classifier rules

Implement priority order exactly as the MVP plan specifies:

1. If `compliance.compliance_hold_status != NONE`, or `exception.exception_code` contains `COMPLIANCE`, `SANCTIONS`, `AML`, or `POLICY`, select `ComplianceAgent`.
2. Else if `exception.exception_code` contains `DUPLICATE`, or `duplicate_evidence.duplicate_candidates` is non-empty, select `DuplicatePaymentAgent`.
3. Else if `exception.exception_code` contains `BENEFICIARY`, `INVALID_ACCOUNT`, `INVALID_IFSC`, `INVALID_UPI`, or `NAME_MISMATCH`, select `BeneficiaryAgent`.
4. Else if `exception.exception_code` contains `NETWORK`, `TIMEOUT`, `NO_ACK`, `RAIL_UNAVAILABLE`, or `DOWNSTREAM`, select `NetworkAgent`.
5. Else select `ManualReviewFallback`.

Implementation note: uppercase the exception code before matching. Treat missing code as unknown.

## 8. Agent adapter design

Use one narrow adapter so the orchestrator is independent of teammate implementations:

```python
AGENT_MODULES = {
    "BeneficiaryAgent": "payment_exception_mvp.agents.beneficiary_agent",
    "DuplicatePaymentAgent": "payment_exception_mvp.agents.duplicate_payment_agent",
    "ComplianceAgent": "payment_exception_mvp.agents.compliance_agent",
    "NetworkAgent": "payment_exception_mvp.agents.network_agent",
}

def invoke(agent_name: str, agent_input: dict) -> dict:
    module = import_module(AGENT_MODULES[agent_name])
    return module.analyze(agent_input)
```

If import or invocation fails, the adapter should return an orchestrator-owned failure object or raise a controlled `AgentInvocationError`. The orchestrator then returns `MANUAL_REVIEW` with `agent_failed` and `agent_not_available` markers.

## 9. Subagent handoffs needed from teammates

The detailed handoff contract is in `plans/payment_exception_subagent_handoff_contract.md`.

Minimum ask from each subagent owner:

| Agent | Need by integration time | Default file | Default callable |
|---|---|---|---|
| BeneficiaryAgent | Function accepts scoped beneficiary envelope and returns common output schema | `payment_exception_mvp/agents/beneficiary_agent.py` | `analyze(agent_input: dict) -> dict` |
| DuplicatePaymentAgent | Function accepts duplicate evidence envelope and returns common output schema | `payment_exception_mvp/agents/duplicate_payment_agent.py` | `analyze(agent_input: dict) -> dict` |
| ComplianceAgent | Function fails closed on hold, AML, sanctions, or policy flags | `payment_exception_mvp/agents/compliance_agent.py` | `analyze(agent_input: dict) -> dict` |
| NetworkAgent | Function handles timeout, missing ACK, rail unavailable, finality unknown | `payment_exception_mvp/agents/network_agent.py` | `analyze(agent_input: dict) -> dict` |

Explicit teammate handoff requirements:

1. Do not require the full canonical payload.
2. Do not perform side effects.
3. Return a plain JSON-serializable dict.
4. Keep `automation_allowed=false`.
5. Use only accepted action codes unless agreed with orchestrator owner.
6. Return within 5 seconds for fixture data.
7. Share one sample input and one sample output for quick integration.

If a teammate cannot deliver by the integration window, the orchestrator will plug in a safe manual-review stub and mark it clearly in the final response.

## 10. Safety fallback implementation

After the subagent returns, the orchestrator owns final safety review.

| Condition | Orchestrator override |
|---|---|
| Compliance signal exists | Force `ESCALATE_COMPLIANCE` |
| Agent confidence below `policy.manual_review_threshold` | Force `MANUAL_REVIEW` unless action is already conservative hold or compliance escalation |
| Agent recommends retry but duplicate evidence exists | Force `HOLD_AND_RECONCILE` |
| Agent recommends retry but funds movement is unknown | Force `HOLD_AND_RECONCILE` |
| Agent recommends repair but beneficiary validation confidence is low | Force `REQUEST_CLIENT_CORRECTION` or `MANUAL_REVIEW` |
| Agent output schema invalid | Force `MANUAL_REVIEW` |
| Agent throws error | Force `MANUAL_REVIEW` |
| Unsupported exception type | Force `MANUAL_REVIEW` |

For MVP, do not execute the action. The action is only a recommendation.

## 11. Checkpoints to emit

Use this full checkpoint list so the demo shows traceability:

1. `request_received`
2. `canonical_schema_validated`
3. `payload_normalized`
4. `idempotency_key_created`
5. `classification_started`
6. `classification_completed`
7. `agent_selected`
8. `agent_input_sliced`
9. `agent_input_schema_validated`
10. `agent_invocation_started`
11. `agent_completed` or `agent_failed`
12. `agent_output_validated`
13. `safety_fallbacks_evaluated`
14. `final_decision_created`
15. `response_emitted`

Each checkpoint should include at minimum:

```json
{
  "name": "agent_input_schema_validated",
  "status": "passed",
  "details": "NetworkAgent input contained only network-scoped context"
}
```

## 12. Final response shape

The final response should match the MVP plan:

```json
{
  "trace_id": "trace-evt-001",
  "case_id": "case-pay-001",
  "event_id": "evt-001",
  "payment_id": "pay-001",
  "classification": "incorrect_beneficiary",
  "selected_agent": "BeneficiaryAgent",
  "decision": {
    "action": "REQUEST_CLIENT_CORRECTION",
    "automation_allowed": false,
    "confidence": 0.88,
    "risk_level": "MEDIUM",
    "reason_codes": ["INVALID_BENEFICIARY", "CLIENT_INPUT_REQUIRED"]
  },
  "evidence": ["beneficiary_validation.validation_status=FAILED"],
  "checkpoints": [],
  "fallbacks_triggered": [],
  "explanation": "Beneficiary validation failed and no deterministic correction is available.",
  "next_steps": ["Create client outreach task"]
}
```

## 13. Smoke tests

Run these at the end of the 30-minute sprint:

| Test | Expected result |
|---|---|
| Beneficiary invalid fixture | `selected_agent=BeneficiaryAgent`, action is `REQUEST_CLIENT_CORRECTION` or safe fallback |
| Duplicate fixture | `selected_agent=DuplicatePaymentAgent`, action is `CANCEL_DUPLICATE` or safe hold |
| Compliance hold fixture | `selected_agent=ComplianceAgent`, action is `ESCALATE_COMPLIANCE`, `automation_allowed=false` |
| Network timeout fixture | `selected_agent=NetworkAgent`, action is `HOLD_AND_RECONCILE` or conservative equivalent |
| Unknown fixture | `selected_agent=ManualReviewFallback`, action is `MANUAL_REVIEW` |
| Invalid subagent output | Final action is `MANUAL_REVIEW`, checkpoint records `agent_output_invalid` |
| Missing subagent module | Final action is `MANUAL_REVIEW`, fallback records `agent_not_available` |

Suggested commands after implementation:

```bash
conda activate payment-exception-orchestrator
python -m payment_exception_mvp.app --fixture payment_exception_mvp/fixtures/beneficiary_invalid.json
python -m pytest -q
```

## 14. Definition of done

The orchestrator sprint is complete when:

- The conda env is active with Python 3.10.
- CLI can process at least one valid fixture end to end.
- Classifier picks the correct agent for all five fixture categories.
- Agent input is scoped and validated before invocation.
- Missing, crashing, or invalid subagents safely return manual review.
- Safety fallback rules are applied after agent output.
- Final response includes selected agent, decision, evidence, checkpoints, fallbacks, explanation, and next steps.
- Subagent owners have the handoff contract and know the default callable contract.

## 15. Immediate implementation order if coding starts now

1. Create `schemas.py` with only required fields from the MVP canonical event and common output schema.
2. Create `checkpoints.py` with `add_checkpoint(name, status="passed", details=None)`.
3. Create `classifiers.py` and verify mapping with five tiny dict fixtures.
4. Create `slicers.py` with explicit field copies per agent.
5. Create `agent_adapters.py` with dynamic import plus safe `AgentInvocationError`.
6. Create `safety.py` with override rules.
7. Create `orchestrator.py` that wires the modules together.
8. Create `app.py` CLI for one fixture path.
9. Add smoke tests for classification and failure fallback.
10. Plug in teammate subagents as they arrive.
