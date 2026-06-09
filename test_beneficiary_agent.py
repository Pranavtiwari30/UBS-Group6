from agents.beneficiary_agent import analyze

# Case 1: IFSC typo → RECOMMEND_REPAIR
def test_ifsc_typo():
    result = analyze({
        "payment_id": "pay-001",
        "payment_summary": {
            "payment_rail": "NEFT",
            "current_transaction_status": "FAILED",
            "funds_movement_status": "NOT_MOVED"
        },
        "beneficiary": {
            "name": "Asha Rao",
            "account_number": "1234567890",
            "ifsc": "HDFCO002345",   # O instead of 0
            "upi_id": None
        },
        "client_contact_history": []
    })
    assert result["action"] == "RECOMMEND_REPAIR", result
    print("✅ test_ifsc_typo passed:", result["action"])


# Case 2: Missing UPI ID → REQUEST_CLIENT_CORRECTION
def test_missing_upi():
    result = analyze({
        "payment_id": "pay-002",
        "payment_summary": {
            "payment_rail": "UPI",
            "current_transaction_status": "FAILED",
            "funds_movement_status": "NOT_MOVED"
        },
        "beneficiary": {
            "name": "Bob",
            "account_number": None,
            "ifsc": None,
            "upi_id": None      # missing
        },
        "client_contact_history": []
    })
    assert result["action"] == "REQUEST_CLIENT_CORRECTION", result
    print("✅ test_missing_upi passed:", result["action"])


# Case 3: Unknown status → MANUAL_REVIEW
def test_unknown_status():
    result = analyze({
        "payment_id": "pay-003",
        "payment_summary": {
            "payment_rail": "NEFT",
            "current_transaction_status": "UNKNOWN",
            "funds_movement_status": "UNKNOWN"
        },
        "beneficiary": {
            "name": "Jane",
            "account_number": "9876543210",
            "ifsc": "SBIN0001234",
            "upi_id": None
        },
        "client_contact_history": []
    })
    assert result["action"] == "MANUAL_REVIEW", result
    print("✅ test_unknown_status passed:", result["action"])


# Case 4: NEW — perfectly valid details → MANUAL_REVIEW
def test_valid_but_rejected():
    result = analyze({
        "payment_id": "pay-004",
        "payment_summary": {
            "payment_rail": "NEFT",
            "current_transaction_status": "FAILED",
            "funds_movement_status": "NOT_MOVED"
        },
        "beneficiary": {
            "name": "Asha Rao",
            "account_number": "1234567890",
            "ifsc": "SBIN0001234",   # perfectly valid
            "upi_id": None
        },
        "client_contact_history": []
    })
    assert result["action"] == "MANUAL_REVIEW", result
    assert result["confidence"] == 0.95, result
    print("✅ test_valid_but_rejected passed:", result["action"])


# Case 5: Unresolved prior contact → MANUAL_REVIEW
def test_unresolved_contact():
    result = analyze({
        "payment_id": "pay-005",
        "payment_summary": {
            "payment_rail": "UPI",
            "current_transaction_status": "FAILED",
            "funds_movement_status": "NOT_MOVED"
        },
        "beneficiary": {
            "name": "Raj",
            "account_number": None,
            "ifsc": None,
            "upi_id": "raj@upi"
        },
        "client_contact_history": [
            {"date": "2026-06-08", "resolved": False}
        ]
    })
    assert result["action"] == "MANUAL_REVIEW", result
    print("✅ test_unresolved_contact passed:", result["action"])


if __name__ == "__main__":
    test_ifsc_typo()
    test_missing_upi()
    test_unknown_status()
    test_valid_but_rejected()
    test_unresolved_contact()
    print("\n✅ All 5 tests passed")
