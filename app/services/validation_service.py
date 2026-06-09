"""
Validation Service — rule-based checks for beneficiary details.

Covers:
  - IFSC code format (handles both 'ifsc' and 'ifsc_code' field names)
  - UPI ID format
  - Account number basic sanity
  - Required field presence
  - SWIFT/BIC format

All rules are deterministic — no AI involved here.
"""

import re
from typing import Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# IFSC: 4 uppercase letters (bank code) + '0' + 6 alphanumeric chars
IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

# UPI: localpart@provider  (e.g. john@okicici, 9876543210@upi)
UPI_PATTERN = re.compile(r"^[\w.\-+]+@[a-zA-Z]{2,}$")

# Account number: 9–18 digits (covers most Indian banks)
ACCOUNT_NUMBER_PATTERN = re.compile(r"^\d{9,18}$")

# SWIFT/BIC: 8 or 11 alphanumeric characters
SWIFT_PATTERN = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")


# ---------------------------------------------------------------------------
# Field-name normalization
# ---------------------------------------------------------------------------

def _get_ifsc(beneficiary: dict) -> str:
    """
    Accept both 'ifsc' (MVP canonical payload) and 'ifsc_code' (our internal model).
    Returns whichever is present, or empty string.
    """
    return beneficiary.get("ifsc") or beneficiary.get("ifsc_code") or ""


# ---------------------------------------------------------------------------
# Public validation helpers
# ---------------------------------------------------------------------------

def validate_ifsc(ifsc: str) -> Tuple[bool, str]:
    """Returns (is_valid, reason)."""
    if not ifsc:
        return False, "IFSC code is missing"
    ifsc = ifsc.strip().upper()
    if IFSC_PATTERN.match(ifsc):
        return True, "IFSC code is valid"
    return False, f"IFSC code '{ifsc}' does not match expected format (e.g. HDFC0001234)"


def validate_upi(upi_id: str) -> Tuple[bool, str]:
    if not upi_id:
        return False, "UPI ID is missing"
    upi_id = upi_id.strip()
    if UPI_PATTERN.match(upi_id):
        return True, "UPI ID is valid"
    return False, f"UPI ID '{upi_id}' does not match expected format (e.g. name@bankcode)"


def validate_account_number(account_number: str) -> Tuple[bool, str]:
    if not account_number:
        return False, "Account number is missing"
    account_number = account_number.strip().replace(" ", "")
    if ACCOUNT_NUMBER_PATTERN.match(account_number):
        return True, "Account number format is valid"
    return False, f"Account number '{account_number}' must be 9-18 digits"


def validate_swift(swift: str) -> Tuple[bool, str]:
    if not swift:
        return False, "SWIFT/BIC code is missing"
    swift = swift.strip().upper()
    if SWIFT_PATTERN.match(swift):
        return True, "SWIFT/BIC code is valid"
    return False, f"SWIFT/BIC code '{swift}' does not match expected format"


def validate_beneficiary_fields(
    beneficiary: dict, payment_rail: str
) -> Tuple[bool, list]:
    """
    Validate beneficiary fields based on the payment rail.
    Handles both 'ifsc' and 'ifsc_code' field names for compatibility
    with the orchestrator's canonical MVP payload schema.

    Returns:
        (all_valid: bool, list of error strings)
    """
    errors = []
    rail = payment_rail.strip().upper() if payment_rail else ""

    logger.debug(f"Validating beneficiary for rail: {rail}")

    # --- Fields required for ALL rails ---
    if not beneficiary.get("name"):
        errors.append("Beneficiary name is missing")

    # --- Rail-specific checks ---
    if rail in ("NEFT", "RTGS", "IMPS"):
        # Handle both 'ifsc' (MVP plan) and 'ifsc_code' (internal model)
        ifsc = _get_ifsc(beneficiary)
        ok, msg = validate_ifsc(ifsc)
        if not ok:
            errors.append(msg)
        ok, msg = validate_account_number(beneficiary.get("account_number", ""))
        if not ok:
            errors.append(msg)

    elif rail == "UPI":
        ok, msg = validate_upi(beneficiary.get("upi_id", ""))
        if not ok:
            errors.append(msg)

    elif rail == "SWIFT":
        ok, msg = validate_swift(beneficiary.get("swift_code", ""))
        if not ok:
            errors.append(msg)
        if not beneficiary.get("country"):
            errors.append("Beneficiary country is required for SWIFT payments")

    else:
        # Unknown rail — check for at least one routing identifier
        has_identifier = any([
            _get_ifsc(beneficiary),
            beneficiary.get("upi_id"),
            beneficiary.get("account_number"),
            beneficiary.get("swift_code"),
        ])
        if not has_identifier:
            errors.append(f"No routing identifier found for payment rail '{rail}'")

    all_valid = len(errors) == 0
    logger.debug(f"Beneficiary validation result: valid={all_valid}, errors={errors}")
    return all_valid, errors
