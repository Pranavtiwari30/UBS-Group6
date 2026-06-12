# Payment Exception Resolution Agents

The platform separates diagnosis from authority. Agents are investigation specialists that receive a versioned envelope with scoped context, policy, permissions, and redaction profiles. **Agents are read-only**—they produce structured recommendations but do not own money movement.

## Core Contract
All agents receive an envelope containing:
- `trace_id`, `case_id`, `payment_id`, and `evidence_snapshot_id`
- Scoped `context` containing only the evidence they need to see
- `policy` providing thresholds and automation mode
- `permissions` to enforce their read-only boundaries

Agents must return a standard response including `classification`, `action`, `confidence`, `reason_codes`, `evidence_facts`, `explanation`, and `next_steps`.

## 1. Beneficiary Agent
- **Purpose**: Diagnose invalid account, UPI, routing, IFSC, or beneficiary mismatch.
- **Inputs**: Beneficiary validation, masked details, payment summary, client history.
- **Allowed Recommendations**: Request client correction, deterministic repair candidate, manual review.
- **Must Defer**: Any repair without deterministic validation and client/policy approval.

## 2. Duplicate Payment Agent
- **Purpose**: Detect duplicate instructions across channels and retries.
- **Inputs**: Payment intent, duplicate trace, client references, beneficiary fingerprint, amount.
- **Allowed Recommendations**: Cancel current duplicate, hold duplicate, manual review.
- **Must Defer**: Cancellation when current payment finality or cancellability is ambiguous.

## 3. Compliance Triage Agent
- **Purpose**: Summarize compliance status and route restricted cases.
- **Inputs**: Redacted compliance status, hold type, allowed queue metadata.
- **Allowed Recommendations**: Escalate compliance, hold, block client disclosure.
- **Must Defer**: Compliance release, detailed sanctions explanation to general ops or client.

## 4. Network and Rail Agent
- **Purpose**: Diagnose rail outage, ACK gaps, uncertain finality, settlement windows.
- **Inputs**: Network logs, rail status, ACKs, ledger state, retry history.
- **Allowed Recommendations**: Hold and reconcile, safe retry candidate, incident route.
- **Must Defer**: Retry if finality, funds movement, or prior retry outcome is unknown.

## Final Decision Authority & Safety Gate
While agents provide recommendations, the **Deterministic Decision Engine** and the **Safety Gate** have the final say. An LLM Reviewer (running on `gpt-5.4`) may also inspect the case to re-route between specialists or tighten the risk assessment, but it can never bypass the hard safety rules (e.g., releasing a compliance hold or executing a retry without known finality).
