from agents.validator import validate_beneficiary


def analyze(agent_input: dict) -> dict:

    # --- Parse nested schema ---
    payment_id = agent_input.get("payment_id", "UNKNOWN")
    payment_summary = agent_input.get("payment_summary", {})
    beneficiary = agent_input.get("beneficiary", {})
    client_contact_history = agent_input.get("client_contact_history", [])

    payment_rail = payment_summary.get("payment_rail", "")
    status = payment_summary.get("current_transaction_status", "")
    funds_status = payment_summary.get("funds_movement_status", "")

    evidence = []
    next_steps = []

    # --- Safety gate 1: unclear funds movement ---
    if status in ("UNKNOWN", "PENDING") or funds_status == "UNKNOWN":
        return {
            "action": "MANUAL_REVIEW",
            "automation_allowed": False,
            "confidence": 0.5,
            "risk_level": "HIGH",
            "evidence": [
                f"current_transaction_status={status}",
                f"funds_movement_status={funds_status}"
            ],
            "explanation": (
                "Transaction status is unclear. "
                "Funds movement cannot be confirmed. "
                "Manual review required before any action."
            ),
            "next_steps": [
                "Check payment rail acknowledgement",
                "Confirm funds movement status with core banking",
                "Do not retry until status is confirmed"
            ]
        }

    # --- Safety gate 2: prior unresolved client outreach ---
    unresolved = [
        c for c in client_contact_history
        if c.get("resolved") is False
    ]
    if unresolved:
        return {
            "action": "MANUAL_REVIEW",
            "automation_allowed": False,
            "confidence": 0.6,
            "risk_level": "MEDIUM",
            "evidence": [
                f"unresolved_client_contacts={len(unresolved)}",
                f"last_contact={unresolved[-1].get('date', 'unknown')}"
            ],
            "explanation": (
                "Prior unresolved client outreach exists. "
                "Sending another notification risks duplicate contact. "
                "Operations should follow up on existing case."
            ),
            "next_steps": [
                "Check existing client outreach case",
                "Do not send duplicate notification",
                "Escalate to operations if no response within SLA"
            ]
        }

    # --- Core validation ---
    validation = validate_beneficiary(beneficiary, payment_rail)
    confidence = validation["confidence"]
    issues = validation["issues"]
    suggestions = validation["suggestions"]

    evidence.append(f"payment_rail={payment_rail}")
    evidence.append(f"exception_code={agent_input.get('exception_code', 'INVALID_BENEFICIARY')}")
    for issue in issues:
        evidence.append(f"validation_issue={issue}")
    if suggestions:
        for k, v in suggestions.items():
            evidence.append(f"suggestion={k}:{v}")

    # --- NEW: perfectly valid payload = ambiguous rejection ---
    # If our validator says everything looks correct (0.95),
    # the bank rejected it for a reason we can't see.
    # Safer to send to manual review than guess.
    if confidence >= 0.95 and not issues:
        return {
            "action": "MANUAL_REVIEW",
            "automation_allowed": False,
            "confidence": 0.95,
            "risk_level": "MEDIUM",
            "evidence": evidence + ["all_fields_validated_as_correct"],
            "explanation": (
                "Beneficiary details appear structurally valid "
                "but the payment was still rejected by the bank. "
                "Root cause is ambiguous — manual investigation required."
            ),
            "next_steps": [
                "Contact beneficiary bank for rejection reason",
                "Verify account is active and not dormant",
                "Do not retry without bank confirmation"
            ]
        }

    # --- Fixable typo found ---
    if confidence >= 0.85 and suggestions:
        return {
            "action": "RECOMMEND_REPAIR",
            "automation_allowed": False,
            "confidence": confidence,
            "risk_level": "LOW",
            "evidence": evidence,
            "explanation": (
                f"Likely typo detected in beneficiary details. "
                f"Suggested correction: {suggestions}. "
                f"Repair recommended but requires confirmation before resubmission."
            ),
            "next_steps": [
                f"Apply suggested correction: {suggestions}",
                "Confirm corrected details with client before resubmission",
                "Resubmit only after confirmation"
            ]
        }

    # --- Wrong data, client must re-enter ---
    if confidence >= 0.75:
        return {
            "action": "REQUEST_CLIENT_CORRECTION",
            "automation_allowed": False,
            "confidence": confidence,
            "risk_level": "MEDIUM",
            "evidence": evidence,
            "explanation": (
                "Beneficiary details are invalid and cannot be auto-corrected. "
                "Client must provide updated beneficiary information."
            ),
            "next_steps": [
                "Notify client of failed payment",
                "Request corrected beneficiary details",
                "Do not retry until client provides new details"
            ]
        }

    # --- Low confidence fallback / Missing Fields ---
    if any("Missing" in issue for issue in issues):
        return {
            "action": "REQUEST_CLIENT_CORRECTION",
            "automation_allowed": False,
            "confidence": confidence,
            "risk_level": "HIGH",
            "evidence": evidence,
            "explanation": (
                "Beneficiary details are missing required fields. "
                "Client must provide complete beneficiary information."
            ),
            "next_steps": [
                "Notify client of failed payment",
                "Request missing beneficiary details",
                "Do not retry until client provides complete details"
            ]
        }

    return {
        "action": "MANUAL_REVIEW",
        "automation_allowed": False,
        "confidence": confidence,
        "risk_level": "HIGH",
        "evidence": evidence,
        "explanation": (
            "Multiple validation failures detected. "
            "Confidence too low for automated recommendation. "
            "Manual review required."
        ),
        "next_steps": [
            "Operations team to manually review beneficiary details",
            "Contact client directly",
            "Document findings before any action"
        ]
    }
