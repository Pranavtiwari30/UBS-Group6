import json
import os
from fastapi import APIRouter, HTTPException
from models.user import User

router = APIRouter(prefix="/users", tags=["Users"])

def load_users():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)

@router.get("/{user_id}", response_model=User)
async def get_user(user_id: str):
    users = load_users()
    for user in users:
        if user["user_id"] == user_id:
            return user
    raise HTTPException(status_code=404, detail="User not found")
