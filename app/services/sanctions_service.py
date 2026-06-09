"""
Sanctions Service — deterministic sanctions and AML screening.

Uses in-memory mock data for the hackathon demo.
In production this would call an external sanctions API (e.g., Refinitiv World-Check).

Checks:
  - Sanctioned entity name match
  - Sanctioned country / jurisdiction
  - High-risk amount thresholds
  - Known suspicious client IDs
"""

from typing import Tuple
from app.utils.logger import get_logger
from app.utils.helper import normalize_string

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Mock sanctions data — replace with real API calls in production
# ---------------------------------------------------------------------------

# OFAC / UN sanctioned country codes (ISO-3166 alpha-2 / alpha-3)
SANCTIONED_COUNTRIES = {
    "IR", "IRN",   # Iran
    "KP", "PRK",   # North Korea
    "SY", "SYR",   # Syria
    "CU", "CUB",   # Cuba
    "VE", "VEN",   # Venezuela (partial)
    "RU", "RUS",   # Russia (SDN list entities)
    "BY", "BLR",   # Belarus
    "MM", "MMR",   # Myanmar
    "SD", "SDN",   # Sudan
}

# Partial name match list — SDN / HM Treasury consolidated list
SANCTIONED_ENTITY_NAMES = {
    "TEHRAN BANK",
    "PYONGYANG FINANCIAL",
    "RUSSIAN DEFENSE MINISTRY",
    "WAGNER GROUP",
    "LAZARUS GROUP",
    "IRAN CENTRAL BANK",
    "HEZBOLLAH FINANCIAL UNIT",
    "AL QAEDA FOUNDATION",
    "HAMAS INVESTMENT FUND",
    "BURMESE MILITARY BANK",
}

# Clients flagged internally for AML investigation
SUSPICIOUS_CLIENT_IDS = {
    "CLT-9999",
    "CLT-8888",
    "CLT-0013",
}

# Amounts above this (in USD equivalent) trigger enhanced due diligence
HIGH_VALUE_THRESHOLD_USD = 10_000.0

# Amounts above this are auto-flagged as potentially structuring-related
STRUCTURING_THRESHOLD_USD = 9_000.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_sanctioned_country(country: str) -> Tuple[bool, str]:
    """Return (is_sanctioned, reason)."""
    if not country:
        return False, ""
    code = normalize_string(country)
    if code in SANCTIONED_COUNTRIES:
        return True, f"Beneficiary country '{country}' is on the sanctions list"
    return False, ""


def check_sanctioned_entity(name: str) -> Tuple[bool, str]:
    """Partial match against sanctioned entity names (case-insensitive)."""
    if not name:
        return False, ""
    name_upper = name.strip().upper()
    for entity in SANCTIONED_ENTITY_NAMES:
        if entity in name_upper or name_upper in entity:
            return True, f"Beneficiary name '{name}' matches sanctioned entity '{entity}'"
    return False, ""


def check_suspicious_client(client_id: str) -> Tuple[bool, str]:
    """Flag clients already under AML review."""
    if not client_id:
        return False, ""
    if normalize_string(client_id) in {normalize_string(c) for c in SUSPICIOUS_CLIENT_IDS}:
        return True, f"Client '{client_id}' is flagged for AML investigation"
    return False, ""


def check_high_value(amount: float, currency: str) -> Tuple[bool, str]:
    """
    Flag transactions near or above regulatory reporting thresholds.
    For the demo, we treat all amounts as USD-equivalent.
    """
    if amount >= HIGH_VALUE_THRESHOLD_USD:
        return True, (
            f"Transaction amount {currency} {amount:,.2f} exceeds the "
            f"high-value threshold of USD {HIGH_VALUE_THRESHOLD_USD:,.2f} — "
            "enhanced due diligence required"
        )
    if STRUCTURING_THRESHOLD_USD <= amount < HIGH_VALUE_THRESHOLD_USD:
        return True, (
            f"Transaction amount {currency} {amount:,.2f} is near the reporting "
            "threshold — possible structuring activity"
        )
    return False, ""


def run_sanctions_screening(transaction: dict) -> dict:
    """
    Run all deterministic sanctions checks.
    Returns a summary dict consumed by the Compliance Agent.
    """
    beneficiary = transaction.get("beneficiary_details", {})
    hits = []

    # Country check
    country = beneficiary.get("country", "")
    flagged, reason = check_sanctioned_country(country)
    if flagged:
        hits.append({"check": "SANCTIONED_COUNTRY", "detail": reason})
        logger.warning(f"[{transaction.get('payment_id')}] {reason}")

    # Entity name check
    name = beneficiary.get("name", "")
    flagged, reason = check_sanctioned_entity(name)
    if flagged:
        hits.append({"check": "SANCTIONED_ENTITY", "detail": reason})
        logger.warning(f"[{transaction.get('payment_id')}] {reason}")

    # Client AML flag
    flagged, reason = check_suspicious_client(transaction.get("client_id", ""))
    if flagged:
        hits.append({"check": "AML_CLIENT_FLAG", "detail": reason})
        logger.warning(f"[{transaction.get('payment_id')}] {reason}")

    # High-value / structuring check
    flagged, reason = check_high_value(
        transaction.get("amount", 0),
        transaction.get("currency", "USD"),
    )
    if flagged:
        hits.append({"check": "HIGH_VALUE", "detail": reason})
        logger.info(f"[{transaction.get('payment_id')}] {reason}")

    return {
        "sanctions_hit": len(hits) > 0,
        "hits": hits,
        "total_flags": len(hits),
    }
