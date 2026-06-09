# Project Context

## Repository purpose

This repository currently contains planning material for a Payment Exception Resolution Agent, an agentic AI system for diagnosing and routing failed or held payment transactions.

## Important paths

- `plans/payment_exception_resolution_agent_problem_statement.md`: Source problem statement and expected deliverables.
- `plans/payment_exception_resolution_agent_mvp_plan.md`: Current 1.5-hour MVP implementation plan with best-practice canonical and per-subagent schemas.
- `plans/payment_exception_resolution_agent_future_production_plan.md`: Current future production implementation plan with versioned schemas, durable workflow, safety gates, idempotency, observability, and rollout strategy.
- `plans/payment_exception_orchestrator_mvp_30min_implementation_plan.md`: Focused 30-minute implementation plan for the orchestrator, including phases, adapter design, safety fallbacks, and smoke tests.
- `plans/payment_exception_subagent_handoff_contract.md`: Explicit input/output contract and integration checklist for teammates building the four subagents.
- `environment.yml`: Conda environment spec for Python 3.10 orchestrator work.
- `payment_exception_mvp/`: Python MVP implementation package for the orchestrator, CLI runner, deterministic classifier, scoped slicers, safety fallbacks, adapter layer, fixtures, and temporary subagent stubs.
- `tests/test_orchestrator_smoke.py`: Pytest smoke tests for the five MVP fixtures and safe subagent-unavailable fallback.

## Current state

- Documentation-only repository at the time this context was created.
- Application source code now exists under `payment_exception_mvp/`.
- A Python 3.10 conda environment named `payment-exception-orchestrator` has been created for orchestrator work. Recreate it with `conda env create -f environment.yml`.
- Run tests with `conda run -n payment-exception-orchestrator python -m pytest -q`.
- Run the CLI demo with `conda run -n payment-exception-orchestrator python -m payment_exception_mvp.app --fixture payment_exception_mvp/fixtures/beneficiary_invalid.json`.

## Working assumptions

- The current split planning deliverables use a canonical exception event at ingress and agent-specific scoped schemas for beneficiary, duplicate payment, compliance, and network agents.
- The planned MVP will use a simple mock API, an orchestrator, and four isolated subagents for: incorrect beneficiary, duplicate payment submission, compliance hold, and network or payment rail failure.
- The orchestrator should use deterministic classification, scoped subagent adapters, checkpointed responses, and safety fallbacks. Subagents are owned by teammates and should expose `analyze(agent_input: dict) -> dict` unless another adapter is agreed.
- Temporary subagent stubs are included only to keep the orchestrator demo runnable. Teammates can replace `payment_exception_mvp/agents/*_agent.py` as long as they preserve `analyze(agent_input: dict) -> dict` and the common output schema.
- Production design should prioritize payment safety, idempotency, auditability, bounded retries, durable checkpoints, isolated subagents, and conservative escalation over aggressive automation.
