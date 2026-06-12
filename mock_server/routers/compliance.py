import json
import os
from fastapi import APIRouter, HTTPException
from models.compliance import Compliance

router = APIRouter(prefix="/compliance", tags=["Compliance"])

def load_compliance():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "compliance.json")
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)

@router.get("/{user_id}", response_model=Compliance)
async def get_compliance(user_id: str):
    records = load_compliance()
    for record in records:
        if record["user_id"] == user_id:
            return record
    raise HTTPException(status_code=404, detail="Compliance record not found")
