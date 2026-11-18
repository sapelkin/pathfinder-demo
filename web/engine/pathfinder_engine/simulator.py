"""One-minute steps of the demo waiting room, and the fictional people who arrive in it.

``SimConfig``, ``SimState``, ``SimEngine`` and ``Identity``. The same algorithm as ``simulate`` in
``tools/waitroom_sim.py``, which calibrated the seed; the random draws happen in a fixed order, so the demo week on
seed 62 is the same on every run.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, NamedTuple, Optional

from . import clock, network
from .domain import ArrivalMode, ClinicalFlag, Cohort, Episode, Outcome, Stage
from .rng import SeededRNG
from .seed import SeedFile

_INF = float("inf")


class _Care(NamedTuple):
    median: float
    logSD: float


class _Days(NamedTuple):
    p25: float
    p50: float
    p75: float


class _Flags(NamedTuple):
    selfHarm: float
    drugs: float
    police: float
    ambulance: float


class _Arrival(NamedTuple):
    car: float
    bus: float
    taxi: float
    ambulance: float
    police: float


class _Band(NamedTuple):
    lo: int
    hi: int
    weight: float


class _Complaint(NamedTuple):
    key: str
    label: str
    lo: int
    hi: int


class SimConfig:
    """Parameters for the demo waiting room, all read from the seed."""

    _BAND_RANGES = {"18-24": (18, 24), "25-44": (25, 44), "45-64": (45, 64), "65-74": (65, 74), "75-84": (75, 84),
                    "85+": (85, 96)}

    def __init__(self, seed: SeedFile):
        a = seed.aggregates
        self.weekly: float = seed.demo_ed.weekly_presentations
        self.shape: list[float] = list(seed.arrival_shape)
        self.triageMix: list[float] = list(a.triage_mix)
        self.referredByATS: list[float] = list(a.referred_at_triage_by_ats)
        self.targets: list[float] = list(seed.sim.priority_targets)
        self.patienceMedian: list[float] = list(seed.sim.patience_median_min)
        self.patienceSigma: float = seed.sim.patience_sigma
        self.slack: float = seed.sim.service_slack
        self.lag: int = seed.sim.service_lag_hours
        by_ats = sorted(a.cohort_by_ats, key=lambda r: r.ats)
        self.mhByATS: list[float] = [r.mh if r.mh is not None else 0.06 for r in by_ats]
        self.waitMedianByATS: list[float] = [x if x is not None else 60 for x in seed.sim.calibration.median_wait_by_ats]
        self.p65ByATS: list[float] = [r.p65 if r.p65 is not None else 0.2 for r in by_ats]

        self.admit: dict[Cohort, list[float]] = {}
        self.leftAtOwnRisk: dict[Cohort, float] = {}
        self.priorBands: dict[Cohort, list[float]] = {}
        self.daysSince: dict[Cohort, _Days] = {}
        self.flags: dict[Cohort, _Flags] = {}
        self.arrival: dict[Cohort, _Arrival] = {}
        self.ageBands: dict[Cohort, list[_Band]] = {}
        for c in Cohort:
            key = c.value
            self.admit[c] = [x if x is not None else 0.3 for x in a.admit_by_cohort_ats.get(key, [])]
            laor = a.left_at_own_risk_by_cohort.get(key)
            self.leftAtOwnRisk[c] = laor if laor is not None else 0.01
            p = a.prior_visits_by_cohort.get(key, {})
            self.priorBands[c] = [float(p.get(b) or 0) for b in ["0", "1", "2-3", "4+"]]
            d = a.days_since_last_visit_by_cohort.get(key)
            self.daysSince[c] = _Days(d.p25 if d and d.p25 is not None else 10, d.p50 if d and d.p50 is not None else 35,
                                      d.p75 if d and d.p75 is not None else 80)
            f = a.flags_by_cohort.get(key)
            self.flags[c] = _Flags(_or(f.self_harm if f else None, 0), _or(f.drugs_alcohol if f else None, 0),
                                   _or(f.police if f else None, 0), _or(f.ambulance if f else None, 0.2))
            m = (a.arrival_mode_by_cohort or {}).get(key)
            self.arrival[c] = _Arrival(
                _or(m.private if m else None, 0.75), _or(m.public if m else None, 0.03), _or(m.taxi if m else None, 0),
                _or(m.ambulance if m else None, _or(f.ambulance if f else None, 0.2)),
                _or(m.police if m else None, _or(f.police if f else None, 0.01)))
            bands = a.age_bands_by_cohort.get(key, {})
            out = []
            for label, n in bands.items():
                r = self._BAND_RANGES.get(label)
                if n is None or r is None:
                    continue
                out.append(_Band(r[0], r[1], float(n)))
            self.ageBands[c] = sorted(out, key=lambda b: b.lo)
        self.care: dict[str, _Care] = {k: _Care(v.median, v.log_sd) for k, v in a.care_hours.items()}
        self.suburbs: list[network.Suburb] = list(network.SUBURBS)  # metro mode swaps in the hospital's table

    def arrivals_per_minute(self, t: int) -> float:
        return self.weekly * self.shape[clock.hour_of_week(t)] / 60.0

    def calls_per_minute(self, t: int) -> float:
        return self.slack * self.weekly * self.shape[(clock.hour_of_week(t) - self.lag + 168) % 168] / 60.0


def _or(x: Optional[float], default: float) -> float:
    return default if x is None else x


class SimEvent(NamedTuple):
    kind: str  # "left" | "finished" | "redirected"
    id: int


@dataclass
class SimState:
    now: int
    rng: SeededRNG
    episodes: list[Episode] = field(default_factory=list)
    waiting: list[int] = field(default_factory=list)
    inCare: list[int] = field(default_factory=list)
    events: list[SimEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"now": self.now, "rng": self.rng.state, "episodes": [e.to_dict() for e in self.episodes],
                "waiting": list(self.waiting), "inCare": list(self.inCare),
                "events": [[ev.kind, ev.id] for ev in self.events]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SimState":
        rng = SeededRNG(1)
        rng.state = int(d["rng"])
        return cls(now=int(d["now"]), rng=rng, episodes=[Episode.from_dict(e) for e in d["episodes"]],
                   waiting=[int(x) for x in d["waiting"]], inCare=[int(x) for x in d["inCare"]],
                   events=[SimEvent(k, int(i)) for k, i in d.get("events", [])])


# --- Fictional people -----------------------------------------------------------------------------------------------

FIRST_NAMES = ["Alex", "Sam", "Priya", "Jordan", "Mia", "Noah", "Chloe", "Liam", "Ava", "Ethan", "Zara",
               "Oliver", "Grace", "Lucas", "Isla", "Mateo", "Ruby", "Hamish", "Leila", "Tom", "Anika",
               "Josh", "Ella", "Kai", "Maya", "Ben", "Hana", "Finn", "Nora", "Jack", "Sofia", "Aaron",
               "Tahlia", "Declan", "Imogen", "Ravi", "Lena", "Callum", "Jade", "Omar", "Beth", "Nikhil"]
OLDER_NAMES = ["Margaret", "Robert", "Dorothy", "Kevin", "Joan", "Geoff", "Patricia", "Brian", "Shirley",
               "Graham", "Barbara", "Neville", "Judith", "Colin", "Maureen", "Trevor", "Helen", "Ian",
               "Beverley", "Keith", "Lorraine", "Warren", "Elaine", "Russell"]
INITIALS = list("ABCDEFGHJKLMNPRSTVW")

COMPLAINTS: dict[Cohort, list[_Complaint]] = {
    Cohort.mh: [_Complaint("suicidal", "Suicidal thoughts", 2, 3), _Complaint("self_harm", "Self-harm", 2, 3),
                _Complaint("anxiety", "Anxiety, panic", 3, 5), _Complaint("psychosis", "Hearing voices, paranoia", 2, 4),
                _Complaint("agitation", "Agitation", 1, 3), _Complaint("intox", "Intoxication", 2, 4),
                _Complaint("low_mood", "Low mood", 3, 5), _Complaint("crisis", "Situational crisis", 3, 5)],
    Cohort.p65: [_Complaint("fall", "Fall", 2, 4), _Complaint("sob", "Shortness of breath", 1, 3),
                 _Complaint("chest_pain", "Chest pain", 2, 3), _Complaint("confusion", "New confusion", 2, 3),
                 _Complaint("weak", "Weakness, unwell", 3, 4), _Complaint("abdo", "Abdominal pain", 2, 4),
                 _Complaint("dizzy", "Dizziness", 3, 4), _Complaint("limb", "Limb injury", 3, 5),
                 _Complaint("urinary", "Urinary symptoms", 4, 5), _Complaint("fever", "Fever", 2, 4)],
    Cohort.other: [_Complaint("abdo", "Abdominal pain", 2, 4), _Complaint("chest_pain", "Chest pain", 2, 3),
                   _Complaint("limb", "Limb injury", 3, 5), _Complaint("laceration", "Laceration", 4, 5),
                   _Complaint("back", "Back pain", 3, 5), _Complaint("fever", "Fever", 2, 4),
                   _Complaint("headache", "Headache", 2, 4), _Complaint("vomiting", "Vomiting, diarrhoea", 3, 5),
                   _Complaint("sore_throat", "Sore throat", 4, 5), _Complaint("rash", "Rash", 4, 5),
                   _Complaint("sob", "Shortness of breath", 1, 3), _Complaint("eye", "Eye problem", 2, 5),
                   _Complaint("allergy", "Allergic reaction", 1, 4), _Complaint("dizzy", "Dizziness", 3, 4)],
}
_COMPLAINTS_BY_ATS: dict[tuple[Cohort, int], list[_Complaint]] = {
    (c, a): [x for x in COMPLAINTS[c] if x.lo <= a <= x.hi] for c in Cohort for a in range(1, 6)
}
_UNWELL = _Complaint("unwell", "Unwell", 1, 5)


def make_identity(id: int, cohort: Cohort, ats: int, t: int, rng: SeededRNG, c: SimConfig) -> Episode:
    """A fictional person: names are invented; ages, history and flags follow the cohort's aggregate distributions."""
    bands = c.ageBands.get(cohort) or [_Band(25, 60, 1)]
    band = bands[rng.pick([b.weight for b in bands])]
    age = rng.int(band.lo, band.hi)
    first = rng.element(OLDER_NAMES) if age >= 65 else rng.element(FIRST_NAMES)
    name = f"{first} {rng.element(INITIALS)}."
    options = _COMPLAINTS_BY_ATS[(cohort, ats)]
    complaint = _UNWELL if not options else rng.element(options)

    prior_band = rng.pick(c.priorBands.get(cohort) or [1, 1, 1, 1])
    if prior_band == 0:
        prior = 0
    elif prior_band == 1:
        prior = 1
    elif prior_band == 2:
        prior = rng.int(2, 3)
    else:
        prior = 4 + min(8, int(-3.0 * math.log(max(rng.uniform(), 1e-9))))
    days: Optional[int] = None
    q = c.daysSince.get(cohort)
    if prior > 0 and q is not None:
        u = rng.uniform()
        if u < 0.25:
            lo, hi = 1.0, q.p25
        elif u < 0.5:
            lo, hi = q.p25, q.p50
        elif u < 0.75:
            lo, hi = q.p50, q.p75
        else:
            lo, hi = q.p75, q.p75 * 2.5
        days = max(1, int(lo + (hi - lo) * rng.uniform()))
    flags: set[ClinicalFlag] = set()
    f = c.flags.get(cohort) or _Flags(0, 0, 0, 0.2)
    if complaint.key == "suicidal":
        flags.add(ClinicalFlag.suicidalIdeation)
    if complaint.key == "self_harm" or rng.chance(f.selfHarm * 0.5):
        flags.add(ClinicalFlag.selfHarm)
    if complaint.key == "psychosis":
        flags.add(ClinicalFlag.psychosis)
    if complaint.key == "agitation":
        flags.add(ClinicalFlag.agitation)
    if complaint.key == "intox" or rng.chance(f.drugs):
        flags.add(ClinicalFlag.drugsAlcohol)
    # Mode of arrival follows the cohort's shares in the data; one in ten private-transport arrivals is assumed
    # to have walked in, which the data does not distinguish. The home is drawn from the demo metro's suburbs.
    m = c.arrival.get(cohort) or _Arrival(0.75, 0.03, 0, 0.2, 0.02)
    u = rng.uniform() * (m.car + m.bus + m.taxi + m.ambulance + m.police)
    if u < m.police:
        mode = ArrivalMode.police
    elif u < m.police + m.ambulance:
        mode = ArrivalMode.ambulance
    elif u < m.police + m.ambulance + m.bus:
        mode = ArrivalMode.publicTransport
    elif u < m.police + m.ambulance + m.bus + m.taxi:
        mode = ArrivalMode.taxi
    else:
        mode = ArrivalMode.walked if rng.chance(0.1) else ArrivalMode.car
    lat, lon, suburb = network.home(rng, c.suburbs)
    sex = "F" if rng.chance(0.5) else "M"
    prior_dnw = prior > 0 and rng.chance(0.08)
    return Episode(id=id, name=name, age=age, sex=sex, cohort=cohort, complaint=complaint.label,
                   complaintKey=complaint.key, ats=ats, arrival=t, arrivalMode=mode, priorVisits=prior,
                   daysSinceLast=days, priorDNW=prior_dnw, flags=flags, homeLat=lat, homeLon=lon, homeSuburb=suburb)


# --- The engine -----------------------------------------------------------------------------------------------------

def priority(e: Episode, now: int, c: SimConfig) -> float:
    """The patient waiting longest relative to their category's target is called first."""
    return (now - e.arrival) / c.targets[e.ats - 1]


def next_to_call(s: SimState, c: SimConfig) -> Optional[int]:
    best: Optional[int] = None
    best_score = -_INF
    best_ats = 9
    now = s.now
    episodes = s.episodes
    targets = c.targets
    for id in s.waiting:
        e = episodes[id]
        if e.holdFromCall:
            continue
        score = (now - e.arrival) / targets[e.ats - 1]
        if score > best_score or (score == best_score and e.ats < best_ats):
            best = id
            best_score = score
            best_ats = e.ats
    return best


def call(s: SimState, c: SimConfig, id: int) -> None:
    s.waiting.remove(id)
    e = s.episodes[id]
    e.stage = Stage.inCare
    e.calledAt = s.now
    if e.plannedOutcome is None:
        if s.rng.chance(c.leftAtOwnRisk.get(e.cohort, 0.01)):
            e.plannedOutcome = Outcome.leftAtOwnRisk
        else:
            admit = c.admit.get(e.cohort, [])
            p_admit = admit[e.ats - 1] if 0 <= e.ats - 1 < len(admit) else 0.3
            e.plannedOutcome = Outcome.admitted if s.rng.chance(p_admit) else Outcome.discharged
    if e.scriptedCareMinutes is not None:
        e.careEnds = s.now + e.scriptedCareMinutes
    else:
        key = "B" if e.plannedOutcome is Outcome.admitted else ("R3" if e.plannedOutcome is Outcome.leftAtOwnRisk else "D")
        p = c.care.get(key, _Care(2.0, 1.0))
        hours = min(20.0, max(0.3, s.rng.lognormal(p.median, p.logSD)))
        e.careEnds = s.now + int(hours * 60)
    s.inCare.append(id)


_LEAVE_REASONS = ["Wait too long", "Felt better", "Work or family", "Transport home"]


def leave(s: SimState, id: int) -> None:
    s.waiting.remove(id)
    e = s.episodes[id]
    e.stage = Stage.closed
    e.outcome = Outcome.didNotWait
    e.outcomeAt = s.now
    if e.leaveReason is None and not e.isHero and s.rng.chance(0.3):
        e.leaveReason = s.rng.element(_LEAVE_REASONS)
    s.events.append(SimEvent("left", id))


def finish(s: SimState, id: int) -> None:
    s.inCare.remove(id)
    e = s.episodes[id]
    e.stage = Stage.closed
    e.outcome = e.plannedOutcome if e.plannedOutcome is not None else Outcome.discharged
    e.outcomeAt = s.now
    s.events.append(SimEvent("finished", id))


def arrive(s: SimState, c: SimConfig) -> None:
    rng = s.rng
    ats = rng.pick(c.triageMix) + 1
    u = rng.uniform()
    mh = c.mhByATS[ats - 1]
    cohort = Cohort.mh if u < mh else (Cohort.p65 if u < mh + c.p65ByATS[ats - 1] else Cohort.other)
    e = make_identity(len(s.episodes), cohort, ats, s.now, rng, c)
    if rng.chance(c.referredByATS[ats - 1]):
        e.stage = Stage.closed
        e.outcome = Outcome.redirected
        e.outcomeAt = s.now
        e.redirectService = network.redirect_target(e)
        s.episodes.append(e)
        s.events.append(SimEvent("redirected", e.id))
        return
    e.patience = rng.lognormal(c.patienceMedian[ats - 1], c.patienceSigma)
    e.etaConsent = rng.chance(0.85)
    e.etaSentAt = s.now + 3 if e.etaConsent else None
    s.episodes.append(e)
    s.waiting.append(e.id)


def step(s: SimState, c: SimConfig) -> None:
    t = s.now
    for _ in range(s.rng.poisson(c.arrivals_per_minute(t))):
        arrive(s, c)
    episodes = s.episodes
    # Category 1 goes straight in.
    for id in list(s.waiting):
        e = episodes[id]
        if e.ats == 1 and not e.holdFromCall:
            call(s, c, id)
    calls = s.rng.poisson(c.calls_per_minute(t))
    while calls > 0:
        id = next_to_call(s, c)
        if id is None:
            break
        call(s, c, id)
        calls -= 1
    for id in list(s.waiting):
        if (t - episodes[id].arrival) >= episodes[id].patience:
            leave(s, id)
    for id in list(s.inCare):
        ends = episodes[id].careEnds
        if ends is not None and ends <= t:
            finish(s, id)
    s.now += 1
