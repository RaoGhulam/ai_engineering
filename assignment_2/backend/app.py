"""FastAPI backend. The API key never leaves this process.

    uvicorn app:app --app-dir backend --port 8000
"""
import json
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import benchmark
import budget
import config
from cube import SOLVED, apply_moves, random_scramble
from solver import shortest_solution

app = FastAPI(title="Rubik's Cube Race")
FRONTEND = config.ROOT / "frontend"


class RunRequest(BaseModel):
    puzzles: int = 3
    scramble: int = 4
    max_moves: int = 5
    seed: int = 2026
    models: list[str] | None = None   # default: all models
    append: bool = False              # add these models to the existing results.json


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/config")
def get_config():
    return {
        "models": config.MODELS, "solved": SOLVED,
        "budget": {"cap": budget.HARD_CAP, "used": budget.used(), "remaining": budget.remaining()},
        "running": benchmark.LIVE["running"],
    }


@app.get("/api/results")
def get_results():
    if not benchmark.RESULTS.exists():
        raise HTTPException(404, "no benchmark has been run yet")
    return json.loads(benchmark.RESULTS.read_text(encoding="utf-8"))


@app.get("/api/live")
def live(since: int = 0):
    ev = benchmark.LIVE["events"]
    return {"running": benchmark.LIVE["running"], "error": benchmark.LIVE["error"],
            "events": ev[since:], "next": len(ev)}


@app.post("/api/run")
def run(req: RunRequest):
    if benchmark.LIVE["running"]:
        raise HTTPException(409, "a benchmark is already running")
    n_models = len([m for m in config.MODELS if not req.models or m["key"] in req.models])
    worst = req.puzzles * n_models * req.max_moves
    if worst > budget.remaining():
        raise HTTPException(402, f"worst case {worst} calls exceeds the remaining "
                                 f"OpenRouter budget of {budget.remaining()}")

    def work():
        try:
            benchmark.run_benchmark(req.puzzles, req.scramble, req.max_moves, req.seed,
                                    req.models, append=req.append)
        except Exception:
            pass  # error is recorded in LIVE and in results.json

    benchmark.LIVE["running"] = True
    threading.Thread(target=work, daemon=True).start()
    return {"started": True, "worst_case_calls": worst}


@app.get("/api/scramble")
def scramble(length: int = 4, seed: int | None = None):
    """Engine-only preview (no API calls)."""
    import random
    scr = random_scramble(length, random.Random(seed))
    state = apply_moves(SOLVED, scr)
    return {"scramble": scr, "state": state, "optimal": shortest_solution(state)}


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
