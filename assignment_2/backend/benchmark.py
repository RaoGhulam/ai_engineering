"""Benchmark runner: every model plays the same scrambled puzzles under the same rules.

    python backend/benchmark.py --puzzles 3 --scramble 4 --max-moves 5 --seed 2026

Before any request is sent, the worst-case number of calls
(puzzles x models x max_moves) is checked against the remaining API budget.
"""
import argparse
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import adapters
import budget
import config
from cube import SOLVED, apply_move, apply_moves, is_solved, net, random_scramble
from solver import shortest_solution

RESULTS = config.DATA / "results.json"
EVENTS = config.DATA / "live_events.jsonl"

_events_lock = threading.Lock()
LIVE = {"running": False, "events": [], "error": None}


def emit(ev: dict):
    ev["t"] = time.time()
    with _events_lock:
        LIVE["events"].append(ev)
        with EVENTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev) + "\n")


def make_puzzles(n: int, scramble_len: int, seed: int):
    """Scrambles whose exact BFS distance equals the scramble length (no hidden shortcuts)."""
    rng = random.Random(seed)
    puzzles = []
    while len(puzzles) < n:
        scr = random_scramble(scramble_len, rng)
        state = apply_moves(SOLVED, scr)
        opt = shortest_solution(state)
        if opt is None or len(opt) != scramble_len or any(p["state"] == state for p in puzzles):
            continue
        puzzles.append({"id": f"P{len(puzzles) + 1}", "scramble": scr, "state": state,
                        "optimal_len": len(opt), "optimal_solution": opt})
    return puzzles


def state_payload(state: str, history: list, max_moves: int):
    return {
        "cube_facelets": state,
        "net": net(state),
        "recent_moves": history[-config.RECENT_MOVES_SHOWN:],
        "moves_made": len(history),
        "moves_remaining": max_moves - len(history),
    }


def run_trial(model: dict, puzzle: dict, max_moves: int):
    state = puzzle["state"]
    applied, turns = [], []
    t_start = time.perf_counter()
    emit({"type": "trial_start", "model": model["key"], "puzzle": puzzle["id"], "state": state})
    abort = None
    for turn in range(1, max_moves + 1):
        payload = state_payload(state, applied, max_moves)
        res = adapters.choose_move(model, payload, f"{model['key']} {puzzle['id']} turn {turn}")
        if res.move:
            state = apply_move(state, res.move)
            applied.append(res.move)
        rec = {"turn": turn, "move": res.move, "latency_s": round(res.latency_s, 4),
               "error": res.error, "confidence": res.confidence,
               "probabilities": res.probabilities, "raw": res.raw if res.error else None,
               "usage": res.usage, "state_after": state}
        turns.append(rec)
        emit({"type": "move", "model": model["key"], "puzzle": puzzle["id"], **rec})
        if is_solved(state):
            break
        # any 4xx, rate limiting included, would repeat on an immediate retry: stop instead of
        # burning calls (a free model's 429s once used up 15 calls in ~12 s)
        if res.error and res.error.startswith("http_4"):
            abort = res.error
            break
    total = time.perf_counter() - t_start
    solved = is_solved(state)
    trial = {
        "puzzle_id": puzzle["id"], "model_key": model["key"], "model_id": model["id"],
        "solved": solved, "moves": applied, "turns": turns,
        "moves_applied": len(applied), "calls": len(turns),
        "invalid": sum(1 for t in turns if t["error"]),
        "total_time_s": round(total, 3),
        "avg_latency_s": round(sum(t["latency_s"] for t in turns) / len(turns), 4) if turns else None,
        "optimal_len": puzzle["optimal_len"],
        "gap": len(applied) - puzzle["optimal_len"] if solved else None,
        "aborted": abort, "final_state": state,
    }
    emit({"type": "trial_end", "model": model["key"], "puzzle": puzzle["id"],
          "solved": solved, "moves_applied": len(applied), "total_time_s": trial["total_time_s"],
          "aborted": abort})
    return trial


def summarize(results: dict):
    rows = []
    for m in config.MODELS:
        ts = [t for t in results["trials"] if t["model_key"] == m["key"]]
        if not ts:
            continue
        lat = [x["latency_s"] for t in ts for x in t["turns"]]
        solved = [t for t in ts if t["solved"]]
        gaps = [t["gap"] for t in solved]
        rows.append({
            "key": m["key"], "name": m["name"], "category": m["category"], "id": m["id"],
            "trials": len(ts),
            "avg_move_latency_s": round(sum(lat) / len(lat), 3) if lat else None,
            "median_move_latency_s": round(sorted(lat)[len(lat) // 2], 3) if lat else None,
            "total_time_s": round(sum(t["total_time_s"] for t in ts), 2),
            "avg_trial_time_s": round(sum(t["total_time_s"] for t in ts) / len(ts), 2),
            "total_moves": sum(t["moves_applied"] for t in ts),
            "total_calls": sum(t["calls"] for t in ts),
            "invalid_outputs": sum(t["invalid"] for t in ts),
            "solved": len(solved),
            "success_rate": round(100 * len(solved) / len(ts), 1),
            "avg_gap": round(sum(gaps) / len(gaps), 2) if gaps else None,
            "avg_moves_when_solved": round(sum(t["moves_applied"] for t in solved) / len(solved), 2)
            if solved else None,
        })
    return rows


def _load_for_append(n_puzzles, scramble_len, max_moves, seed):
    """Reuse an earlier run with identical settings so new models play the same puzzles."""
    if not RESULTS.exists():
        return None
    old = json.loads(RESULTS.read_text(encoding="utf-8"))
    m = old["meta"]
    if (m["seed"], m["scramble_len"], m["max_moves"], len(old["puzzles"])) != \
            (seed, scramble_len, max_moves, n_puzzles):
        raise ValueError("--append needs the same --puzzles/--scramble/--max-moves/--seed as results.json")
    return old


def run_benchmark(n_puzzles: int, scramble_len: int, max_moves: int, seed: int,
                  model_keys=None, parallel=True, append=False):
    models = [m for m in config.MODELS if not model_keys or m["key"] in model_keys]
    worst_case = n_puzzles * len(models) * max_moves
    if worst_case > budget.remaining():
        raise budget.BudgetExceeded(
            f"worst case {worst_case} calls exceeds remaining budget {budget.remaining()}")
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    LIVE.update(running=True, events=[], error=None)
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    EVENTS.write_text("", encoding="utf-8")
    puzzles = make_puzzles(n_puzzles, scramble_len, seed)
    results = _load_for_append(n_puzzles, scramble_len, max_moves, seed) if append else None
    if results:
        assert [p["state"] for p in results["puzzles"]] == [p["state"] for p in puzzles]
        keys = {m["key"] for m in models}
        results["trials"] = [t for t in results["trials"] if t["model_key"] not in keys]
        results["meta"].setdefault("runs", []).append(
            {"created": datetime.now(timezone.utc).isoformat(), "models": sorted(keys)})
    else:
        results = {
            "meta": {
                "created": datetime.now(timezone.utc).isoformat(),
                "seed": seed, "scramble_len": scramble_len, "max_moves": max_moves,
                "metric": "HTM (half-turn metric, 18 moves)",
                "timeout_s": config.REQUEST_TIMEOUT_S, "retries": config.MAX_RETRIES,
                "recent_moves_shown": config.RECENT_MOVES_SHOWN,
                "budget_used_before": budget.used(),
            },
            "puzzles": puzzles, "trials": [],
        }
    results["meta"]["models"] = config.MODELS
    emit({"type": "benchmark_start", "puzzles": puzzles, "models": [m["key"] for m in models],
          "max_moves": max_moves})
    try:
        for p in puzzles:
            emit({"type": "puzzle_start", "puzzle": p["id"], "state": p["state"]})
            if parallel:
                with ThreadPoolExecutor(len(models)) as ex:
                    trials = list(ex.map(lambda m: run_trial(m, p, max_moves), models))
            else:
                trials = [run_trial(m, p, max_moves) for m in models]
            results["trials"].extend(trials)
            RESULTS.write_text(json.dumps(results, indent=1), encoding="utf-8")
    except Exception as e:  # keep partial results and surface the error
        LIVE["error"] = str(e)
        raise
    finally:
        results["meta"]["budget_used_after"] = budget.used()
        results["summary"] = summarize(results)
        RESULTS.write_text(json.dumps(results, indent=1), encoding="utf-8")
        emit({"type": "benchmark_end", "summary": results["summary"], "error": LIVE["error"]})
        LIVE["running"] = False
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--puzzles", type=int, default=3)
    ap.add_argument("--scramble", type=int, default=4)
    ap.add_argument("--max-moves", type=int, default=5)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--append", action="store_true",
                    help="add/replace these models' trials in an existing results.json")
    ap.add_argument("--dry-run", action="store_true", help="only build puzzles; no API calls")
    a = ap.parse_args()
    if a.dry_run:
        for p in make_puzzles(a.puzzles, a.scramble, a.seed):
            print(p["id"], " ".join(p["scramble"]), "-> optimal", " ".join(p["optimal_solution"]))
        print("budget remaining:", budget.remaining(),
              "worst case:", a.puzzles * len(a.models or config.MODELS) * a.max_moves)
    else:
        out = run_benchmark(a.puzzles, a.scramble, a.max_moves, a.seed, a.models, append=a.append)
        for row in out["summary"]:
            print(json.dumps(row))
