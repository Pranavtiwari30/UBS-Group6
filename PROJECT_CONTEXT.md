# Project Context

## Repository purpose

This repository currently contains planning material for a Payment Exception Resolution Agent, an agentic AI system for diagnosing and routing failed or held payment transactions.

## Important paths

- `plans/payment_exception_resolution_agent_problem_statement.md`: Source problem statement and expected deliverables.
- `plans/payment_exception_resolution_agent_mvp_plan.md`: Current 1.5-hour MVP implementation plan with best-practice canonical and per-subagent schemas.
- `plans/payment_exception_resolution_agent_future_production_plan.md`: Current future production implementation plan with versioned schemas, durable workflow, safety gates, idempotency, observability, and rollout strategy.

## Current state

- Documentation-only repository at the time this context was created.
- No application source code, package manager files, test runner, or build commands are present yet.

## Working assumptions

- The current split planning deliverables use a canonical exception event at ingress and agent-specific scoped schemas for beneficiary, duplicate payment, compliance, and network agents.
- The planned MVP will use a simple mock API, an orchestrator, and four isolated subagents for: incorrect beneficiary, duplicate payment submission, compliance hold, and network or payment rail failure.
- Production design should prioritize payment safety, idempotency, auditability, bounded retries, durable checkpoints, isolated subagents, and conservative escalation over aggressive automation.
