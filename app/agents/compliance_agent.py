"""
Compliance Agent — RAG + LLM POWERED (AI COMPONENT)

This is the ONLY agent that uses AI. All other agents are rule-based.

Input schema (orchestrator slices to these fields only):
  payment_id, client_id, beneficiary_details, amount, currency,
  compliance_hold_status, payment_rail, exception_code

Architecture:
  Transaction
    → Deterministic pre-screening (sanctions_service — fast, no LLM cost)
    → Build context-aware query
    → Retrieve relevant compliance policy chunks (FAISS vector search)
    → LLM reasoning over retrieved context + transaction data
    → Structured MVP-compliant decision

MVP Actions (Section 8 of orchestrator plan):
  - ESCALATE_COMPLIANCE   → always for confirmed hits (never auto-resolve)
  - HOLD_AND_RECONCILE    → hold pending compliance review (ambiguous cases)
  - MANUAL_REVIEW         → LLM system failure fallback

CRITICAL:
  - automation_allowed is ALWAYS False for this agent.
  - Compliance issues are NEVER auto-resolved.
  - If LLM fails, always escalate — never silently pass.

Dependencies:
  pip install langchain langchain-openai openai faiss-cpu
"""

import os

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.rag.retriever import get_relevant_docs, format_docs_for_prompt
from app.services.sanctions_service import run_sanctions_screening
from app.utils.logger import get_logger
from app.utils.helper import now_iso

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# LLM Configuration
# ---------------------------------------------------------------------------
LLM_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = 0.0   # Zero = deterministic, reproducible output

# ---------------------------------------------------------------------------
# Prompt Template — instructs LLM to return MVP-compliant JSON
# ---------------------------------------------------------------------------
COMPLIANCE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a senior compliance officer AI at UBS, a major international bank.
Your role is to analyze payment transactions for compliance risks using the bank's policies.

You have access to excerpts from the bank's official compliance policy documents below.
Use ONLY the provided policy context and the transaction data to make your decision.
Do NOT invent regulations or policies not present in the context.

COMPLIANCE POLICY CONTEXT:
{policy_context}

CRITICAL RULES:
1. Never auto-resolve or auto-approve any compliance issue.
2. If there is ANY doubt, recommend HOLD_AND_RECONCILE — not PROCEED.
3. Confirmed sanctions hits ALWAYS require action=ESCALATE_COMPLIANCE.
4. compliance_hold_status != NONE ALWAYS requires ESCALATE_COMPLIANCE, confidence 0.99.
5. Exception code containing COMPLIANCE/SANCTIONS/AML/POLICY ALWAYS requires ESCALATE_COMPLIANCE.
6. automation_allowed MUST always be false.
7. Be specific — cite the policy section triggered in your explanation.

You MUST respond with valid JSON only. No markdown. No extra text.
The JSON must match this exact schema:
{{
  "classification": "string describing the compliance issue type",
  "issue_detected": true or false,
  "root_cause": "brief technical root cause",
  "action": "ESCALATE_COMPLIANCE or HOLD_AND_RECONCILE",
  "automation_allowed": false,
  "confidence": 0.0 to 1.0,
  "risk_level": "LOW or MEDIUM or HIGH or CRITICAL",
  "evidence": ["list", "of", "supporting", "signal", "strings"],
  "explanation": "human-readable explanation of the compliance decision",
  "next_steps": ["ordered", "list", "of", "recommended", "actions"]
}}"""
    ),
    (
        "human",
        """Analyze this payment transaction for compliance and sanctions risks:

TRANSACTION DETAILS:
- Payment ID: {payment_id}
- Client ID: {client_id}
- Payment Rail: {payment_rail}
- Amount: {currency} {amount}
- Beneficiary Name: {beneficiary_name}
- Beneficiary Country: {beneficiary_country}
- Beneficiary Bank (SWIFT): {beneficiary_swift}
- Exception Code: {exception_code}
- Compliance Hold Status: {compliance_hold_status}

DETERMINISTIC PRE-SCREENING RESULTS:
{pre_screening_summary}

Provide your compliance assessment as JSON."""
    ),
])

json_parser = JsonOutputParser()


def _build_pre_screening_summary(screening: dict) -> str:
    """Format deterministic pre-screening result for the LLM prompt."""
    if not screening["sanctions_hit"]:
        return "No sanctions hits detected in deterministic pre-screening."
    lines = [f"SANCTIONS FLAGS DETECTED ({screening['total_flags']} flag(s)):"]
    for hit in screening["hits"]:
        lines.append(f"  [{hit['check']}] {hit['detail']}")
    return "\n".join(lines)


def _build_query(transaction: dict) -> str:
    """Natural language query for FAISS vector retrieval."""
    beneficiary = transaction.get("beneficiary_details") or {}
    parts = [
        f"compliance rules for {transaction.get('payment_rail', '')} payment",
        f"beneficiary country {beneficiary.get('country', 'unknown')}",
        f"amount {transaction.get('currency', '')} {transaction.get('amount', 0)}",
    ]
    hold = transaction.get("compliance_hold_status", "NONE")
    if hold and hold != "NONE":
        parts.append(f"compliance hold status: {hold}")
    code = transaction.get("exception_code", "")
    if code:
        parts.append(f"exception: {code}")
    return " | ".join(parts)


def _fallback_response(payment_id: str, reason: str, num_docs: int = 0) -> dict:
    """
    Safe fallback when LLM call fails.
    Always escalates — never silently passes a transaction on error.
    """
    logger.error(f"[ComplianceAgent] LLM fallback for {payment_id}: {reason}")
    return {
        "agent_name": "ComplianceAgent",
        "classification": "system_error_escalation",
        "issue_detected": True,
        "root_cause": f"Compliance check could not complete due to system error: {reason}",
        "action": "ESCALATE_COMPLIANCE",
        "automation_allowed": False,
        "confidence": 0.50,
        "risk_level": "HIGH",
        "evidence": [
            f"llm_error: {reason}",
            "Defaulting to escalation as per fail-closed policy",
        ],
        "explanation": (
            "The AI compliance reasoning system encountered an error. "
            "Per fail-closed policy, the transaction is escalated for human review."
        ),
        "next_steps": [
            "Escalate immediately to the compliance team for manual review",
            "Do not process or release the payment until cleared by compliance",
            "Investigate the system error and retry once resolved",
        ],
        "escalation_required": True,
        "audit_notes": (
            f"Analyzed at {now_iso()} | Payment: {payment_id} | "
            f"LLM unavailable — fail-closed escalation. Error: {reason} | "
            f"Policy docs retrieved: {num_docs}"
        ),
    }


def analyze(transaction: dict) -> dict:
    """
    Analyze a transaction for compliance and sanctions risks using RAG + LLM.

    Flow:
      1. Deterministic pre-screening (fast, no LLM cost)
      2. Retrieve relevant compliance policy chunks via FAISS
      3. LLM reasoning over transaction + policy context
      4. Build MVP-compliant response, with pre-screening safety override

    Args:
        transaction: Agent-sliced dict (payment_id, client_id, beneficiary_details,
                     amount, currency, compliance_hold_status, payment_rail, exception_code)

    Returns:
        MVP-compliant agent response dict.
    """
    payment_id = transaction.get("payment_id", "UNKNOWN")
    beneficiary = transaction.get("beneficiary_details") or {}
    compliance_hold = (transaction.get("compliance_hold_status") or "NONE").upper()
    exception_code = (transaction.get("exception_code") or "").upper()

    logger.info(f"[ComplianceAgent] Analyzing transaction: {payment_id}")

    # ------------------------------------------------------------------
    # Step 1: Deterministic pre-screening
    # ------------------------------------------------------------------
    pre_screening = run_sanctions_screening(transaction)
    pre_summary = _build_pre_screening_summary(pre_screening)
    logger.info(
        f"[ComplianceAgent] Pre-screening: "
        f"sanctions_hit={pre_screening['sanctions_hit']}, "
        f"flags={pre_screening['total_flags']}"
    )

    # ------------------------------------------------------------------
    # Step 2: RAG retrieval
    # ------------------------------------------------------------------
    query = _build_query(transaction)
    docs = []
    try:
        docs = get_relevant_docs(query, k=4)
        policy_context = format_docs_for_prompt(docs)
    except Exception as e:
        logger.error(f"[ComplianceAgent] Vector store error: {e}")
        return _fallback_response(payment_id, f"Retrieval error: {e}", 0)

    # ------------------------------------------------------------------
    # Step 3: LLM reasoning
    # ------------------------------------------------------------------
    logger.info(f"[ComplianceAgent] Sending to LLM ({LLM_MODEL})...")
    llm_result = None
    try:
        llm = ChatOpenAI(model=LLM_MODEL, temperature=LLM_TEMPERATURE)
        chain = COMPLIANCE_PROMPT | llm | json_parser
        llm_result = chain.invoke({
            "policy_context": policy_context,
            "payment_id": payment_id,
            "client_id": transaction.get("client_id", ""),
            "payment_rail": transaction.get("payment_rail", ""),
            "currency": transaction.get("currency", ""),
            "amount": f"{transaction.get('amount', 0):,.2f}",
            "beneficiary_name": beneficiary.get("name", "Unknown"),
            "beneficiary_country": beneficiary.get("country", "Unknown"),
            "beneficiary_swift": beneficiary.get("swift_code", "N/A"),
            "exception_code": exception_code,
            "compliance_hold_status": compliance_hold,
            "pre_screening_summary": pre_summary,
        })
    except Exception as e:
        return _fallback_response(payment_id, str(e), len(docs))

    logger.info(
        f"[ComplianceAgent] LLM decision: "
        f"action={llm_result.get('action')}, "
        f"confidence={llm_result.get('confidence')}"
    )

    # ------------------------------------------------------------------
    # Step 4: Safety override — pre-screening always wins over LLM
    # Rule: compliance_hold != NONE → ESCALATE_COMPLIANCE (conf 0.99)
    # Rule: sanctions pre-screen hit → ESCALATE_COMPLIANCE
    # ------------------------------------------------------------------
    force_escalate = (
        pre_screening["sanctions_hit"]
        or compliance_hold not in ("NONE", "")
        or any(kw in exception_code for kw in ("SANCTION", "AML", "COMPLIANCE", "POLICY"))
    )

    if force_escalate and llm_result.get("action") != "ESCALATE_COMPLIANCE":
        logger.warning(
            f"[ComplianceAgent] {payment_id} — "
            "Overriding LLM action to ESCALATE_COMPLIANCE (pre-screen/hold rule)"
        )
        llm_result["action"] = "ESCALATE_COMPLIANCE"
        llm_result["issue_detected"] = True
        llm_result["risk_level"] = "CRITICAL"
        if compliance_hold not in ("NONE", ""):
            llm_result["confidence"] = 0.99
        llm_result["root_cause"] = (
            f"Pre-screening override: {pre_summary} | " + llm_result.get("root_cause", "")
        )

    # Ensure automation_allowed is ALWAYS False for compliance
    llm_result["automation_allowed"] = False

    # Append audit metadata
    audit_suffix = (
        f"\n\nPre-screening: {pre_summary}"
        f"\nPolicy chunks retrieved: {len(docs)}"
        f"\nLLM model: {LLM_MODEL}"
        f"\nAnalyzed at: {now_iso()}"
    )

    return {
        "agent_name": "ComplianceAgent",
        "classification": llm_result.get("classification", "compliance_risk_detected"),
        "issue_detected": bool(llm_result.get("issue_detected", True)),
        "root_cause": llm_result.get("root_cause", "Compliance risk identified"),
        "action": llm_result.get("action", "ESCALATE_COMPLIANCE"),
        "automation_allowed": False,
        "confidence": float(llm_result.get("confidence", 0.90)),
        "risk_level": llm_result.get("risk_level", "HIGH"),
        "evidence": llm_result.get("evidence", [pre_summary]),
        "explanation": llm_result.get("explanation", "Compliance risk requires human review."),
        "next_steps": llm_result.get("next_steps", [
            "Escalate immediately to the compliance team",
            "Hold the transaction — do not release without compliance clearance",
        ]),
        "escalation_required": True,   # Always True for compliance agent
        "audit_notes": llm_result.get("audit_notes", "") + audit_suffix,
    }
