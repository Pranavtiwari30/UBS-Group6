"""
General utility helpers shared across all agents.
Kept deliberately minimal — no magic, just pure functions.
"""

from datetime import datetime, timezone
from typing import Any, Optional


def safe_get(data: dict, *keys, default=None) -> Any:
    """
    Safely traverse nested dicts without KeyError.
    Example: safe_get(tx, "beneficiary_details", "ifsc_code")
    """
    for key in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(key, default)
    return data


def parse_timestamp(ts: str) -> Optional[datetime]:
    """
    Parse an ISO-8601 timestamp string into a timezone-aware datetime.
    Returns None if parsing fails — never raises.
    """
    if not ts:
        return None
    try:
        # Handle both 'Z' suffix and '+00:00' offset
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def seconds_between(ts1: str, ts2: str) -> Optional[float]:
    """
    Return the absolute number of seconds between two ISO timestamps.
    Returns None if either timestamp cannot be parsed.
    """
    dt1 = parse_timestamp(ts1)
    dt2 = parse_timestamp(ts2)
    if dt1 is None or dt2 is None:
        return None
    return abs((dt2 - dt1).total_seconds())


def normalize_string(value: Optional[str]) -> str:
    """Strip and uppercase a string value for consistent comparisons."""
    if not value:
        return ""
    return str(value).strip().upper()


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()
