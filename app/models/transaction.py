"""
Transaction data model.
Defines the standard input schema for all payment exception agents.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class BeneficiaryDetails(BaseModel):
    name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    upi_id: Optional[str] = None
    bank_name: Optional[str] = None
    country: Optional[str] = None
    swift_code: Optional[str] = None


class Transaction(BaseModel):
    payment_id: str
    client_id: str
    payment_rail: str                      # e.g., NEFT, UPI, SWIFT, IMPS, RTGS
    amount: float
    currency: str
    beneficiary_details: Dict[str, Any]    # Flexible dict for raw input
    submitted_timestamp: str
    exception_code: str                    # e.g., INVALID_BENEFICIARY, DUPLICATE, SANCTION_HIT
    current_transaction_status: str        # e.g., FAILED, HELD, PENDING
    prior_retry_events: List[Dict[str, Any]] = Field(default_factory=list)
    compliance_hold_status: str = "NONE"   # e.g., NONE, AML_HOLD, SANCTION_HOLD
    network_acknowledgements: List[Dict[str, Any]] = Field(default_factory=list)
