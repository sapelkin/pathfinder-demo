"""WA Health's public "Emergency department live activity" page, and the wait model run over it.

The package carries one snapshot
(``data/ed_activity_now.json``, public data, not hackathon Data); in production the feed adapter reads the page.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Optional

from . import eta as eta_engine
from .eta import ETA, Patient
from .rng import SeededRNG
from .simulator import SimConfig

_INF = float("inf")
_MASK = (1 << 64) - 1


@dataclass(frozen=True)
class FeedHospital:
    name: str
    short: str
    t4_avg_wait_min: int
    waiting: int
    in_ed: int

    @property
    def id(self) -> str:
        return self.short


@dataclass(frozen=True)
class FeedSnapshot:
    source: str
    url: str
    taken_text: str
    taken_at: str
    minute_of_week: int  # minutes since Monday 00:00, as SimClock counts
    note: str
    hospitals: list[FeedHospital]

    @staticmethod
    def load() -> "FeedSnapshot":
        text = resources.files("pathfinder_engine").joinpath("data/ed_activity_now.json").read_text(encoding="utf-8")
        return FeedSnapshot.from_json(text)

    @staticmethod
    def from_json(text: str) -> "FeedSnapshot":
        d = json.loads(text)
        return FeedSnapshot(source=d["source"], url=d["url"], taken_text=d["taken_text"], taken_at=d["taken_at"],
                            minute_of_week=int(d["minute_of_week"]), note=d["note"],
                            hospitals=[FeedHospital(name=h["name"], short=h["short"], t4_avg_wait_min=int(h["t4_avg_wait_min"]),
                                                    waiting=int(h["waiting"]), in_ed=int(h["in_ed"])) for h in d["hospitals"]])


CATEGORIES = [3, 4, 5]
HORIZON_MINUTES = 400  # how far back the people now waiting are assumed to have arrived
HORIZON = 720  # a future stops here; a range that reaches it reads "and more"


@dataclass(frozen=True)
class FeedForecast:
    """What the wait model adds to a published row: the throughput the two published numbers imply, and the
    expected wait for someone arriving now, by category."""

    hospital: str
    seenPerHour: float
    scale: float  # this ED's throughput relative to the demo ED at this hour
    byCategory: dict[int, ETA]
    samples: dict[int, list[int]]  # the futures behind each range, for the explainer

    def eta(self, ats: int) -> Optional[ETA]:
        return self.byCategory.get(ats)

    def range_text(self, ats: int) -> Optional[str]:
        """"165–295" or, when the futures run past the horizon, "270+"."""
        e = self.eta(ats)
        if e is None:
            return None
        if e.p90 >= HORIZON:
            return f"{eta_engine.round5(e.p10)}+"
        return e.range_text.replace(" min", "")


def fnv(s: str) -> int:
    """A stable hash of the hospital name (Python's own string hashing changes between runs)."""
    h = 0xcbf29ce484222325
    for b in s.encode("utf-8"):
        h = ((h ^ b) * 0x0000000100000001b3) & _MASK
    return h


def forecast(h: FeedHospital, c: SimConfig, now: int, futures: int = eta_engine.FUTURES) -> Optional[FeedForecast]:
    """The public page gives an average of the recent past. The same wait model that serves the demo ED turns that
    into a forecast for the next arrival, using only the three published numbers and the state's weekly template."""
    if h.waiting <= 0 or h.t4_avg_wait_min <= 0:
        return None
    # Little's law, L = λW: people waiting divided by their average wait is the rate at which people are being
    # seen right now.
    seen_per_minute = h.waiting / h.t4_avg_wait_min
    # The demo ED's service rate at this hour comes from the same template; the ratio scales the whole week.
    scale = seen_per_minute / max(1e-6, c.calls_per_minute(now))

    def arrivals(t: int) -> float:
        return c.arrivals_per_minute(t) * scale

    def calls(t: int) -> float:
        return c.calls_per_minute(t) * scale

    # The people waiting now: categories drawn from who is typically in a waiting room (arrivals weighted by how
    # long each category waits), arrival times spread over the recent past so the average waited is about the
    # published one. Deterministic per hospital, so every run and every recording agrees.
    rng = SeededRNG(fnv(h.name))
    weights = [0.0 if a == 1 else c.triageMix[a - 1] * max(1.0, c.waitMedianByATS[a - 1]) for a in range(1, 6)]
    span = min(HORIZON_MINUTES, 2 * h.t4_avg_wait_min)
    base: list[Patient] = []
    for k in range(h.waiting):
        ats = rng.pick(weights) + 1
        waited = int(span * (k + 0.5) / h.waiting)
        base.append(Patient(id=-1000 - k, ats=ats, arrival=now - waited, patience=_INF, tracked=False, hold=False))
    for a in CATEGORIES:
        base.append(Patient(id=a, ats=a, arrival=now, patience=_INF, tracked=True, hold=False))
    samples = eta_engine.run(base, c, now, (fnv(h.name) + 17) & _MASK, futures=futures, horizon=HORIZON,
                             arrivals=arrivals, calls=calls)
    etas = eta_engine.summarise(samples, base)
    return FeedForecast(hospital=h.short, seenPerHour=seen_per_minute * 60, scale=scale,
                        byCategory={k: v for k, v in etas.items() if k in CATEGORIES},
                        samples={k: v for k, v in samples.items() if k in CATEGORIES})
