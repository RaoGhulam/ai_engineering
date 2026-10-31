"""Deterministic 3x3 cube engine.

State is a 54-character facelet string in the standard URFDLB order
(the Kociemba convention): U1..U9 R1..R9 F1..F9 D1..D9 L1..L9 B1..B9, each
face read row by row as seen when looking straight at that face (U with B at
the top, D with F at the top). Letters name the face whose centre has that
colour, so the solved cube is "UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB".

Move permutations are derived from 3D sticker coordinates rather than
hand-typed tables, then checked by self-tests in tests/test_cube.py.
Metric: half-turn metric (HTM), 18 moves.
"""
import random

FACES = "URFDLB"
SOLVED = "".join(f * 9 for f in FACES)

# outward normal of each face; x -> R, y -> U, z -> F
NORMALS = {"U": (0, 1, 0), "R": (1, 0, 0), "F": (0, 0, 1),
           "D": (0, -1, 0), "L": (-1, 0, 0), "B": (0, 0, -1)}


def _sticker_pos(face: str, r: int, c: int):
    """3D position of the cubie a sticker sits on, for row r / col c of a face."""
    if face == "U":
        return (c - 1, 1, r - 1)
    if face == "D":
        return (c - 1, -1, 1 - r)
    if face == "F":
        return (c - 1, 1 - r, 1)
    if face == "B":
        return (1 - c, 1 - r, -1)
    if face == "R":
        return (1, 1 - r, 1 - c)
    if face == "L":
        return (-1, 1 - r, c - 1)
    raise ValueError(face)


STICKERS = []  # index -> (position, normal)
for _f in FACES:
    for _r in range(3):
        for _c in range(3):
            STICKERS.append((_sticker_pos(_f, _r, _c), NORMALS[_f]))
_INDEX = {s: i for i, s in enumerate(STICKERS)}


def _rotate(v, axis, quarter_turns_cw):
    """Rotate vector v clockwise (looking at the face along -axis) about axis."""
    x, y, z = v
    for _ in range(quarter_turns_cw % 4):
        if axis == (0, 1, 0):
            x, y, z = -z, y, x
        elif axis == (0, -1, 0):
            x, y, z = z, y, -x
        elif axis == (1, 0, 0):
            x, y, z = x, z, -y
        elif axis == (-1, 0, 0):
            x, y, z = x, -z, y
        elif axis == (0, 0, 1):
            x, y, z = y, -x, z
        elif axis == (0, 0, -1):
            x, y, z = -y, x, z
    return (x, y, z)


def _build_perm(face: str, turns: int):
    """perm[i] = index of the sticker that lands at position i after the move."""
    axis = NORMALS[face]
    perm = list(range(54))
    for src, (pos, nrm) in enumerate(STICKERS):
        if sum(p * a for p, a in zip(pos, axis)) == 1:  # on the turning layer
            dst = _INDEX[(_rotate(pos, axis, turns), _rotate(nrm, axis, turns))]
            perm[dst] = src
    return perm


MOVES = {}
for _f in FACES:
    MOVES[_f] = _build_perm(_f, 1)
    MOVES[_f + "2"] = _build_perm(_f, 2)
    MOVES[_f + "'"] = _build_perm(_f, 3)
MOVE_NAMES = [f + s for f in "URFDLB" for s in ("", "'", "2")]

FACE_NAMES = {"U": "upper", "R": "right", "F": "front", "D": "down", "L": "left", "B": "back"}


def move_description(m: str) -> str:
    face = FACE_NAMES[m[0]]
    if m.endswith("2"):
        return f"Turn the {face} face by 180 degrees"
    if m.endswith("'"):
        return f"Turn the {face} face counterclockwise by 90 degrees"
    return f"Turn the {face} face clockwise by 90 degrees"


def apply_move(state: str, move: str) -> str:
    p = MOVES[move]
    return "".join(state[i] for i in p)


def apply_moves(state: str, moves) -> str:
    for m in moves:
        state = apply_move(state, m)
    return state


def is_solved(state: str) -> bool:
    return all(len(set(state[i * 9:(i + 1) * 9])) == 1 for i in range(6))


def inverse(move: str) -> str:
    if move.endswith("2"):
        return move
    if move.endswith("'"):
        return move[0]
    return move + "'"


_OPPOSITE = {"U": "D", "D": "U", "R": "L", "L": "R", "F": "B", "B": "F"}


def random_scramble(length: int, rng: random.Random):
    """Random HTM scramble with no same-face repeats and no X X' cancellations."""
    seq = []
    while len(seq) < length:
        m = rng.choice(MOVE_NAMES)
        if seq and seq[-1][0] == m[0]:
            continue
        # U D U style: same face separated only by its commuting opposite
        if len(seq) >= 2 and seq[-2][0] == m[0] and seq[-1][0] == _OPPOSITE[m[0]]:
            continue
        seq.append(m)
    return seq


def net(state: str) -> str:
    """Human-readable unfolded net (U on top, L F R B in a row, D underneath)."""
    f = {FACES[i]: state[i * 9:(i + 1) * 9] for i in range(6)}
    row = lambda face, r: " ".join(f[face][r * 3:r * 3 + 3])
    lines = []
    for r in range(3):
        lines.append("      " + row("U", r))
    for r in range(3):
        lines.append("  ".join(row(x, r) for x in "LFRB"))
    for r in range(3):
        lines.append("      " + row("D", r))
    return "\n".join(lines)
