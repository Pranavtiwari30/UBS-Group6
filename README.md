# Payment Exception Resolution Orchestrator

An agentic, **recommendation-only** orchestrator for resolving payment exceptions at a bank.
It combines a deterministic rule engine with a two-tier LLM stack: specialist subagents on
**gpt-5.4-mini** and a final decision authority on **gpt-5.4**, all behind a hard safety floor.

The system **never moves money independently without strict deterministic approvals**. It is built as a conservative operations control plane, separating diagnosis from authority.

---

## Architecture

```text
canonical event (from mock API / fixture)
        │
        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 1. validate canonical schema        (schemas.py)            │
  │ 2. rule-based classification        (classifiers.py)        │
  │ 3. slice scoped subagent input      (slicers.py)            │
  │ 4. run specialist subagent          (agents/, gpt-5.4-mini) │
  │ 5. deterministic safety fallbacks   (safety.py)             │  ← hard floor
  │ 6. LLM final decision + handoff     (llm_reviewer.py)       │  ← gpt-5.4
  │ 7. re-apply safety floor on top     (safety.py)             │  ← hard floor again
  └─────────────────────────────────────────────────────────────┘
        │
        ▼
  final response: decision + evidence + checkpoints + fallbacks
```

### Two-tier model design

| Tier | Model (default) | Env var | Role |
|------|-----------------|---------|------|
| Specialist subagents | `gpt-5.4-mini` | `OPENAI_SUBAGENT_MODEL` | Each agent keeps deterministic logic as a baseline and refines it via a single forced tool call. Falls back to the baseline on any failure. |
| Final decision authority | `gpt-5.4` | `OPENAI_MODEL` | Independently inspects the case with **read-only tools**, may **re-route (hand off)** to a different specialist via `invoke_subagent`, and submits the final decision. |

### The Safety Floor (inviolable)

`apply_safety_fallbacks` runs **after** the deterministic agent *and again* on top of the LLM decision. The model can confirm, tighten, raise risk, add reason codes, force `MANUAL_REVIEW`, or re-route — but it can **never**:

- enable automation (`automation_allowed` forced to `false` for financial actions without full audit/lock),
- release or downgrade a compliance hold/escalation,
- ignore a compliance signal (any signal forces `ESCALATE_COMPLIANCE`),
- retry a payment when funds movement or finality is unknown.

If `OPENAI_API_KEY` is missing or any LLM call fails, the deterministic decision is kept and the failure is recorded as a checkpoint — the orchestrator is always runnable offline.

---

## Future Production Roadmap
Beyond the current MVP architecture, the golden production plan incorporates:
- **Event-Sourced Case Ledger**: Append-only case events for audit and replay.
- **Payment-Intent Locking & Idempotency**: Prevents duplicate payment actions across all operational channels.
- **Immutable Evidence Snapshots**: Bitemporal records of exact system knowledge at decision time.
- **Multi-user Operations**: RBAC, maker-checker workflows, and case leases.

---

## Setup & Running

The project uses a conda environment named `payment-exception-orchestrator`:

```bash
conda env create -f environment.yml      # first time
conda activate payment-exception-orchestrator
```

Configure the LLM stages by copying `.env.example` to `.env` and setting `OPENAI_API_KEY`. Without a key, the orchestrator runs deterministic-only.

### Tests (deterministic, no network)
```bash
PAYMENT_EXCEPTION_DISABLE_LLM=1 pytest tests -q
```

### Orchestrate one fixture (CLI)
```bash
python -m payment_exception_mvp.app \
  --fixture payment_exception_mvp/fixtures/beneficiary_invalid.json
```

### Run the mock API server
```bash
cd mock_server
uvicorn app:app --reload          # http://127.0.0.1:8000/docs
python generate_data.py           # regenerate synthetic data
```
