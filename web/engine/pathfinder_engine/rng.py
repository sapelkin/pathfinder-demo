"""Seeded random numbers, so the demo waiting room is identical on every run, on every platform.

A 64-bit splitmix generator with wrapping
arithmetic (masked to 64 bits here), and the same derived draws in the same order.
"""
from __future__ import annotations

import math
from typing import Sequence, TypeVar

T = TypeVar("T")

_MASK = (1 << 64) - 1
_GOLDEN = 0x9E3779B97F4A7C15
_MIX1 = 0xBF58476D1CE4E5B9
_MIX2 = 0x94D049BB133111EB
_TWO53 = 9_007_199_254_740_992.0


class SeededRNG:
    __slots__ = ("state",)

    def __init__(self, seed: int):
        seed &= _MASK
        self.state = _GOLDEN if seed == 0 else seed

    def next(self) -> int:
        self.state = (self.state + _GOLDEN) & _MASK
        z = self.state
        z = ((z ^ (z >> 30)) * _MIX1) & _MASK
        z = ((z ^ (z >> 27)) * _MIX2) & _MASK
        return z ^ (z >> 31)

    def uniform(self) -> float:
        return (self.next() >> 11) / _TWO53

    def chance(self, p: float) -> bool:
        return self.uniform() < p

    def normal(self) -> float:
        u1 = max(self.uniform(), 1e-12)
        u2 = self.uniform()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def lognormal(self, median: float, sigma: float) -> float:
        return median * math.exp(sigma * self.normal())

    def poisson(self, lam: float) -> int:
        if not lam > 0:
            return 0
        limit = math.exp(-lam)
        k = 0
        p = 1.0
        while True:
            k += 1
            p *= self.uniform()
            if not p > limit:
                break
        return k - 1

    def pick(self, weights: Sequence[float]) -> int:
        total = 0.0
        for w in weights:
            total += w
        if not total > 0:
            return 0
        u = self.uniform() * total
        for i, w in enumerate(weights):
            u -= w
            if u <= 0:
                return i
        return len(weights) - 1

    def element(self, items: Sequence[T]) -> T:
        return items[min(len(items) - 1, int(self.uniform() * len(items)))]

    def int(self, lo: int, hi: int) -> int:
        """A whole number in the closed range ``lo...hi``."""
        count = hi - lo + 1
        return lo + min(count - 1, int(self.uniform() * count))
