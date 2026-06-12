from pydantic import BaseModel

class Compliance(BaseModel):
    user_id: str
    aml_hold: bool
    sanctions_flag: bool
