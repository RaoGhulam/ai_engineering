"""Exact shortest-path distance (HTM) via bidirectional breadth-first search.

Complete for the small primary-benchmark states: a frontier of depth 4 from
the solved side (~44k states) plus depth 4 from the scramble side proves
optimality for any distance up to 8.
"""
from cube import MOVE_NAMES, SOLVED, apply_move, inverse

_SOLVED_LAYERS = None


def _bfs_layers(start: str, depth: int):
    seen = {start: []}
    frontier = [start]
    for _ in range(depth):
        nxt = []
        for s in frontier:
            path = seen[s]
            for m in MOVE_NAMES:
                if path and path[-1][0] == m[0]:
                    continue
                t = apply_move(s, m)
                if t not in seen:
                    seen[t] = path + [m]
                    nxt.append(t)
        frontier = nxt
    return seen


def _solved_side(depth=4):
    global _SOLVED_LAYERS
    if _SOLVED_LAYERS is None:
        _SOLVED_LAYERS = _bfs_layers(SOLVED, depth)
    return _SOLVED_LAYERS


def shortest_solution(state: str, max_depth: int = 8):
    """Return an optimal move list from `state` to solved, or None if > max_depth."""
    back = _solved_side(min(4, max_depth))
    if state in back:
        return [inverse(m) for m in reversed(back[state])]
    # forward BFS level by level; the first meeting level is optimal
    seen = {state: []}
    frontier = [state]
    for _ in range(max_depth - 4):
        nxt = []
        best = None
        for s in frontier:
            path = seen[s]
            for m in MOVE_NAMES:
                t = apply_move(s, m)
                if t in seen:
                    continue
                p = path + [m]
                seen[t] = p
                nxt.append(t)
                if t in back:
                    cand = p + [inverse(x) for x in reversed(back[t])]
                    if best is None or len(cand) < len(best):
                        best = cand
        if best is not None:
            return best
        frontier = nxt
    return None


def distance(state: str, max_depth: int = 8):
    sol = shortest_solution(state, max_depth)
    return None if sol is None else len(sol)
