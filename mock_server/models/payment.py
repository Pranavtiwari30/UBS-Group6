from pydantic import BaseModel
from typing import Optional, List

class Payment(BaseModel):
    payment_id: str
    user_id: str
    amount: float
    status: str
    beneficiary: str
    
    # Additional fields needed by other agents
    client_id: Optional[str] = None
    beneficiary_details: Optional[str] = None
    payment_rail: Optional[str] = None
    exception_code: Optional[str] = None
    current_transaction_status: Optional[str] = None
    client_contact_history: Optional[List[str]] = None
    submitted_timestamp: Optional[str] = None
    prior_retry_events: Optional[List[str]] = None
    currency: Optional[str] = "USD"
    compliance_hold_status: Optional[str] = None
    network_acknowledgements: Optional[List[str]] = None
