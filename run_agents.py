"""
Quick integration test — runs all 4 agents against the sample transactions.

Usage (from project root):
    python run_agents.py

This does NOT require FastAPI or an orchestrator. It's a standalone demo
script that your teammate can use to verify each agent works correctly.

For the Compliance Agent, set OPENAI_API_KEY in your environment or .env file.
The other 3 agents work with zero API keys.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# --- Import all agents ---
from app.agents.beneficiary_agent import analyze as beneficiary_analyze
from app.agents.duplicate_payment_agent import analyze as duplicate_analyze
from app.agents.compliance_agent import analyze as compliance_analyze
from app.agents.network_failure_agent import analyze as network_analyze

# ---------------------------------------------------------------------------
# Load sample transactions
# ---------------------------------------------------------------------------
SAMPLE_FILE = Path(__file__).parent / "app" / "data" / "sample_transactions.json"


def load_samples():
    with open(SAMPLE_FILE, encoding="utf-8") as f:
        return json.load(f)


def print_result(result: dict):
    """Pretty-print a single agent result."""
    status_icon = "🔴" if result["issue_detected"] else "✅"
    escalation_icon = "⚠️ " if result.get("escalation_required") else "  "
    print(f"\n  {status_icon} Agent        : {result['agent_name']}")
    print(f"     Issue        : {result['issue_detected']}")
    print(f"     Root Cause   : {result['root_cause']}")
    print(f"     Confidence   : {result['confidence']:.0%}")
    print(f"     Action       : {result['action']}")
    print(f"  {escalation_icon} Escalation  : {result.get('escalation_required', False)}")
    print(f"     Audit Notes  : {result.get('audit_notes', '')[:120]}…")


# ---------------------------------------------------------------------------
# Routing map — exception_code → agent
# ---------------------------------------------------------------------------
AGENT_ROUTING = {
    "INVALID_BENEFICIARY": ("BeneficiaryDetailsAgent", beneficiary_analyze),
    "DUPLICATE_PAYMENT":   ("DuplicatePaymentAgent",   duplicate_analyze),
    "SANCTION_HIT":        ("ComplianceAgent",         compliance_analyze),
    "AML_HOLD":            ("ComplianceAgent",         compliance_analyze),
    "NETWORK_TIMEOUT":     ("NetworkFailureAgent",      network_analyze),
}


def run_demo():
    transactions = load_samples()
    print("\n" + "=" * 70)
    print("  UBS PAYMENT EXCEPTION RESOLUTION — AGENT LAYER DEMO")
    print("=" * 70)

    for tx in transactions:
        pid = tx["payment_id"]
        code = tx["exception_code"]

        print(f"\n{'─' * 70}")
        print(f"  Payment: {pid}  |  Exception: {code}  |  Rail: {tx['payment_rail']}")
        print(f"  Amount : {tx['currency']} {tx['amount']:,.2f}  |  Status: {tx['current_transaction_status']}")
        print(f"  Beneficiary: {tx['beneficiary_details'].get('name', 'N/A')} "
              f"({tx['beneficiary_details'].get('country', 'N/A')})")

        if code not in AGENT_ROUTING:
            print(f"  ⚪ No agent mapped for exception code: {code}")
            continue

        agent_name, agent_fn = AGENT_ROUTING[code]

        # Skip compliance agent if no API key is set (demo fallback)
        if agent_name == "ComplianceAgent" and not os.getenv("OPENAI_API_KEY"):
            print("\n  ⚡ ComplianceAgent skipped — set OPENAI_API_KEY to enable LLM reasoning")
            print("     (Pre-screening still runs — compliance_service is deterministic)")
            # Still run pre-screening to show the deterministic layer
            from app.services.sanctions_service import run_sanctions_screening
            pre = run_sanctions_screening(tx)
            if pre["sanctions_hit"]:
                for hit in pre["hits"]:
                    print(f"     🚨 Pre-screen: [{hit['check']}] {hit['detail']}")
            continue

        try:
            result = agent_fn(tx)
            print_result(result)
        except Exception as e:
            print(f"\n  ❌ Agent error: {e}")

    print(f"\n{'=' * 70}")
    print("  DEMO COMPLETE")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_demo()
