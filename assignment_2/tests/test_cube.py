import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from cube import MOVE_NAMES, SOLVED, apply_move, apply_moves, inverse, is_solved, random_scramble  # noqa: E402
from solver import distance, shortest_solution  # noqa: E402


def test_known_kociemba_strings():
    assert apply_move(SOLVED, "U") == "UUUUUUUUUBBBRRRRRRRRRFFFFFFDDDDDDDDDFFFLLLLLLLLLBBBBBB"
    assert apply_move(SOLVED, "R") == "UUFUUFUUFRRRRRRRRRFFDFFDFFDDDBDDBDDBLLLLLLLLLUBBUBBUBB"


def test_inverses_and_orders():
    for m in MOVE_NAMES:
        assert apply_moves(SOLVED, [m, inverse(m)]) == SOLVED
        assert apply_moves(SOLVED, [m[0]] * 4) == SOLVED
    s = SOLVED
    for _ in range(6):
        s = apply_moves(s, ["R", "U", "R'", "U'"])
    assert s == SOLVED  # sexy move has order 6
    s = SOLVED
    for _ in range(105):
        s = apply_moves(s, ["R", "U"])
    assert s == SOLVED  # (R U) has order 105


def test_colour_counts_preserved():
    s = apply_moves(SOLVED, random_scramble(25, random.Random(1)))
    assert sorted(s) == sorted(SOLVED)
    assert not is_solved(s)


def test_bfs_is_exact():
    rng = random.Random(7)
    for n in range(1, 6):
        scr = random_scramble(n, rng)
        st = apply_moves(SOLVED, scr)
        sol = shortest_solution(st)
        assert apply_moves(st, sol) == SOLVED
        assert len(sol) <= n
    assert distance(apply_moves(SOLVED, ["R", "U", "F", "L", "D", "B"])) == 6


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
