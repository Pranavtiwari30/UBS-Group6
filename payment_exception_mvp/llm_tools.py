from __future__ import annotations

from typing import Any, Callable

from payment_exception_mvp.schemas import ACCEPTED_ACTIONS, CanonicalPaymentException


# Agents the LLM is allowed to re-route to via invoke_subagent.
ROUTABLE_AGENTS = ("BeneficiaryAgent", "DuplicatePaymentAgent", "ComplianceAgent", "NetworkAgent")

RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


class LLMToolbox:
    """Dispatches read-only canonical-event lookups and subagent re-routing for the LLM.

    Information is intentionally limited to what arrived on the canonical event from the
    API. There are no external system calls. ``invoke_subagent`` is the one tool with a
    side effect inside the pipeline: it re-runs a different subagent and records that the
    model chose to re-route.
    """

    def __init__(
        self,
        event: CanonicalPaymentException,
        subagent_runner: Callable[[str], dict[str, Any]],
    ) -> None:
        self._event = event
        self._run_subagent = subagent_runner
        self.invoked_agents: list[str] = []

    # --- read-only accessors -------------------------------------------------

    def get_payment_summary(self) -> dict[str, Any]:
        p = self._event.payment
        return {
            "payment_id": p.payment_id,
            "amount": p.amount,
            "currency": p.currency,
            "payment_rail": p.payment_rail,
            "payment_type": p.payment_type,
            "current_transaction_status": p.current_transaction_status,
        }

    def get_status_evidence(self) -> dict[str, Any]:
        s = self._event.status_evidence
        return {
            "funds_movement_status": s.funds_movement_status,
            "ledger_debit_status": s.ledger_debit_status,
            "network_finality": s.network_finality,
        }

    def get_duplicate_evidence(self) -> dict[str, Any]:
        d = self._event.duplicate_evidence
        return {
            "duplicate_candidates": d.duplicate_candidates,
            "payment_fingerprint": d.payment_fingerprint,
        }

    def get_beneficiary_validation(self) -> dict[str, Any]:
        b = self._event.beneficiary_validation
        return {
            "validation_status": b.validation_status,
            "failed_fields": b.failed_fields,
            "suggested_correction": b.suggested_correction,
            "validation_confidence": b.validation_confidence,
        }

    def get_compliance_flags(self) -> dict[str, Any]:
        c = self._event.compliance
        return {
            "compliance_hold_status": c.compliance_hold_status,
            "screening_result": c.screening_result,
            "screening_reference": c.screening_reference,
            "risk_flags": c.risk_flags,
        }

    def get_policy_thresholds(self) -> dict[str, Any]:
        return self._event.policy.model_dump()

    def get_history(self) -> dict[str, Any]:
        h = self._event.history
        return {
            "prior_retry_events": h.prior_retry_events,
            "client_contact_history": h.client_contact_history,
        }

    def get_exception(self) -> dict[str, Any]:
        e = self._event.exception
        return {
            "exception_code": e.exception_code,
            "exception_type_hint": e.exception_type_hint,
            "description": e.description,
            "severity": e.severity,
        }

    def invoke_subagent(self, agent_name: str) -> dict[str, Any]:
        if agent_name not in ROUTABLE_AGENTS:
            return {"error": f"unknown agent '{agent_name}'", "routable_agents": list(ROUTABLE_AGENTS)}
        result = self._run_subagent(agent_name)
        self.invoked_agents.append(agent_name)
        return result

    # --- dispatch ------------------------------------------------------------

    def dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "invoke_subagent":
            return self.invoke_subagent(str(arguments.get("agent_name", "")))
        handler = getattr(self, name, None)
        if handler is None or name.startswith("_") or name not in _READ_ONLY_TOOL_NAMES:
            return {"error": f"unknown tool '{name}'"}
        return handler()


_READ_ONLY_TOOL_NAMES = {
    "get_payment_summary",
    "get_status_evidence",
    "get_duplicate_evidence",
    "get_beneficiary_validation",
    "get_compliance_flags",
    "get_policy_thresholds",
    "get_history",
    "get_exception",
}


def _read_only_tool(name: str, description: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    }


def tool_schemas() -> list[dict[str, Any]]:
    """OpenAI tool (function) schemas for the final-decision stage."""
    schemas = [
        _read_only_tool("get_payment_summary", "Payment id, amount, currency, rail, type, and current transaction status."),
        _read_only_tool("get_status_evidence", "Funds movement, ledger debit, and network finality status."),
        _read_only_tool("get_duplicate_evidence", "Duplicate candidate payments and the payment fingerprint."),
        _read_only_tool("get_beneficiary_validation", "Beneficiary validation status, failed fields, suggested correction, and confidence."),
        _read_only_tool("get_compliance_flags", "Compliance hold status, screening result, screening reference, and risk flags."),
        _read_only_tool("get_policy_thresholds", "Policy thresholds: manual review, safe retry, duplicate cancel, beneficiary repair."),
        _read_only_tool("get_history", "Prior retry events and client contact history for this payment."),
        _read_only_tool("get_exception", "Raw exception code, type hint, description, and severity."),
        {
            "type": "function",
            "function": {
                "name": "invoke_subagent",
                "description": (
                    "Re-route: run a different specialist subagent than the rule-based classifier chose "
                    "and get its analysis. Use when the evidence points to a different exception type."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {"type": "string", "enum": list(ROUTABLE_AGENTS)},
                    },
                    "required": ["agent_name"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_decision",
                "description": (
                    "Submit the final decision. Call exactly once when analysis is complete. "
                    "You cannot enable automation, release a compliance hold, or downgrade a compliance "
                    "escalation; the orchestrator re-applies hard safety limits after you decide."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": sorted(ACCEPTED_ACTIONS)},
                        "classification": {"type": "string"},
                        "selected_agent": {
                            "type": "string",
                            "description": "Agent whose analysis you are endorsing, or ManualReviewFallback.",
                        },
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "risk_level": {"type": "string", "enum": list(RISK_LEVELS)},
                        "reason_codes": {"type": "array", "items": {"type": "string"}},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                        "explanation": {"type": "string"},
                        "next_steps": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "action",
                        "classification",
                        "selected_agent",
                        "confidence",
                        "risk_level",
                        "reason_codes",
                        "explanation",
                        "next_steps",
                    ],
                    "additionalProperties": False,
                },
            },
        },
    ]
    return schemas
