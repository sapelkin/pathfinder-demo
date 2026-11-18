"""A pointy-top hexagonal grid over the demo metro, in axial coordinates.

Each hexagon is 866 m across (circumradius 500 m), so one step
between neighbouring centres is 866 m. The frame is the metro's local plane: x east, y north, km.
"""
from __future__ import annotations

import math
from typing import NamedTuple


class Hex(NamedTuple):
    q: int
    r: int

    @property
    def s(self) -> int:
        return -self.q - self.r

    @property
    def id(self) -> str:
        return f"{self.q},{self.r}"

    def to_dict(self) -> dict[str, int]:
        return {"q": self.q, "r": self.r}


SIZE = 0.5  # circumradius, km
STEP = SIZE * math.sqrt(3.0)  # centre to centre, km (0.866)
_S3 = math.sqrt(3.0)

DIRECTIONS = [Hex(1, 0), Hex(1, -1), Hex(0, -1), Hex(-1, 0), Hex(-1, 1), Hex(0, 1)]


def _round_half_away(x: float) -> float:
    """To the nearest whole number, halves away from zero (Python's ``round`` rounds halves to even)."""
    return math.floor(x + 0.5) if x >= 0 else -math.floor(-x + 0.5)


def center(h: Hex) -> tuple[float, float]:
    return (SIZE * (_S3 * h.q + _S3 / 2 * h.r), SIZE * 1.5 * h.r)


def hex_at(x: float, y: float) -> Hex:
    """The hexagon containing a point, by rounding in cube coordinates."""
    q = (_S3 / 3 * x - y / 3) / SIZE
    r = (2.0 / 3 * y) / SIZE
    s = -q - r
    rq, rr, rs = _round_half_away(q), _round_half_away(r), _round_half_away(s)
    dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    return Hex(int(rq), int(rr))


def corners(h: Hex) -> list[tuple[float, float]]:
    cx, cy = center(h)
    out = []
    for i in range(6):
        a = math.pi / 180 * (60 * i - 30)
        out.append((cx + SIZE * math.cos(a), cy + SIZE * math.sin(a)))
    return out


def neighbors(h: Hex) -> list[Hex]:
    return [Hex(h.q + d.q, h.r + d.r) for d in DIRECTIONS]


def ring(c: Hex, k: int) -> list[Hex]:
    """The hexagons exactly ``k`` steps from ``c`` (the k-th ring), in walking order; ``k`` = 0 is the centre."""
    if k <= 0:
        return [c]
    out: list[Hex] = []
    h = Hex(c.q + DIRECTIONS[4].q * k, c.r + DIRECTIONS[4].r * k)
    for side in range(6):
        for _ in range(k):
            out.append(h)
            h = Hex(h.q + DIRECTIONS[side].q, h.r + DIRECTIONS[side].r)
    return out


def distance(a: Hex, b: Hex) -> int:
    return (abs(a.q - b.q) + abs(a.r - b.r) + abs(a.s - b.s)) // 2
