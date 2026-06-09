import json
import os
import random
from typing import Any

from fastapi import APIRouter, HTTPException
from models.exception import ExceptionScenario
from canonical_adapter import canonicalize_exception, get_exception_by_case_id

router = APIRouter(prefix="/exceptions", tags=["Exceptions"])

def load_exceptions():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "exceptions.json")
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)

@router.get("/random", response_model=ExceptionScenario)
async def get_random_exception():
    exceptions = load_exceptions()
    if not exceptions:
        raise HTTPException(status_code=404, detail="No exceptions available")
    return random.choice(exceptions)

@router.get("/random/canonical")
async def get_random_canonical_exception() -> dict[str, Any]:
    exceptions = load_exceptions()
    if not exceptions:
        raise HTTPException(status_code=404, detail="No exceptions available")
    return canonicalize_exception(random.choice(exceptions))

@router.get("/{case_id}", response_model=ExceptionScenario)
async def get_exception(case_id: str):
    return get_exception_by_case_id(case_id)

@router.get("/{case_id}/canonical")
async def get_canonical_exception(case_id: str) -> dict[str, Any]:
    return canonicalize_exception(get_exception_by_case_id(case_id))
