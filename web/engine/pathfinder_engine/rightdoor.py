"""The right-door model: a ride-share style ring search over hexagons, then travel time, hours and fit.

The metro is cut into hexagons, and the search spreads
outward from the person's home hexagon ring by ring until enough candidate services are found. Only then does it
cost each candidate: travel time by the way the person gets around (Dijkstra over the hexagon lattice, with a
separate "on the bus" layer for public transport), opening hours and fit. Roads, bus corridors and places are
invented for the demo; the algorithm is the one a real deployment would run. The binary heap keeps a fixed order, so
ties settle the same way on every run.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple, Optional

from . import hexgrid, network
from .clock import WEEK
from .domain import ArrivalMode, Cohort, Episode, TravelMode
from .hexgrid import Hex
from .network import CareService, Kind

_INF = float("inf")


class Node(NamedTuple):
    hex: Hex
    onBus: bool


@dataclass
class TravelField:
    mode: TravelMode
    home: Hex
    minutes: dict[Hex, float] = field(default_factory=dict)  # best time to reach each hexagon
    order: list[Hex] = field(default_factory=list)  # hexagons in the order the model settled them: rising minutes
    prev: dict[Node, Node] = field(default_factory=dict)

    @property
    def max_minutes(self) -> float:
        return self.minutes.get(self.order[-1], 0.0) if self.order else 0.0

    def route(self, h: Hex) -> list[Hex]:
        """The hexagons travelled through to reach ``h``, home first."""
        path: list[Hex] = []
        node: Optional[Node] = Node(h, False)
        guard = 0
        while node is not None and guard < 10_000:
            if not path or path[-1] != node.hex:
                path.append(node.hex)
            node = self.prev.get(node)
            guard += 1
        path.reverse()
        return path


class MinHeap:
    """A binary heap of (minutes, node) pairs, smallest first; equal costs pop in insertion order."""

    def __init__(self) -> None:
        self.items: list[tuple[float, Node]] = []

    def push(self, cost: float, node: Node) -> None:
        items = self.items
        items.append((cost, node))
        i = len(items) - 1
        while i > 0:
            p = (i - 1) // 2
            if items[p][0] <= items[i][0]:
                break
            items[p], items[i] = items[i], items[p]
            i = p

    def pop(self) -> Optional[tuple[float, Node]]:
        items = self.items
        if not items:
            return None
        top = items[0]
        last = items.pop()
        if items:
            items[0] = last
            i = 0
            n = len(items)
            while True:
                l = 2 * i + 1
                r = l + 1
                m = i
                if l < n and items[l][0] < items[m][0]:
                    m = l
                if r < n and items[r][0] < items[m][0]:
                    m = r
                if m == i:
                    break
                items[m], items[i] = items[i], items[m]
                i = m
        return top


# Minutes per hexagon step (866 m).
WALK_PER_HEX = 10.8  # 4.8 km/h
CAR_ARTERIAL = 1.3  # about 40 km/h along an arterial road
CAR_LOCAL = 2.2  # about 24 km/h on local streets
BUS_PER_HEX = 2.4  # about 22 km/h including stops
CAR_START = 2.0  # getting to the car
TAU = 30.0  # minutes: the travel-time scale in the score

MIN_RINGS = 3
MAX_RINGS = 13


def bus_wait(t: int) -> float:
    """Average wait for a bus: half the headway, which depends on the day and hour."""
    m = ((t % WEEK) + WEEK) % WEEK
    day, hour = m // 1440, (m % 1440) // 60
    if day < 5 and 7 <= hour < 19:
        return 5
    if day == 5 and 8 <= hour < 19:
        return 7.5
    return 15


# MARK: The ring search

@dataclass(frozen=True)
class Need:
    """What counts as enough candidates for this person: each group must be found this many times."""

    kinds: tuple[Kind, ...]
    count: int

    @property
    def label(self) -> str:
        return " or ".join(k.label for k in self.kinds)


def need_for(e: Episode) -> list[Need]:
    need = [Need((Kind.ed,), 1), Need((Kind.gp,), 2)]
    if e.cohort is Cohort.mh:
        need.append(Need((Kind.mentalHealth, Kind.safeHaven), 1))
    elif not network.ed_is_right_door(e):
        need.append(Need((Kind.urgentCare,), 1))
        need.append(Need((Kind.pharmacy,), 1))
    return need


@dataclass(frozen=True)
class Ring:
    k: int
    hexes: list[Hex]
    found: list[CareService]


@dataclass(frozen=True)
class Search:
    home: Hex
    rings: list[Ring]
    need: list[Need]
    complete: bool  # every need met before the ring limit

    @property
    def candidates(self) -> list[CareService]:
        return [s for r in self.rings for s in r.found]

    @property
    def hex_count(self) -> int:
        return sum(len(r.hexes) for r in self.rings)

    @property
    def k(self) -> int:
        return len(self.rings) - 1

    def ring_of(self, s: CareService) -> Optional[int]:
        return next((r.k for r in self.rings if s in r.found), None)

    def to_dict(self) -> dict:
        return {"rings": [{"k": r.k, "hexes": [h.to_dict() for h in r.hexes], "found": [s.id for s in r.found]}
                          for r in self.rings],
                "hexCount": self.hex_count, "needs": [n.label for n in self.need], "complete": self.complete, "k": self.k}


def _services_by_hex() -> dict[Hex, list[CareService]]:
    d: dict[Hex, list[CareService]] = {}
    for s in network.SERVICES:
        h = s.hex
        if h is not None:
            d.setdefault(h, []).append(s)
    return d


SERVICES_BY_HEX: dict[Hex, list[CareService]] = _services_by_hex()


def search(home: Hex, e: Episode) -> Search:
    """Expand k-rings from the home hexagon until every need is met (or the limit), keeping only services that suit
    the person. This is the ride-share search pattern: cheap, local, and it stops as soon as it has enough."""
    need = need_for(e)
    have: dict[str, int] = {}
    rings: list[Ring] = []
    complete = False
    for k in range(MAX_RINGS + 1):
        hexes = hexgrid.ring(home, k)
        found = [s for h in hexes for s in SERVICES_BY_HEX.get(h, []) if fit(s, e) > 0]
        rings.append(Ring(k, hexes, found))
        for s in found:
            have[s.kind.value] = have.get(s.kind.value, 0) + 1
        complete = all(sum(have.get(kind.value, 0) for kind in n.kinds) >= n.count for n in need)
        if complete and k >= MIN_RINGS:
            break
    return Search(home=home, rings=rings, need=need, complete=complete)


# MARK: Travel time

def travel_field(home_lat: float, home_lon: float, mode: TravelMode, t: int, radius: int = MAX_RINGS) -> TravelField:
    """Travel minutes from home to every hexagon within ``radius``, by ``mode``, starting at simulated minute ``t``."""
    px, py = network.xy(home_lat, home_lon)
    h0 = hexgrid.hex_at(px, py)
    f = TravelField(mode=mode, home=h0)
    best: dict[Node, float] = {}
    settled: set[Node] = set()
    heap = MinHeap()
    start = Node(h0, False)
    best[start] = 0.0
    heap.push(0.0, start)
    wait = bus_wait(t)
    corridor = network.CORRIDOR_HEXES

    while True:
        item = heap.pop()
        if item is None:
            break
        cost, node = item
        if node in settled:
            continue
        settled.add(node)
        if node.hex not in f.minutes:
            f.minutes[node.hex] = cost
            f.order.append(node.hex)

        def relax(n: Node, c: float) -> None:
            if c < best.get(n, _INF):
                best[n] = c
                f.prev[n] = node
                heap.push(c, n)

        on_corridor = node.hex in corridor
        if node.onBus:
            relax(Node(node.hex, False), cost)  # get off, free
            for n in hexgrid.neighbors(node.hex):
                if n in corridor and hexgrid.distance(n, h0) <= radius:
                    relax(Node(n, True), cost + BUS_PER_HEX)  # ride along the corridor
        else:
            if mode is TravelMode.bus and on_corridor:
                relax(Node(node.hex, True), cost + wait)  # board: wait for the bus
            for n in hexgrid.neighbors(node.hex):
                if hexgrid.distance(n, h0) <= radius:
                    if mode is TravelMode.car:
                        c = CAR_ARTERIAL if on_corridor and n in corridor else CAR_LOCAL
                    else:
                        c = WALK_PER_HEX
                    relax(Node(n, False), cost + c)
    return f


_MINOR = frozenset(["limb", "laceration", "fever", "sore_throat", "rash", "eye", "vomiting", "back", "abdo",
                    "urinary", "headache", "dizzy", "fall"])
_PHARMACY = frozenset(["rash", "sore_throat", "fever", "headache", "vomiting"])


def fit(s: CareService, e: Episode) -> float:
    """How well a service suits the person: 0 hides it, 1 is a natural fit. Transparent rules, not a learned model."""
    mh = e.cohort is Cohort.mh
    major = network.ed_is_right_door(e)  # the ED stays the right door; only follow-up services fit
    k = s.kind
    if k is Kind.ed:
        return 1.0 if major else (0.8 if e.ats <= 3 else 0.45)
    if k is Kind.urgentCare:
        return 0.0 if mh or major else (1.0 if e.complaintKey in _MINOR and e.ats >= 3 else 0.6)
    if k is Kind.gp:
        return 0.75 if mh else (1.0 if e.ats >= 4 else 0.8)
    if k is Kind.pharmacy:
        return 0.0 if mh or major else (0.7 if e.complaintKey in _PHARMACY and e.ats >= 4 else 0.25)
    if k in (Kind.mentalHealth, Kind.safeHaven):
        return 1.0 if mh else 0.0
    if k is Kind.virtualED:
        return 0.4 if mh else (0.9 if e.cohort is Cohort.p65 else 0.7)
    if k is Kind.phone:
        return 0.5 if e.cohort in s.suits else 0.0
    if k is Kind.homeCare:
        return 0.7 if e.cohort is Cohort.p65 else 0.0
    return 0.0


@dataclass(frozen=True)
class Option:
    service: CareService
    minutes: Optional[float]  # door to door; None for services that need no travel
    opensIn: int  # minutes until open; 0 when open now
    fit: float
    score: float
    route: list[Hex]

    @property
    def id(self) -> str:
        return self.service.id

    @property
    def open(self) -> bool:
        return self.opensIn == 0

    @property
    def open_factor(self) -> float:
        return open_factor(self.opensIn, self.service.kind.bookable)

    @property
    def travel_factor(self) -> float:
        return travel_factor(self.minutes)

    def to_dict(self, mode: TravelMode, t: int, rank: int, pinned: bool = False) -> dict:
        return {"service": self.service.to_dict(), "minutes": self.minutes, "minutesText": minutes_text(self.minutes, mode),
                "opensIn": self.opensIn, "openText": open_text(self.opensIn, t), "fit": self.fit, "score": self.score,
                "route": [h.to_dict() for h in self.route], "pinned000": pinned, "rank": rank}


def open_factor(opens_in: int, bookable: bool) -> float:
    """Open now counts fully. A walk-in place that is closed counts less the longer it stays closed; a bookable
    service (a GP, the community team) is booked for when it opens, so being closed now matters less."""
    if opens_in == 0:
        return 1.0
    if bookable:
        return 0.8 if opens_in <= 2 * 1440 else 0.5
    return 0.6 if opens_in <= 180 else 0.3


def travel_factor(minutes: Optional[float]) -> float:
    return math.exp(-minutes / TAU) if minutes is not None else 0.8


class Purpose(str, Enum):
    """What the plan is for: sending someone elsewhere from triage right now, or the right door next time."""

    redirectNow = "redirectNow"
    nextTime = "nextTime"

    @property
    def label(self) -> str:
        return "Redirect now" if self is Purpose.redirectNow else "Next time"


def max_redirect_minutes(mode: TravelMode) -> float:
    """The longest trip a redirect from triage may ask of someone, by the way they travel."""
    return 30 if mode is TravelMode.walk else 45


def blockers(e: Episode) -> list[str]:
    """Why a person cannot be redirected from triage right now. Conservative on purpose: category 4 or 5 only,
    nothing time-critical or high risk, and not brought in by ambulance or police. The nurse can always overrule."""
    out: list[str] = []
    if e.complaintKey in network.TIME_CRITICAL:
        out.append(f"{e.problem} can be time-critical")
    elif e.complaintKey in network.TRAUMA and e.ats <= 3:
        out.append(f"An injury at category {e.ats} stays with the ED")
    if e.ats <= 3:
        out.append(f"Triage category {e.ats} needs the ED")
    if e.arrivalMode in (ArrivalMode.ambulance, ArrivalMode.police):
        out.append(f"Brought in {e.arrivalMode.short}: stays for assessment")
    if any(f.is_high_risk for f in e.flags):
        out.append("High-risk mental health flags: stays with the mental health team")
    return out


@dataclass
class Result:
    search: Search
    field: TravelField
    mode: TravelMode
    purpose: Purpose
    options: list[Option]
    blockers: list[str]  # redirect now: why the person stays in the ED (empty when a redirect is possible)
    edFirst: bool  # next time: the ED stays the right door, so it is pinned first

    @property
    def places(self) -> list[Option]:
        return [o for o in self.options if o.minutes is not None]

    @property
    def remote(self) -> list[Option]:
        return [o for o in self.options if o.minutes is None]


def plan(e: Episode, mode: TravelMode, t: int, purpose: Purpose = Purpose.nextTime) -> Result:
    """The ranked right doors for a person, by the way they travel, at simulated minute ``t``: search, then cost,
    then score. For a redirect now only places open now and within reach count, and only if nothing blocks the
    redirect."""
    px, py = network.xy(e.homeLat, e.homeLon)
    srch = search(hexgrid.hex_at(px, py), e)
    fld = travel_field(e.homeLat, e.homeLon, mode, t, radius=srch.k + 3)
    candidates = {s.id for s in srch.candidates}
    blocks = blockers(e) if purpose is Purpose.redirectNow else []
    options: list[Option] = []
    for s in network.SERVICES:
        f = fit(s, e)
        if not f > 0:
            continue
        if purpose is Purpose.redirectNow:
            if s.kind is Kind.ed or s.kind is Kind.homeCare or not s.is_open(t):
                continue  # already in an ED; open now only
        minutes: Optional[float] = None
        route: list[Hex] = []
        h = s.hex
        if h is not None:
            if s.id not in candidates or h not in fld.minutes:
                continue  # not found by the search
            minutes = fld.minutes[h] + (CAR_START + s.parking_minutes if mode is TravelMode.car else 0)
            if purpose is Purpose.redirectNow and minutes > max_redirect_minutes(mode):
                continue
            route = fld.route(h)
        opens_in = s.opens_in(t)
        options.append(Option(service=s, minutes=minutes, opensIn=opens_in, fit=f,
                              score=f * open_factor(opens_in, s.kind.bookable) * travel_factor(minutes), route=route))
    options.sort(key=lambda o: -o.score)
    ed_first = purpose is Purpose.nextTime and network.ed_is_right_door(e)
    if ed_first:
        i = next((j for j, o in enumerate(options) if o.service.kind is Kind.ed), None)
        if i is not None and i > 0:
            options.insert(0, options.pop(i))
    return Result(search=srch, field=fld, mode=mode, purpose=purpose, options=options if not blocks else [],
                  blockers=blocks, edFirst=ed_first)


# MARK: Text

def minutes_text(m: Optional[float], mode: TravelMode) -> str:
    if m is None:
        return "No travel"
    return f"{int(math.floor(m + 0.5))} min {mode.short}"


def open_text(opens_in: int, t: int) -> str:
    """"Open now", "Opens 6 pm", "Opens tomorrow 8 am", "Opens Mon 8 am"."""
    if opens_in == 0:
        return "Open now"
    now = ((t % WEEK) + WEEK) % WEEK
    at = (now + opens_in) % WEEK
    day_now, day_at = now // 1440, at // 1440
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    h, mi = (at % 1440) // 60, at % 60
    hour12 = 12 if h % 12 == 0 else h % 12
    ampm = "am" if h < 12 else "pm"
    clock = f"{hour12} {ampm}" if mi == 0 else f"{hour12}:{mi:02d} {ampm}"
    if day_at == day_now and opens_in < 1440:
        return f"Opens {clock}"
    if (day_at - day_now + 7) % 7 == 1:
        return f"Opens tomorrow {clock}"
    return f"Opens {names[day_at]} {clock}"
