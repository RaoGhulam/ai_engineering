"""Hard, persistent cap on OpenRouter API calls.

Every request to openrouter.ai (catalog lookups included) must go through
`reserve()` first. The counter is stored on disk so the cap holds across
process restarts and separate benchmark runs.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "data" / "api_call_ledger.json"
HARD_CAP = 1000  # was 67 for the first run; raised for the 30-move rerun

_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    pass


def _load() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    return {"cap": HARD_CAP, "used": 0, "calls": []}


def used() -> int:
    return _load()["used"]


def remaining() -> int:
    return HARD_CAP - used()


def reserve(purpose: str) -> int:
    """Record one call before it is made. Raises if the cap would be passed."""
    with _lock:
        ledger = _load()
        if ledger["used"] >= HARD_CAP:
            raise BudgetExceeded(f"OpenRouter call cap of {HARD_CAP} reached")
        ledger["used"] += 1
        ledger["calls"].append({
            "n": ledger["used"],
            "at": datetime.now(timezone.utc).isoformat(),
            "purpose": purpose,
        })
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        return ledger["used"]
