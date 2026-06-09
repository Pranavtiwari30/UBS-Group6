import re

def validate_beneficiary(details: dict, payment_rail: str) -> dict:
    issues = []
    suggestions = {}

    # Check name
    name = details.get("name")
    if not name or not str(name).strip():
        issues.append("Missing or empty name")

    if payment_rail == "UPI":
        upi_id = details.get("upi_id")
        if not upi_id:
            issues.append("Missing upi_id")
        elif not re.match(r"^\w+@\w+$", str(upi_id)):
            issues.append("Invalid upi_id format")

    elif payment_rail in ("NEFT", "IMPS", "RTGS"):
        account_number = details.get("account_number")
        if not account_number:
            issues.append("Missing account_number")
        else:
            if not re.match(r"^\d{9,18}$", str(account_number)):
                issues.append("Invalid account_number format")

        ifsc = details.get("ifsc")
        if not ifsc:
            issues.append("Missing ifsc")
        else:
            ifsc_str = str(ifsc)
            if re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", ifsc_str):
                pass
            elif re.match(r"^[A-Z]{4}O[A-Z0-9]{6}$", ifsc_str):
                issues.append("IFSC code contains letter 'O' instead of digit '0' at position 5")
                suggestions["corrected_ifsc"] = ifsc_str[:4] + "0" + ifsc_str[5:]
            else:
                issues.append("Invalid ifsc format")
    else:
        issues.append(f"Unsupported payment_rail: {payment_rail}")

    valid = len(issues) == 0

    # Confidence scoring
    if valid:
        confidence = 0.95
    elif len(issues) == 1 and suggestions:
        confidence = 0.88
    elif len(issues) > 1:
        confidence = 0.2
    else:
        if "Missing" in issues[0]:
            confidence = 0.5
        else:
            confidence = 0.2

    return {
        "valid": valid,
        "issues": issues,
        "suggestions": suggestions,
        "confidence": confidence
    }
