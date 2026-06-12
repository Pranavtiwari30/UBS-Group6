# Payment Exception Resolution Agent

## Table of Contents

| Attribute | Detail |
|---|---|
| Track | Agentic AI / AI Engineering |
| Expected Deliverable | Architecture brief, agent catalogue, decision and orchestration workflow, sample end-to-end traces, threshold and escalation notes |
| Format | Working prototype or pseudo code |

## 2. Problem Title

**Payment Exception Resolution Agent — A Production-Grade Agentic System for Diagnosing, Routing, and Resolving Failed Payment Transactions**

## 3. One-Line Summary

Design a production-grade system that detects payment exceptions, diagnoses likely root causes using internal and external evidence, determines whether the issue can be resolved automatically or requires escalation, and advances the case through safe remediation with full auditability.

## 4. Business Scenario

Banks and payment processors handle large daily volumes of outbound and inbound payment transactions across rails such as domestic transfers, wire payments, internal book transfers, and scheduled disbursements. A meaningful share of these transactions enter exception states because of incorrect beneficiary details, insufficient funds, duplicate submissions, network or clearing failures, sanctions or compliance holds, cut-off timing issues, or downstream system unavailability.

Operations teams typically investigate these failures manually by examining payment status systems, account data, routing information, compliance queues, network acknowledgements, prior retry attempts, and customer contact history. They then decide whether the transaction should be retried, repaired, held, cancelled, escalated, or communicated back to the client. This is expensive, slow, and difficult to scale as payment volumes and exception diversity grow.

The production environment is constrained by multiple dependent systems with their own latency and failure behavior, differing payment-rail rules, strict correctness and audit requirements, and asymmetric error costs. A missed resolvable exception delays funds availability and harms customer experience, while an unsafe automated correction or retry can create duplicate payments, compliance breaches, or incorrect fund movement. The system must therefore diagnose carefully, act conservatively under uncertainty, and maintain a clear record of every recommendation and automated action.

Cases for reference:

- **Incorrect beneficiary details:** Payment fails due to wrong account/UPI/IFSC, requiring either auto-validation correction or customer re-input.
- **Insufficient funds:** Transaction fails at debit due to low balance, requiring balance check and safe retry or client notification.
- **Duplicate payment submission:** Same payment triggered twice, needing duplicate detection and safe cancellation to avoid double debit.
- **Compliance / sanctions hold:** Payment is blocked by AML or sanctions screening and must be escalated for manual compliance review.
- **Network / payment rail failure:** Transaction status is uncertain due to system or clearing network outage, requiring reconciliation before retry.
- **Cut-off time miss:** Payment submitted after rail timing window and must be re-queued for next processing cycle.
- **Uncertain retry outcome:** Prior retries failed or have unknown status, requiring investigation to avoid duplicate execution before further action.

The above cases are for your reference, you are free to choose any suitable cases to build your solution.

## 5. Why the Problem is Non-Trivial

Participants must reason through several tensions that do not have simple answers:

- A failed payment may reflect one root cause, multiple interacting causes, or inconsistent status across systems.
- Some exceptions can be resolved automatically, while others require client input, operations review, compliance release, or downstream network recovery.
- Retrying a failed transaction can improve completion rates but also increases the risk of duplicate execution if state is stale or ambiguous.
- Diagnosis depends on data spread across transaction systems, account ledgers, compliance platforms, routing directories, and message logs that may be incomplete or temporarily unavailable.
- Different payment rails and exception types impose different timing, repairability, and escalation constraints.
- Multi-agent designs introduce coordination, determinism, bounded retries, and failure-isolation concerns that must be explicitly justified.
- The system output must remain auditable and replayable because exception decisions may later be reviewed for operational, customer, or regulatory reasons.

## 6. The Problem Statement

Design and describe a production-grade Payment Exception Resolution Agent that handles failed or held payment transactions end to end.

For each payment exception, the system must determine the likely cause, identify what additional evidence is needed, decide whether the issue can be resolved automatically or requires internal or external follow-up, and define the resulting operational action with justification.

The submission must show how the system ingests payment exceptions, investigates status and root cause, reaches a decision, triggers downstream actions, records an audit trail, and handles duplicate events, partial information, stale state, and dependency failure.

A single-agent design is allowed only if justified. Otherwise, the submission must define a multi-agent system with explicit roles, contracts, orchestration logic, and communication boundaries.

## 7. End-to-End Flow the Submission Must Cover

The submission must define, as requirements, the complete end-to-end flow covering:

1. **Ingress** — How failed transactions, exception events, or manual case triggers enter the system and are validated, normalised, and deduplicated.
2. **Orchestration** — How work is assigned, sequenced, parallelised, and budgeted across diagnosis and remediation.
3. **Investigation** — How the system gathers transaction context, checks payment-state evidence, identifies likely root causes, and assesses whether automated correction is safe.
4. **Decision** — How the system determines the next resolution action and records its basis.
5. **Egress** — How the decision and any required outputs are delivered to transaction systems, case queues, or communication channels.
6. **Async post-decision** — How follow-on work such as retries, notifications, case updates, monitoring, and audit persistence is handled after the primary decision path.
7. **Replay and feedback** — How prior exception decisions are replayed when new status events arrive, retries complete, or human reviewers override prior outcomes.

## 8. Inputs the System Receives

At minimum, assume the system receives schema-level inputs such as:

- `payment_id`
- `client_id`
- `account_id`
- `payment_rail`
- `payment_type`
- `amount`
- `currency`
- `beneficiary_details`
- `submitted_timestamp`
- `exception_event_type`
- `exception_code`
- `current_transaction_status`
- `prior_retry_events[]`
- `compliance_hold_status`
- `network_acknowledgements[]`
- `client_contact_history[]`

## 9. Tools and Data Sources Available

The system may use any of the following, each with its own latency profile and independent failure modes:

- Payment orchestration or transaction status system
- Core account and balance systems
- Routing and beneficiary validation services
- Payment network or clearing acknowledgements and message logs
- Compliance and sanctions review systems
- Duplicate-detection or payment trace repositories
- Case-management and operations workflow systems
- Client communication channels and template services
- Retry or repair execution services
- Audit, monitoring, and observability systems

## 10. Multi-Agent Design Requirements

The submission must define the following as explicit requirements:

- **Topology** — A clear topology of agents and components involved in diagnosis, evidence gathering, resolution, communication, and follow-up.
- **Per-agent contracts** — For each agent, its purpose, inputs, outputs, authority, side effects, and what it must defer.
- **Communication model** — The message or state schema passed between agents and external tools.
- **Orchestration model** — The control strategy governing routing, retries, branching, and completion.
- **Concurrency** — Which investigations may run in parallel and how partial evidence is merged.
- **Loop and depth control** — Bounded retries, bounded resolution loops, explicit re-check limits, and termination rules.
- **Budget sharing** — How synchronous diagnosis time and asynchronous remediation budgets are allocated.
- **Failure isolation** — How a failing dependency, unresolved ambiguity, or malformed agent output affects the overall resolution path.
- **Determinism** — How the same input and same evidence set produce the same recorded resolution outcome.

## 11. Production-Grade Requirements

The design must address all of the following:

- **Latency** — A stated budget for primary exception diagnosis and how it is enforced.
- **Reliability** — Safe behavior when transaction systems, compliance systems, network logs, or communication services fail or return partial data.
- **Idempotency** — Duplicate exception triggers, repeated retries, and repeated side effects must not create duplicate corrections, duplicate payments, or divergent case states.
- **Configurability** — Resolution rules, retry policies, routing rules, rail-specific controls, and ownership mappings must be configuration-driven.
- **Observability** — Structured logs, metrics, traces, queue visibility, and alertable operating signals.
- **Auditability** — A replayable record of the payment state, evidence used, agents invoked, recommended or executed actions, and downstream side effects.
- **Explainability** — Human-readable justification for why a payment was retried, repaired, held, cancelled, escalated, or communicated back to the client.
- **Safety controls** — Kill switches, auto-retry pause controls, degraded modes, and the ability to narrow automation scope safely.
- **Deployability** — Safe rollout and staged activation suitable for payment operations.
- **Security and privacy** — Handling of payment details, account information, client communications, and access controls.
- **Feedback loop** — How retry outcomes, operator overrides, client responses, and later payment status events alter future behavior.

## 12. Functional Behaviors the Solution Must Address

The solution must explicitly handle the following:

- A payment exception that can be resolved automatically with no client involvement.
- A payment exception that requires client outreach before further action can be taken.
- A payment exception caused by conflicting evidence across transaction, network, or account systems.
- A payment on compliance hold that cannot be auto-resolved.
- A payment with prior failed retries and uncertain current execution status.
- A payment affected by network or downstream system outages.
- A duplicate trigger or replayed exception event against the same payment case.
- A case that requires escalation to operations, compliance, or another internal queue.
- A case where the safe action is to defer or hold rather than retry or cancel.
- A case that is re-opened because later status events change the original conclusion.

## 13. Out of Scope

Participants are not expected to:

- Build production integrations to real payment rails, clearing networks, or messaging providers.
- Implement a complete payment engine or ledger.
- Build a customer-facing portal or operations UI.
- Build a full sanctions or compliance screening system.
- Solve every payment-rail-specific format rule in full operational detail.

## 14. Expected Deliverables

Each submission must include:

1. **Architecture** — A clear end-to-end architecture covering ingress, orchestration, investigation, decision, egress, asynchronous follow-up, and replay or feedback.
2. **Agent catalogue** — The agent set or justified single-agent structure, including each agent's purpose, contract, authority, and dependencies.
3. **Working prototype or pseudo code**
4. **Decision and orchestration workflow** — A structured description of how the system proceeds from exception trigger to resolution outcome.
5. **Sample end-to-end traces** — Representative walkthroughs showing how different payment exceptions move through the system.
6. **Threshold and escalation notes** — The decision thresholds, routing boundaries, and escalation rules used by the design.
7. **Production readiness plan** — Reliability, observability, idempotency, deployment safety, security, and fallback design.
8. **Assumptions and trade-offs** — Explicit assumptions, implications, and rationale.

Optional bonus:

- A runnable mock implementation with stubbed status, compliance, and retry dependencies.
- A replay or monitoring harness showing how exception outcomes are revisited as new status events arrive.
