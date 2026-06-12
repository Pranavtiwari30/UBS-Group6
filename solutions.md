# Payment Exception Resolution Solution

## Overview
The Payment Exception Resolution Orchestrator is a recommendation-only system designed for diagnosing and routing failed or held payment transactions. It is built as a conservative payment operations control plane rather than an autonomous payment actor. The system optimizes for safe resolution under uncertainty, not maximum automation.

## Core Principles
1. **Automate Investigation First**: Collect evidence, classify root cause, summarize, route, and recommend.
2. **Automate Safe Non-Financial Work Next**: Case creation, queue routing, holds, deferrals, compliance escalation, and approved template-based outreach.
3. **Automate Financial Actions Only in Narrow Cohorts**: Retry, repair, or duplicate cancellation require deterministic policy approval, rail-specific finality, payment-intent locking, pre-action revalidation, and full audit.
4. **Never Automate Compliance Release**: Compliance release remains in the authoritative compliance platform with appropriate controls. The system fails closed for compliance.
5. **No Retry Under Uncertainty**: Unknown funds movement, unknown finality, conflicting evidence, or uncertain prior retry status blocks retry.
6. **Decisioning is Deterministic**: The same event, evidence snapshot, policy version, and agent outputs produce the same final decision.

## End-to-End Architecture
The architecture uses an **event-sourced payment exception workflow** combined with a deterministic policy/safety core and scoped read-only diagnostic agents.

### Components
1. **Validation & Normalization Gateway**: Validates incoming events, canonicalizes them, and assigns trace IDs.
2. **Payment Intent Ledger & Idempotency Service**: Prevents duplicate actions across channels. Represents the canonical identity for the business intent.
3. **Event-Sourced Case Ledger**: Append-only case events and current case projection. Source of truth for case state, audit, replay, and operator concurrency.
4. **Evidence Aggregator & Snapshot Store**: Collects source facts (ledger, balance, compliance, network) in parallel and creates immutable, hashed evidence snapshots. Agents never fetch arbitrary source data.
5. **Policy Control Plane**: Trusted policy, thresholds, rollout cohorts, freshness budgets, and kill switches.
6. **Agent Router & Diagnostic Agents**: Agents receive scoped read-only slices of evidence and produce structured recommendations.
7. **Deterministic Decision Engine**: Merges evidence, policy, and agent outputs into a final decision based on a configured hierarchy (e.g., Compliance > Ledger > Finality > Duplicate Trace).
8. **Safety Gate**: Applies hard rules (e.g., force hold on compliance signal) and overrides any unsafe agent recommendations.
9. **Idempotent Action Executor**: Performs approved actions (non-financial/financial) and tracks attempts through their lifecycle, including pre-action revalidation immediately prior to side effects.

## Latency and Scale
The system relies on latency budgets rather than indefinite waiting:
- **Primary synchronous diagnosis**: Returns within a defined SLO (e.g., 2s) or transitions to asynchronous investigation.
- Parallel evidence collection with freshness budgets. Slower sources can arrive later and trigger replay.
- Agents run with strict latency boundaries (e.g., 500ms synchronous budget) and their failure results in safe fallbacks.

## Multi-user Operations and Replay
Human review is treated as a success path. The Ops and Compliance Workbench supports:
- Case leases and optimistic concurrency.
- Maker-checker controls for high-value actions.
- Separation of duties between ops, compliance, risk approvers, and engineering.
- Replay Engine: Reopens cases when new evidence, status outcomes, or human overrides arrive, without overwriting prior decisions.
