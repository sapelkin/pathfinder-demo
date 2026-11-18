"""Expected time to attention: percentiles of when each waiting person is called across simulated futures.

Runs the same waiting-room rules forward from the current
state, many times over, with fresh arrivals from the weekly template. Everyone in the room is followed at once, so
one batch gives every patient their range.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional

from .domain import Episode
from .rng import SeededRNG
from .simulator import SimConfig, SimState

FUTURES = 100
HORIZON = 600
_INF = float("inf")
_MASK = (1 << 64) - 1


def round5(m: int) -> int:
    """To the nearest 5 minutes, halves away from zero, never below 0."""
    x = m / 5
    r = math.floor(x + 0.5) if x >= 0 else -math.floor(-x + 0.5)
    return max(0, int(r) * 5)


@dataclass(frozen=True)
class ETA:
    p10: int
    p50: int
    p90: int
    ahead: int

    @property
    def range_text(self) -> str:
        lo = round5(self.p10)
        hi = max(lo + 5, round5(self.p90))
        return f"under {hi} min" if lo == 0 else f"{lo}–{hi} min"

    def to_dict(self) -> dict:
        return {"p10": self.p10, "p50": self.p50, "p90": self.p90, "ahead": self.ahead, "rangeText": self.range_text}

    @classmethod
    def from_dict(cls, d: dict) -> "ETA":
        return cls(p10=int(d["p10"]), p50=int(d["p50"]), p90=int(d["p90"]), ahead=int(d["ahead"]))


@dataclass
class Patient:
    """A person in the queue, reduced to what the rules need."""

    id: int
    ats: int
    arrival: int
    patience: float
    tracked: bool
    hold: bool


def base_patients(s: SimState, extra: Optional[Episode] = None) -> list[Patient]:
    base = [Patient(id=id, ats=s.episodes[id].ats, arrival=s.episodes[id].arrival, patience=_INF, tracked=True,
                    hold=s.episodes[id].holdFromCall) for id in s.waiting]
    if extra is not None:
        base.append(Patient(id=extra.id, ats=extra.ats, arrival=s.now, patience=_INF, tracked=True, hold=False))
    return base


def estimate(s: SimState, c: SimConfig, extra: Optional[Episode] = None) -> dict[int, ETA]:
    return estimate_with_samples(s, c, extra)[0]


def estimate_with_samples(s: SimState, c: SimConfig, extra: Optional[Episode] = None
                          ) -> tuple[dict[int, ETA], dict[int, list[int]]]:
    """The summary per patient plus the raw minutes-until-seen from every simulated future."""
    base = base_patients(s, extra)
    seed = ((s.now & _MASK) * 2_654_435_761 + len(base)) & _MASK
    samples = run(base, c, s.now, seed, arrivals=c.arrivals_per_minute, calls=c.calls_per_minute)
    return summarise(samples, base), samples


def run(base: list[Patient], c: SimConfig, now: int, seed: int, futures: int = FUTURES, horizon: int = HORIZON,
        arrivals: Optional[Callable[[int], float]] = None, calls: Optional[Callable[[int], float]] = None
        ) -> dict[int, list[int]]:
    """Minutes until each tracked patient is called, in every simulated future. ``arrivals`` and ``calls`` give
    the rates per minute at a minute of the week; the demo ED uses its SimConfig's, a real ED a scaled copy."""
    arrivals = arrivals or c.arrivals_per_minute
    calls = calls or c.calls_per_minute
    tracked_ids = [p.id for p in base if p.tracked and not p.hold]
    if not tracked_ids:
        return {}
    rng = SeededRNG(seed)
    samples: dict[int, list[int]] = {id: [] for id in tracked_ids}
    triage_mix = c.triageMix
    referred = c.referredByATS
    patience_median = c.patienceMedian
    sigma = c.patienceSigma
    targets = c.targets
    end = now + horizon
    # Rates repeat each minute of the week; memoise them per minute offset for the batch.
    rate_a: dict[int, float] = {}
    rate_c: dict[int, float] = {}

    for _ in range(futures):
        # Rows: [id, ats, arrival, patience, tracked, hold]
        q = [[p.id, p.ats, p.arrival, p.patience, p.tracked, p.hold] for p in base]
        remaining = len(tracked_ids)
        t = now
        synthetic = -1
        while t < end and remaining > 0:
            lam = rate_a.get(t)
            if lam is None:
                lam = rate_a[t] = arrivals(t)
            for _ in range(rng.poisson(lam)):
                a = rng.pick(triage_mix) + 1
                if rng.chance(referred[a - 1]):
                    continue
                patience = rng.lognormal(patience_median[a - 1], sigma)
                q.append([synthetic, a, t, patience, False, False])
                synthetic -= 1
            i = 0
            while i < len(q):
                row = q[i]
                if row[1] == 1 and not row[5]:
                    if row[4]:
                        samples[row[0]].append(t - now)
                        remaining -= 1
                    del q[i]
                else:
                    i += 1
            mu = rate_c.get(t)
            if mu is None:
                mu = rate_c[t] = calls(t)
            n = rng.poisson(mu)
            while n > 0:
                best = -1
                best_score = -_INF
                best_ats = 9
                for j, row in enumerate(q):
                    if row[5]:
                        continue
                    score = (t - row[2]) / targets[row[1] - 1]
                    if score > best_score or (score == best_score and row[1] < best_ats):
                        best = j
                        best_score = score
                        best_ats = row[1]
                if best < 0:
                    break
                row = q[best]
                if row[4]:
                    samples[row[0]].append(t - now)
                    remaining -= 1
                del q[best]
                n -= 1
            # Other people may give up and leave; the people we follow are assumed to stay.
            q = [row for row in q if row[4] or (t - row[2]) < row[3]]
            t += 1
        for row in q:
            if row[4] and not row[5]:
                samples[row[0]].append(horizon)
    return samples


def summarise(samples: dict[int, list[int]], base: list[Patient]) -> dict[int, ETA]:
    """Percentiles per tracked patient, and how many people are ahead of each in the queue as it stands."""
    result: dict[int, ETA] = {}
    by_id = {p.id: p for p in base}
    for id, xs in samples.items():
        if not xs:
            continue
        v = sorted(xs)
        n = len(v)

        def pct(p: float) -> int:
            return v[min(n - 1, int(p * n))]

        me = by_id.get(id)
        # People ahead: a more urgent category, or the same category and here earlier.
        ahead = 0
        if me is not None:
            ahead = sum(1 for o in base if not o.hold and o.id != id
                        and (o.ats < me.ats or (o.ats == me.ats and o.arrival < me.arrival)))
        result[id] = ETA(p10=pct(0.1), p50=pct(0.5), p90=pct(0.9), ahead=ahead)
    return result
