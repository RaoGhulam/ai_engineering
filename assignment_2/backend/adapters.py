"""OpenRouter adapters. Both interfaces implement one game-action contract:

    choose_move(model, state_payload) -> MoveResult

The decision models get the state through the Decisions API with a typed
`choice` question; Opus gets the identical state, instructions and option
list through chat completions with a JSON-schema constrained reply.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field

import httpx

import budget
import config
from cube import MOVE_NAMES, move_description

INSTRUCTIONS = (
    "You are playing a 3x3 Rubik's Cube. Choose the single next move most likely to progress "
    "toward the solved cube (every face a single colour) in as few total moves as possible. "
    "The state is a 54-character facelet string in URFDLB order: U1-U9, R1-R9, F1-F9, D1-D9, "
    "L1-L9, B1-B9, each face read row by row as seen looking directly at that face "
    "(U is viewed from above with B at the top; D is viewed from below with F at the top). "
    "Each letter names the face whose centre sticker has that colour. Moves use standard "
    "Singmaster notation in the half-turn metric."
)
CRITERIA = {m: move_description(m) for m in MOVE_NAMES}


@dataclass
class MoveResult:
    move: str | None            # validated move, or None if the reply was unusable
    latency_s: float
    raw: str = ""
    error: str | None = None    # "malformed", "invalid_move", "http_<code>", "timeout", ...
    confidence: float | None = None
    probabilities: dict | None = None
    usage: dict = field(default_factory=dict)


def _headers():
    return {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Rubiks Cube Race",
    }


_pool = ThreadPoolExecutor(8)


def _post(url, body, purpose):
    """POST with a hard wall-clock deadline. httpx's own timeout is per read, and OpenRouter
    keeps slow requests alive with whitespace, so it alone never fires."""
    budget.reserve(purpose)
    t0 = time.perf_counter()
    fut = _pool.submit(httpx.post, url, headers=_headers(), json=body,
                       timeout=config.REQUEST_TIMEOUT_S)
    try:
        r = fut.result(timeout=config.REQUEST_TIMEOUT_S)
    except (FutureTimeout, httpx.TimeoutException):
        return None, time.perf_counter() - t0, "timeout"
    except httpx.HTTPError as e:
        return None, time.perf_counter() - t0, f"network: {e}"
    return r, time.perf_counter() - t0, None


def decide_move(model_id: str, state: dict, purpose: str) -> MoveResult:
    body = {
        "model": model_id,
        "state": state,
        "questions": {
            "next_move": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": CRITERIA}
        },
    }
    r, dt, err = _post(config.DECISIONS_URL, body, purpose)
    if err:
        return MoveResult(None, dt, error=err)
    raw = r.text
    if r.status_code != 200:
        return MoveResult(None, dt, raw=raw[:2000], error=f"http_{r.status_code}")
    try:
        data = r.json()
        ans = data["answers"]["next_move"]
        choice = ans.get("choice")
    except (ValueError, KeyError, TypeError):
        return MoveResult(None, dt, raw=raw[:2000], error="malformed")
    res = MoveResult(None, dt, raw=raw[:2000], confidence=ans.get("confidence"),
                     probabilities=ans.get("probabilities"), usage=data.get("usage", {}))
    if choice in MOVE_NAMES:
        res.move = choice
    else:
        res.error = "invalid_move"
    return res


MOVE_SCHEMA = {
    "name": "next_move",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"move": {"type": "string", "enum": MOVE_NAMES}},
        "required": ["move"],
        "additionalProperties": False,
    },
}


_MOVE_OBJECT = re.compile(r'\{\s*"move"\s*:\s*"([^"]*)"\s*\}')


def _parse_move(content: str):
    """Strict JSON first; else the last bare {"move": "..."} object in the text (e.g. in a code fence)."""
    try:
        return json.loads(content)["move"]
    except (ValueError, KeyError, TypeError):
        found = _MOVE_OBJECT.findall(content or "")
        return found[-1] if found else None


def chat_move(model_id: str, state: dict, purpose: str, params: dict | None = None,
              structured: bool = True) -> MoveResult:
    user = {
        "state": state,
        "question": {"name": "next_move", "type": "choice",
                     "instructions": INSTRUCTIONS, "options": CRITERIA},
        "response_format": 'Reply with exactly one JSON object: {"move": "<one option key>"}',
    }
    body = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are a Rubik's Cube solving agent. You answer with "
             "exactly one JSON object naming one allowed move, and nothing else."},
            {"role": "user", "content": json.dumps(user, indent=1)},
        ],
        "max_tokens": 32000,
        **(params or {}),
    }
    if structured:
        body["response_format"] = {"type": "json_schema", "json_schema": MOVE_SCHEMA}
    r, dt, err = _post(config.CHAT_URL, body, purpose)
    if err:
        return MoveResult(None, dt, error=err)
    raw = r.text
    if r.status_code != 200:
        return MoveResult(None, dt, raw=raw[:2000], error=f"http_{r.status_code}")
    try:
        data = r.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, TypeError, IndexError):
        return MoveResult(None, dt, raw=raw[:2000], error="malformed")
    res = MoveResult(None, dt, raw=(content or "")[:2000], usage=data.get("usage", {}))
    move = _parse_move(content)
    if move is None:
        res.error = "malformed"
        return res
    if move in MOVE_NAMES:
        res.move = move
    else:
        res.error = "invalid_move"
    return res


def choose_move(model: dict, state: dict, purpose: str) -> MoveResult:
    if model["interface"] == "decisions":
        return decide_move(model["id"], state, purpose)
    return chat_move(model["id"], state, purpose, model.get("chat_params"),
                     model.get("structured_outputs", True))
