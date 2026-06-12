import json
import os
from fastapi import APIRouter, HTTPException
from models.payment import Payment

router = APIRouter(prefix="/payments", tags=["Payments"])

def load_payments():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "payments.json")
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)

@router.get("/{payment_id}", response_model=Payment)
async def get_payment(payment_id: str):
    payments = load_payments()
    for payment in payments:
        if payment["payment_id"] == payment_id:
            return payment
    raise HTTPException(status_code=404, detail="Payment not found")
