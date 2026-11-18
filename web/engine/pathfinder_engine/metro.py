"""Metro mode: the simulated ED can be any of the metropolitan EDs in WA Health's live-activity snapshot.

The snapshot (``data/ed_activity_now.json``) gives three numbers per hospital: people waiting, people in the ED and
the category-4 average wait. From them this module builds the room "as it stands" at the demo's start minute
(Saturday 2:30 pm; the snapshot itself was taken on a Sunday night, which the source text says), scales the demo
ED's arrival and service rates to the hospital's throughput with Little's law (as ``feed.py`` does for its
forecast) while keeping the hour-of-week shape, renames the lattice's suburbs to real ones around the hospital, and
measures, rather than declares, what the redirect gate would do to that room over the next six hours. Roads, bus
corridors and services stay the invented demo lattice. Standard library only, so it runs under Pyodide too.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from . import feed, network, rightdoor, simulator
from .domain import ArrivalMode, Cohort, Episode, Outcome, Stage
from .network import Suburb
from .rightdoor import Purpose
from .rng import SeededRNG
from .seed import SeedFile
from .simulator import SimConfig, SimEvent, SimState

if TYPE_CHECKING:  # the measurement takes a model; model.py imports this module
    from .model import AppModel

DEMO_ID = "demo"
DEFAULT_HOSPITAL = "fiona-stanley"
DISCLAIMER = ("Demo metro: every hospital, clinic, road and bus route is invented. Travel times come from the hexagon "
              "model, not a routing service.")
HORIZON_MINUTES = 360
REPLICAS = 3
START_MINUTE = 5 * 1440 + 14 * 60 + 30  # the demo's Saturday 2:30 pm (model.START_MINUTE; kept here to avoid a cycle)


def slug(short: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", short.lower()).strip("-")


@dataclass(frozen=True)
class Hospital:
    id: str
    name: str
    short: str
    waiting: int
    in_ed: int
    t4_avg_wait_min: int
    suburbs: tuple[Suburb, ...]

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "short": self.short, "waiting": self.waiting, "inEd": self.in_ed,
                "t4AvgWaitMin": self.t4_avg_wait_min, "suburbs": [s.name for s in self.suburbs]}


# Real suburb names around each hospital, placed as rough km offsets (x east, y north) on the demo lattice. Spread is
# the standard deviation of homes around the centre; weight the share of the ED's patients. Distances and directions
# are approximate; everything else on the map is invented.
def _s(name: str, x: float, y: float, spread: float = 1.0, weight: float = 10) -> Suburb:
    return Suburb(name, x, y, spread, weight)


HOSPITAL_SUBURBS: dict[str, tuple[Suburb, ...]] = {
    "armadale": (_s("Armadale", 0.0, 0.3, 1.0, 16), _s("Kelmscott", -1.5, 3.5, 1.1, 14), _s("Seville Grove", -2.5, 0.5, 1.0, 13),
                 _s("Camillo", -2.0, 2.0, 0.9, 10), _s("Brookdale", 0.5, -2.5, 0.9, 9), _s("Mount Nasura", 1.5, 1.0, 0.8, 8),
                 _s("Harrisdale", -6.0, 3.5, 1.3, 12), _s("Byford", -1.0, -7.0, 1.4, 10)),
    "fiona-stanley": (_s("Murdoch", 0.0, 0.5, 0.9, 12), _s("Bull Creek", 2.5, 1.5, 1.0, 13), _s("Leeming", 1.5, -2.5, 1.1, 14),
                      _s("Kardinya", -2.5, 0.5, 1.0, 12), _s("Bateman", 1.0, 2.5, 0.8, 9), _s("Winthrop", -1.0, 2.0, 0.8, 9),
                      _s("Willetton", 5.0, 0.0, 1.3, 15), _s("Melville", -3.0, 4.0, 1.2, 12)),
    "joondalup": (_s("Joondalup", 0.0, 0.0, 1.0, 16), _s("Edgewater", 0.0, -2.5, 1.0, 13), _s("Currambine", -1.0, 3.0, 1.0, 13),
                  _s("Kinross", -1.0, 5.0, 1.1, 11), _s("Heathridge", -2.5, -1.5, 1.0, 13), _s("Wanneroo", 6.0, -1.0, 1.4, 14),
                  _s("Ocean Reef", -3.5, 1.0, 1.1, 12)),
    "king-edward": (_s("Subiaco", 0.0, 0.0, 0.8, 16), _s("West Leederville", 1.5, 1.5, 0.8, 12), _s("Shenton Park", -1.5, -1.0, 0.9, 12),
                    _s("Daglish", -1.0, 0.5, 0.6, 8), _s("Jolimont", -0.5, 1.0, 0.6, 8), _s("Wembley", -1.5, 2.0, 0.9, 12),
                    _s("Leederville", 2.5, 1.0, 0.8, 12), _s("West Perth", 2.5, -0.5, 0.8, 12)),
    "peel": (_s("Mandurah", -1.5, 0.5, 1.1, 16), _s("Greenfields", 0.5, 1.0, 1.0, 13), _s("Halls Head", -4.5, -1.5, 1.2, 14),
             _s("Falcon", -6.0, -5.0, 1.3, 11), _s("Dudley Park", -1.0, -2.0, 0.9, 11), _s("Meadow Springs", 0.5, 5.0, 1.1, 12),
             _s("Lakelands", 1.0, 8.0, 1.2, 10), _s("Coodanup", -1.0, -3.5, 1.0, 10)),
    "perth-children-s": (_s("Nedlands", 0.0, -1.0, 0.9, 13), _s("Subiaco", 2.5, 1.0, 0.9, 14), _s("Shenton Park", 0.5, 1.0, 0.8, 11),
                         _s("Claremont", -3.0, -1.5, 1.0, 12), _s("Floreat", -1.5, 3.0, 1.0, 12), _s("Wembley", 0.5, 3.0, 0.9, 13),
                         _s("Dalkeith", -0.5, -3.0, 0.9, 10), _s("Crawley", 1.5, -1.5, 0.7, 9)),
    "rockingham": (_s("Rockingham", -1.5, 1.5, 1.1, 15), _s("Cooloongup", 0.5, -0.5, 1.0, 13), _s("Waikiki", -1.5, -3.0, 1.1, 13),
                   _s("Safety Bay", -3.5, -3.5, 1.1, 12), _s("Shoalwater", -4.0, 0.0, 1.0, 10), _s("Baldivis", 6.0, -2.0, 1.5, 16),
                   _s("Port Kennedy", -1.5, -6.5, 1.2, 11), _s("Hillman", 1.0, 1.0, 0.8, 8)),
    "royal-perth": (_s("Perth", -1.5, 0.0, 0.9, 16), _s("East Perth", 1.0, 0.5, 0.8, 12), _s("Northbridge", -1.0, 1.0, 0.7, 11),
                    _s("Highgate", 0.0, 2.0, 0.7, 9), _s("Mount Lawley", 0.5, 3.5, 1.0, 12), _s("Victoria Park", 2.0, -2.5, 1.0, 13),
                    _s("South Perth", -0.5, -2.5, 1.0, 12), _s("West Perth", -3.0, 0.5, 0.9, 10), _s("Maylands", 4.0, 2.0, 1.0, 10)),
    "sir-charles-gairdner": (_s("Nedlands", 0.0, -1.0, 0.9, 14), _s("Subiaco", 2.5, 1.0, 0.9, 14), _s("Wembley", 0.5, 3.0, 0.9, 13),
                             _s("Floreat", -1.5, 3.0, 1.0, 12), _s("Shenton Park", 0.5, 1.0, 0.8, 11), _s("Claremont", -3.0, -1.5, 1.0, 12),
                             _s("Mount Claremont", -2.0, 1.5, 0.9, 10), _s("Daglish", 1.5, 1.5, 0.6, 7)),
    "midland": (_s("Midland", 0.0, 0.0, 1.0, 16), _s("Midvale", 2.0, 0.5, 0.9, 12), _s("Bellevue", 1.5, -1.0, 0.9, 11),
                _s("Woodbridge", -1.0, 0.5, 0.7, 9), _s("Guildford", -3.0, -0.5, 1.0, 12), _s("Swan View", 3.5, -1.5, 1.1, 12),
                _s("Stratton", 2.5, 2.5, 1.0, 11), _s("Viveash", -0.5, 1.5, 0.7, 8)),
}

_snapshot: Optional[feed.FeedSnapshot] = None
_demo_numbers: Optional[tuple[int, int, int]] = None


def snapshot() -> feed.FeedSnapshot:
    global _snapshot
    if _snapshot is None:
        _snapshot = feed.FeedSnapshot.load()
    return _snapshot


def demo_numbers(seed: SeedFile) -> tuple[int, int, int]:
    """The demo ED's own (waiting, in_ed, t4 mean wait) at the start minute: its warm-up week, with Jess (category 4,
    held for the mental health team since 12:40) in the room as the app has her."""
    global _demo_numbers
    if _demo_numbers is None:
        c = SimConfig(seed)
        s = SimState(0, SeededRNG(seed.sim.seed))
        jess_at = START_MINUTE - 110
        while s.now < START_MINUTE:
            if s.now == jess_at:
                lat, lon = network.coordinate(-3.7, 2.0)
                jess = Episode(id=len(s.episodes), name="Jess T.", age=24, sex="F", cohort=Cohort.mh, complaint="Panic attack, anxious",
                               complaintKey="anxiety", ats=4, arrival=s.now, arrivalMode=ArrivalMode.publicTransport,
                               homeLat=lat, homeLon=lon, patience=136, holdFromCall=True, isHero=True)
                s.episodes.append(jess)
                s.waiting.append(jess.id)
            simulator.step(s, c)
        t4 = [s.now - s.episodes[i].arrival for i in s.waiting if s.episodes[i].ats == 4]
        _demo_numbers = (len(s.waiting), len(s.waiting) + len(s.inCare), int(round(sum(t4) / len(t4))) if t4 else 0)
    return _demo_numbers


def demo_hospital(seed: SeedFile) -> Hospital:
    waiting, in_ed, t4 = demo_numbers(seed)
    return Hospital(DEMO_ID, seed.demo_ed.name, "Demo ED", waiting, in_ed, t4, tuple(network.SUBURBS))


def hospitals(seed: SeedFile) -> list[Hospital]:
    """The demo ED first, then every hospital in the snapshot."""
    out = [demo_hospital(seed)]
    for h in snapshot().hospitals:
        id = slug(h.short)
        out.append(Hospital(id, h.name, h.short, h.waiting, h.in_ed, h.t4_avg_wait_min,
                            HOSPITAL_SUBURBS.get(id, tuple(network.SUBURBS))))
    return out


def find(id: str, seed: SeedFile) -> Optional[Hospital]:
    return next((h for h in hospitals(seed) if h.id == id), None)


def source() -> dict:
    s = snapshot()
    return {"takenText": s.taken_text, "takenAt": s.taken_at, "url": s.url,
            "note": ("The published numbers (people waiting, people in the ED, category-4 average wait) are taken as "
                     "the room as it stands at the demo's Saturday 2:30 pm; the page itself was read on "
                     f"{s.taken_text}.")}


# MARK: Rates and the room

def rate_scale(h: Hospital, c: SimConfig, now: int = START_MINUTE) -> float:
    """Little's law: people waiting over their average wait is the rate people are being seen; its ratio to the demo
    ED's service rate at this hour scales the whole week (feed.py does the same for its forecast). A hospital with
    nobody waiting keeps the demo ED's rates."""
    if h.id == DEMO_ID or h.waiting <= 0 or h.t4_avg_wait_min <= 0:
        return 1.0
    return (h.waiting / h.t4_avg_wait_min) / max(1e-6, c.calls_per_minute(now))


def configure(c: SimConfig, h: Hospital, now: int = START_MINUTE) -> float:
    """Points a fresh SimConfig at the hospital: scaled weekly volume (the hour-of-week shape stays) and its suburbs.
    Returns the scale applied."""
    scale = rate_scale(h, c, now)
    c.weekly = c.weekly * scale
    c.suburbs = list(h.suburbs)
    return scale


def _draw_cohort(rng: SeededRNG, c: SimConfig, ats: int) -> Cohort:
    u = rng.uniform()
    mh = c.mhByATS[ats - 1]
    return Cohort.mh if u < mh else (Cohort.p65 if u < mh + c.p65ByATS[ats - 1] else Cohort.other)


def _care_minutes(rng: SeededRNG, c: SimConfig, e: Episode) -> int:
    key = "B" if e.plannedOutcome is Outcome.admitted else ("R3" if e.plannedOutcome is Outcome.leftAtOwnRisk else "D")
    p = c.care.get(key, simulator._Care(2.0, 1.0))
    return int(min(20.0, max(0.3, rng.lognormal(p.median, p.logSD))) * 60)


def build_room(h: Hospital, c: SimConfig, now: int, first_id: int, rng: SeededRNG,
               reserved: tuple[tuple[int, int], ...] = ()) -> tuple[list[Episode], list[Episode]]:
    """The published room: ``waiting − len(reserved)`` people waiting (categories in the proportions of a typical
    waiting room, arrival times spread so the category-4 mean wait is the published one and the other categories
    follow their target ratios) and ``in_ed − waiting`` people in care part-way through a stay from the care-hours
    table. ``reserved`` lists people already in the room, as (category, minutes waited), so the published count and
    the category-4 mean hold with them included. People are drawn exactly as the simulator draws arrivals, with
    homes in the hospital's suburbs."""
    n_wait = max(0, h.waiting - len(reserved))
    n_care = max(0, h.in_ed - h.waiting)
    weights = [0.0 if a == 1 else c.triageMix[a - 1] * max(1.0, c.waitMedianByATS[a - 1]) for a in range(1, 6)]
    t4_target = c.targets[3]
    mean_wait = [h.t4_avg_wait_min * (c.targets[a - 1] / t4_target) for a in range(1, 6)]
    cats = [rng.pick(weights) + 1 for _ in range(n_wait)]
    waiting: list[Episode] = []
    id = first_id
    # Waits spread evenly over [0, 2 × mean] within each category, so each category's mean is its target; a reserved
    # person's wait counts toward their category's mean.
    by_cat: dict[int, list[int]] = {}
    for k, a in enumerate(cats):
        by_cat.setdefault(a, []).append(k)
    waited = [0] * n_wait
    for a, ks in by_cat.items():
        held = [w for ra, w in reserved if ra == a]
        target = (mean_wait[a - 1] * (len(ks) + len(held)) - sum(held)) / len(ks)
        target = max(0.0, target)
        for j, k in enumerate(ks):
            waited[k] = int(round(2.0 * target * (j + 0.5) / len(ks)))
    for k, a in enumerate(cats):
        cohort = _draw_cohort(rng, c, a)
        e = simulator.make_identity(id, cohort, a, now - waited[k], rng, c)
        # Still here after waiting this long: the patience left is a fresh draw on top of the time already waited.
        e.patience = waited[k] + rng.lognormal(c.patienceMedian[a - 1], c.patienceSigma)
        e.etaConsent = rng.chance(0.85)
        e.etaSentAt = e.arrival + 3 if e.etaConsent else None
        waiting.append(e)
        id += 1
    in_care: list[Episode] = []
    for _ in range(n_care):
        a = rng.pick(c.triageMix) + 1
        cohort = _draw_cohort(rng, c, a)
        e = simulator.make_identity(id, cohort, a, now, rng, c)
        if rng.chance(c.leftAtOwnRisk.get(cohort, 0.01)):
            e.plannedOutcome = Outcome.leftAtOwnRisk
        else:
            admit = c.admit.get(cohort, [])
            e.plannedOutcome = Outcome.admitted if rng.chance(admit[a - 1] if a - 1 < len(admit) else 0.3) else Outcome.discharged
        total = _care_minutes(rng, c, e)
        elapsed = int(rng.uniform() * total)
        w = 0 if a == 1 else int(rng.uniform() * 2.0 * mean_wait[a - 1])
        e.calledAt = now - elapsed
        e.arrival = e.calledAt - w
        e.careEnds = now + max(1, total - elapsed)
        e.stage = Stage.inCare
        e.patience = float("inf")
        e.etaConsent = rng.chance(0.85)
        e.etaSentAt = e.arrival + 3 if e.etaConsent else None
        in_care.append(e)
        id += 1
    return waiting, in_care


def apply_room(s: SimState, h: Hospital, c: SimConfig, now: int) -> None:
    """Replaces the warm-up week's room at ``now`` with the published one: closed episodes keep their history (renumbered),
    the demo's own people (Jess, Liam) stay, everyone else waiting or in care gives way to the generated room."""
    keep = [e for e in s.episodes if e.outcome is not None or e.isHero]
    for i, e in enumerate(keep):
        e.id = i
    s.episodes = keep
    s.waiting = [e.id for e in keep if e.stage is Stage.waiting]
    s.inCare = [e.id for e in keep if e.stage is Stage.inCare]
    s.events = [SimEvent(ev.kind, next(e.id for e in keep if e.isHero and e.name == "Liam K.")) for ev in s.events
                if ev.kind == "redirected"] if s.events else []
    rng = SeededRNG(feed.fnv(h.name))
    reserved = tuple((s.episodes[i].ats, now - s.episodes[i].arrival) for i in s.waiting)
    waiting, in_care = build_room(h, c, now, len(s.episodes), rng, reserved=reserved)
    for e in waiting:
        s.episodes.append(e)
        s.waiting.append(e.id)
    for e in in_care:
        s.episodes.append(e)
        s.inCare.append(e.id)


# MARK: The measured effect

def _redirect_target(e: Episode, now: int) -> Optional[str]:
    """Where the redirect gate would send a new category-4/5 arrival right now, or None when they stay."""
    if e.ats < 4 or rightdoor.blockers(e):
        return None
    places = rightdoor.plan(e, e.arrivalMode.travel, now, Purpose.redirectNow).places
    return places[0].service.name if places else None


def _fork(s: SimState, seed: int) -> SimState:
    f = SimState(now=s.now, rng=SeededRNG(seed), episodes=[copy.copy(e) for e in s.episodes],
                 waiting=list(s.waiting), inCare=list(s.inCare), events=[])
    return f


def _run_arm(s0: SimState, c: SimConfig, seed: int, horizon: int, redirect: bool) -> dict:
    s = _fork(s0, seed)
    first_new = len(s.episodes)
    end = s.now + horizon
    redirected = 0
    while s.now < end:
        before = len(s.episodes)
        simulator.step(s, c)
        if redirect:
            for e in s.episodes[before:]:
                if e.stage is not Stage.waiting:
                    continue
                target = _redirect_target(e, s.now)
                if target is None:
                    continue
                s.waiting.remove(e.id)
                e.stage = Stage.closed
                e.outcome = Outcome.redirected
                e.outcomeAt = s.now
                e.redirectService = target
                s.events.append(SimEvent("redirected", e.id))
                redirected += 1
    called = [e for e in s.episodes if e.ats == 4 and e.calledAt is not None and s0.now <= e.calledAt < end]
    t4 = [e.calledAt - e.arrival for e in called]
    t4_new = [e.calledAt - e.arrival for e in called if e.id >= first_new]
    return {"t4": sum(t4) / len(t4) if t4 else None, "t4n": len(t4),
            "t4new": sum(t4_new) / len(t4_new) if t4_new else None, "waiting": len(s.waiting),
            "arrivals": len(s.episodes) - first_new, "redirected": redirected}


def measure_effect(m: "AppModel", horizon: int = HORIZON_MINUTES, replicas: int = REPLICAS) -> dict:
    """Runs the current hospital forward from the state as it stands, ``replicas`` times with the same seeds, with and
    without the redirect gate on new category-4/5 arrivals, and reports what was measured."""
    base = m.sim
    seeds = [((feed.fnv(m.hospital.name) + 101 * (r + 1)) ^ (base.now & 0xFFFF)) & ((1 << 64) - 1) for r in range(replicas)]
    arms = {"baseline": [_run_arm(base, m.config, sd, horizon, False) for sd in seeds],
            "withRedirects": [_run_arm(base, m.config, sd, horizon, True) for sd in seeds]}

    def mean(xs: list[Optional[float]]) -> Optional[float]:
        ys = [x for x in xs if x is not None]
        return round(sum(ys) / len(ys), 1) if ys else None

    red = arms["withRedirects"]
    arrivals = sum(r["arrivals"] for r in red)
    return {
        "publishedT4AvgWaitMin": m.hospital.t4_avg_wait_min,
        "simulatedT4WaitMin": {"baseline": mean([r["t4"] for r in arms["baseline"]]),
                               "withRedirects": mean([r["t4"] for r in red])},
        # The same for category-4 people who arrived within the horizon: the two arms share that arrival stream, so
        # this is the gate's effect without the backlog's selection (the backlog is called deeper when the room clears).
        "newArrivalT4WaitMin": {"baseline": mean([r["t4new"] for r in arms["baseline"]]),
                                "withRedirects": mean([r["t4new"] for r in red])},
        "redirectedShare": round(sum(r["redirected"] for r in red) / arrivals, 3) if arrivals else 0.0,
        "waitingNow": {"baseline": mean([r["waiting"] for r in arms["baseline"]]),
                       "withRedirects": mean([r["waiting"] for r in red])},
        "horizonMinutes": horizon, "replicas": replicas, "takenText": snapshot().taken_text,
        "method": (f"The room as it stands run forward {horizon // 60} hours {replicas} times on the same seeds, once as "
                   "is and once sending new category 4–5 arrivals that pass the redirect gate to an open place within "
                   "reach; the category-4 wait is the mean wait of category-4 patients called within the horizon, "
                   "and the new-arrival wait the same for those who arrived within it."),
    }
