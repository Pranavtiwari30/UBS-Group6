from pydantic import BaseModel
from typing import Optional

class ExceptionScenario(BaseModel):
    case_id: str
    payment_id: str
    user_id: str
    exception_type: str
    description: str
    severity: str
    
    # Optional detailed fields potentially used by agents
    exception_code: Optional[str] = None
    current_transaction_status: Optional[str] = None
