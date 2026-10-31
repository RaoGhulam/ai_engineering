import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _read_env_file(path: Path) -> None:
    """Load KEY=VALUE lines; a bare `sk-or-...` line is taken as the API key."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        elif line.startswith("sk-or-"):
            os.environ.setdefault("OPENROUTER_API_KEY", line)


_read_env_file(ROOT / ".env")
_read_env_file(ROOT.parent / ".env")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"

MODELS = [
    {"key": "jev", "name": "Jev 1.13", "category": "System-1 decision model",
     "id": "typesafe/jev-1.13", "interface": "decisions"},
    {"key": "luna", "name": "OpenAI GPT-6 Luna Decisions", "category": "System-1 decision model",
     "id": "openai/gpt-6-luna-decisions", "interface": "decisions"},
    {"key": "clef", "name": "Cloudflare Clef", "category": "System-1 decision model",
     "id": "cloudflare/clef", "interface": "decisions"},
    {"key": "opus", "name": "Claude Opus 5.5", "category": "Frontier LLM",
     "id": "anthropic/claude-opus-5.5", "interface": "chat",
     "chat_params": {"max_tokens": 16000}},
    # Free stand-in for the frontier LLM: the key had no credit for Opus or Sonnet, and the free
    # Nemotron 3 Ultra spent 500 s / 16k tokens on one warm-up move without answering.
    {"key": "gemma", "name": "Google Gemma 4 26B (free)", "category": "LLM (free substitute)",
     "id": "google/gemma-4-26b-a4b-it:free", "interface": "chat",
     "chat_params": {"max_tokens": 8000}},
]

REQUEST_TIMEOUT_S = 180   # same for every model
MAX_RETRIES = 0           # same for every model; failures are logged, not retried
RECENT_MOVES_SHOWN = 5    # same recent-move history policy for every model
