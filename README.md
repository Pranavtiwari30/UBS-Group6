# Payment Exception Resolution Orchestrator

An agentic, **recommendation-only** orchestrator for resolving payment exceptions at a bank.
It combines a deterministic rule engine with a two-tier LLM stack: specialist subagents on
**gpt-5.4-mini** and a final decision authority on **gpt-5.4**, all behind a hard safety floor.

The system **never moves money**. It never retries, cancels, repairs, releases holds, or
contacts clients — it only produces a recommended action, a risk level, reason codes, and an
auditable checkpoint trail. `automation_allowed` is always `false`.

---

## Architecture

```
canonical event (from mock API / fixture)
        │
        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 1. validate canonical schema        (schemas.py)             │
  │ 2. rule-based classification        (classifiers.py)         │
  │ 3. slice scoped subagent input      (slicers.py)             │
  │ 4. run specialist subagent          (agents/, gpt-5.4-mini)  │
  │ 5. deterministic safety fallbacks   (safety.py)              │  ← hard floor
  │ 6. LLM final decision + handoff     (llm_reviewer.py, gpt-5.4)│
  │ 7. re-apply safety floor on top     (safety.py)              │  ← hard floor again
  └─────────────────────────────────────────────────────────────┘
        │
        ▼
  final response: decision + evidence + checkpoints + fallbacks
```

### Two-tier model design

| Tier | Model (default) | Env var | Role |
|------|-----------------|---------|------|
| Specialist subagents | `gpt-5.4-mini` | `OPENAI_SUBAGENT_MODEL` | Each agent (beneficiary / duplicate / compliance / network) keeps deterministic logic as a baseline and refines it via a single forced `submit_analysis` tool call. Falls back to the baseline on any failure. |
| Final decision authority | `gpt-5.4` | `OPENAI_MODEL` | Independently inspects the case with **read-only tools**, may **re-route (hand off)** to a different specialist via `invoke_subagent`, and submits the final decision. |

### The safety floor (inviolable)

`apply_safety_fallbacks` runs **after** the deterministic agent *and again* on top of the LLM
decision. The model can confirm, tighten, raise risk, add reason codes, force `MANUAL_REVIEW`,
or re-route — but it can **never**:

- enable automation (`automation_allowed` forced to `false`),
- release or downgrade a compliance hold/escalation,
- ignore a compliance signal (any signal forces `ESCALATE_COMPLIANCE`).

If `OPENAI_API_KEY` is missing or any LLM call fails, the deterministic decision is kept and the
failure is recorded as a checkpoint — the orchestrator is always runnable offline.

---

## Repository layout

```
payment_exception_mvp/
  orchestrator.py        # pipeline wiring + checkpoints
  classifiers.py         # deterministic exception → agent routing
  slicers.py             # scoped, minimal context per subagent
  safety.py              # the hard safety floor
  schemas.py             # Pydantic canonical + agent + response models
  checkpoints.py         # audit trail recorder
  agent_adapters.py      # dynamic subagent invocation
  app.py                 # CLI: run one fixture through the orchestrator
  llm_config.py          # LLMConfig + zero-dependency .env loader
  llm_reviewer.py        # gpt-5.4 final-decision tool-calling loop
  llm_tools.py           # read-only tools + submit_decision schema
  agents/
    _specialist.py       # shared gpt-5.4-mini refine() helper
    beneficiary_agent.py  duplicate_payment_agent.py
    compliance_agent.py   network_agent.py
  fixtures/              # one canonical payload per exception type

mock_server/             # FastAPI mock of upstream banking systems
  app.py                 # FastAPI app (users/payments/compliance/exceptions)
  generate_data.py       # synthetic data generator
  canonical_adapter.py   # mock record → canonical exception payload
  data/                  # generated JSON (exceptions, payments, compliance, users)

tests/                   # pytest suite (deterministic + LLM-mocked + mock-API)
outputs/                 # sample live-run responses, one per exception type
```

---

## Setup

The project uses a conda environment named `payment-exception-orchestrator`:

```bash
conda env create -f environment.yml      # first time
conda activate payment-exception-orchestrator
```

Configure the LLM stages by copying the template and adding your key:

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY=sk-...
```

`.env` is gitignored. Real environment variables always take precedence over `.env`.
Without a key, the orchestrator runs deterministic-only.

### Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `OPENAI_API_KEY` | — | Enables both LLM tiers. Unset = deterministic-only. |
| `OPENAI_MODEL` | `gpt-5.4` | Final decision authority. |
| `OPENAI_SUBAGENT_MODEL` | `gpt-5.4-mini` | Specialist subagents. |
| `OPENAI_BASE_URL` | (blank) | Custom OpenAI-compatible endpoint. |
| `OPENAI_TEMPERATURE` | (blank) | Sampling temperature; blank = model default. |
| `OPENAI_MAX_TOOL_ITERATIONS` | `8` | Reviewer tool-loop cap. |
| `PAYMENT_EXCEPTION_DISABLE_LLM` | (blank) | `1`/`true`/`yes` forces deterministic-only. |

---

## Running

### Tests (deterministic, no network)

```bash
PAYMENT_EXCEPTION_DISABLE_LLM=1 pytest tests -q
```

LLM-path tests use injected fakes, so they make no real calls even with the flag off.

### Orchestrate one fixture (CLI)

```bash
# deterministic only
PAYMENT_EXCEPTION_DISABLE_LLM=1 python -m payment_exception_mvp.app \
  --fixture payment_exception_mvp/fixtures/beneficiary_invalid.json

# live (gpt-5.4-mini subagents + gpt-5.4 reviewer)
python -m payment_exception_mvp.app \
  --fixture payment_exception_mvp/fixtures/beneficiary_invalid.json
```

Fixtures: `beneficiary_invalid`, `duplicate_submission`, `compliance_hold`,
`network_failure`, `unknown_exception`.

### Orchestrate against the mock API data

```bash
python - <<'PY'
import sys; sys.path.insert(0, "mock_server")
from canonical_adapter import get_exception_by_case_id, canonicalize_exception
from payment_exception_mvp.orchestrator import orchestrate
import json
canonical = canonicalize_exception(get_exception_by_case_id("CASE1011"))
print(json.dumps(orchestrate(canonical), indent=2))
PY
```

### Run the mock API server

```bash
cd mock_server
uvicorn app:app --reload          # http://127.0.0.1:8000/docs
python generate_data.py           # regenerate synthetic data
```

---

## Example: a real handoff

On a duplicate-payment case whose underlying client carries an AML risk flag, the gpt-5.4
reviewer inspected the compliance evidence, **handed off** `DuplicatePaymentAgent → ComplianceAgent`,
and the safety floor enforced `ESCALATE_COMPLIANCE`:

```
selected_agent: ComplianceAgent   action: ESCALATE_COMPLIANCE   risk: CRITICAL
reason_codes: [COMPLIANCE_HOLD, FAIL_CLOSED, AML_RISK_FLAG, DUPLICATE_CANDIDATE_FOUND]
checkpoint llm_rerouted: DuplicatePaymentAgent -> ComplianceAgent via [ComplianceAgent]
```

See `outputs/` for full responses per exception type.
