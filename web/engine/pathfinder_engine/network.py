"""The demo metro and the services someone could go to instead of, or after, this ED.

Statewide phone and virtual services are real public services
with their published hours; every hospital, clinic, pharmacy, road and location is invented for the demo. Coordinates
are plain ``(lat, lon)`` tuples; ``Metro.coordinate`` does the km-to-degrees maths.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from . import hexgrid
from .clock import WEEK
from .domain import Cohort, Episode
from .hexgrid import Hex
from .rng import SeededRNG


class Kind(str, Enum):
    ed = "ed"
    urgentCare = "urgentCare"
    gp = "gp"
    pharmacy = "pharmacy"
    mentalHealth = "mentalHealth"
    safeHaven = "safeHaven"
    virtualED = "virtualED"
    phone = "phone"
    homeCare = "homeCare"

    @property
    def label(self) -> str:
        return {
            "ed": "Emergency department", "urgentCare": "Urgent care clinic", "gp": "GP", "pharmacy": "Pharmacy",
            "mentalHealth": "Mental health team", "safeHaven": "Safe Haven", "virtualED": "Virtual ED",
            "phone": "Phone line", "homeCare": "Care at home",
        }[self.value]

    @property
    def bookable(self) -> bool:
        """Booked rather than walked into, so closing hours matter less in the score."""
        return self in (Kind.gp, Kind.mentalHealth, Kind.homeCare)


@dataclass(frozen=True)
class CareService:
    id: str
    name: str
    kind: Kind
    x: Optional[float]  # km east of the demo ED; None for phone, virtual and at-home services
    y: Optional[float]  # km north of the demo ED
    contact: str
    hoursText: str
    windows: tuple[tuple[int, int], ...]  # closed ranges of minutes of the week, Monday 00:00 = 0
    suits: frozenset[Cohort]
    goodFor: str

    @property
    def is_place(self) -> bool:
        return self.x is not None and self.y is not None

    @property
    def coordinate(self) -> Optional[tuple[float, float]]:
        if self.x is None or self.y is None:
            return None
        return coordinate(self.x, self.y)

    @property
    def hex(self) -> Optional[Hex]:
        if self.x is None or self.y is None:
            return None
        return hexgrid.hex_at(self.x, self.y)

    def is_open(self, t: int) -> bool:
        return self.opens_in(t) == 0

    def opens_in(self, t: int) -> int:
        """Minutes until it is next open, from ``t``; 0 when open now."""
        m = ((t % WEEK) + WEEK) % WEEK
        for lo, hi in self.windows:
            if lo <= m <= hi:
                return 0
        best = WEEK
        for lo, _ in self.windows:
            d = lo - m
            best = min(best, d if d >= 0 else d + WEEK)
        return best

    @property
    def parking_minutes(self) -> float:
        """Minutes from the car to the door, added to driving time."""
        if self.kind is Kind.ed:
            return 6
        if self.kind is Kind.urgentCare:
            return 3
        return 2

    @property
    def symbol(self) -> str:
        return {
            "ed": "cross.fill", "urgentCare": "cross.case.fill", "gp": "stethoscope", "pharmacy": "pills.fill",
            "mentalHealth": "brain.head.profile", "safeHaven": "cup.and.saucer.fill", "virtualED": "video.fill",
            "phone": "phone.fill", "homeCare": "house.fill",
        }[self.kind.value]

    def to_dict(self) -> dict:
        c = self.coordinate
        return {
            "id": self.id, "name": self.name, "kind": self.kind.value, "kindLabel": self.kind.label, "x": self.x,
            "y": self.y, "lat": c[0] if c else None, "lon": c[1] if c else None, "contact": self.contact,
            "hoursText": self.hoursText, "windows": [[lo, hi] for lo, hi in self.windows],
            "suits": sorted(s.value for s in self.suits), "goodFor": self.goodFor, "symbol": self.symbol,
            "bookable": self.kind.bookable, "hex": self.hex.to_dict() if self.hex else None,
        }


# --- The demo metro -------------------------------------------------------------------------------------------------

ED_LAT = -31.9290
ED_LON = 115.9020
KM_PER_DEG_LAT = 110.57
KM_PER_DEG_LON = 111.32 * math.cos(ED_LAT * math.pi / 180)


def xy(lat: float, lon: float) -> tuple[float, float]:
    return ((lon - ED_LON) * KM_PER_DEG_LON, (lat - ED_LAT) * KM_PER_DEG_LAT)


def coordinate(x: float, y: float) -> tuple[float, float]:
    """(lat, lon) of a point ``x`` km east and ``y`` km north of the demo ED."""
    return (ED_LAT + y / KM_PER_DEG_LAT, ED_LON + x / KM_PER_DEG_LON)


@dataclass(frozen=True)
class Suburb:
    name: str
    x: float
    y: float
    spread: float  # km, standard deviation of homes around the centre
    weight: float  # share of the demo ED's patients


SUBURBS = [
    Suburb("Central", 0.2, 0.8, 1.0, 15),
    Suburb("Marlow", -3.2, 2.3, 1.0, 13),
    Suburb("Kingsford", 1.4, 4.5, 1.1, 11),
    Suburb("Riverbend", 4.8, 0.4, 1.1, 13),
    Suburb("Eastvale", 5.4, -3.2, 1.2, 9),
    Suburb("Southmead", 0.6, -4.3, 1.1, 11),
    Suburb("Westhaven", -5.2, -1.4, 1.3, 10),
    Suburb("Hillcrest", 5.6, 5.0, 1.4, 8),
    Suburb("Northgate", -0.8, 7.0, 1.3, 8),
]
_SUBURB_WEIGHTS = [s.weight for s in SUBURBS]


def home(rng: SeededRNG, suburbs: Optional[list[Suburb]] = None) -> tuple[float, float, str]:
    """A home for a fictional patient: a suburb by weight, then a spot around its centre. Returns (lat, lon, suburb).
    ``suburbs`` defaults to the demo metro's; metro mode passes the hospital's own table."""
    table = SUBURBS if suburbs is None else suburbs
    s = table[rng.pick(_SUBURB_WEIGHTS if suburbs is None else [x.weight for x in table])]
    x = s.x + rng.normal() * s.spread
    y = s.y + rng.normal() * s.spread
    lat, lon = coordinate(x, y)
    return (lat, lon, s.name)


def suburb(x: float, y: float, suburbs: Optional[list[Suburb]] = None) -> str:
    table = SUBURBS if suburbs is None else suburbs
    best = min(table, key=lambda s: (s.x - x) * (s.x - x) + (s.y - y) * (s.y - y))
    return best.name


# Arterial roads with bus routes, as polylines in km. Invented, like everything else on the demo map.
CORRIDORS: list[list[tuple[float, float]]] = [
    [(-7.5, -0.2), (-5.4, -1.0), (-3.0, 0.4), (0.0, 0.2), (2.4, 0.5), (4.6, 0.9), (7.3, -1.5), (8.5, -1.8)],  # east–west
    [(0.6, -6.5), (0.6, -4.2), (0.4, -1.8), (0.2, 0.2), (0.8, 2.4), (1.2, 4.5), (0.2, 6.2), (-1.0, 7.6)],  # north–south
    [(0.0, 0.2), (-1.6, 1.4), (-3.2, 2.4), (-4.6, 3.8), (-5.8, 5.0)],  # north-west
    [(0.2, 0.2), (1.8, 1.6), (3.2, 2.6), (4.3, 3.1), (5.8, 5.2)],  # north-east
    [(0.4, -0.2), (2.4, -1.6), (4.0, -2.8), (5.6, -3.4), (7.3, -1.7)],  # south-east
    [(0.0, 0.0), (-1.8, -1.2), (-3.4, -2.7), (-5.4, -1.6)],  # south-west
    [(-3.2, 2.4), (-1.0, 4.0), (1.2, 4.5), (3.2, 4.2), (4.9, 1.6)],  # northern link
]


def _corridor_hexes() -> frozenset[Hex]:
    """The hexagons the arterials pass through."""
    out: set[Hex] = set()
    for line in CORRIDORS:
        for i in range(1, len(line)):
            x0, y0 = line[i - 1]
            x1, y1 = line[i]
            length = math.sqrt((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0))
            n = max(1, int(length / 0.12))
            for k in range(n + 1):
                f = k / n
                out.add(hexgrid.hex_at(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
    return frozenset(out)


CORRIDOR_HEXES: frozenset[Hex] = _corridor_hexes()


# --- The services ---------------------------------------------------------------------------------------------------

ALWAYS = ((0, 10_079),)
ALL = frozenset([Cohort.mh, Cohort.p65, Cohort.other])
WEEKDAYS = [0, 1, 2, 3, 4]


def daily(frm: int, to: int) -> tuple[tuple[int, int], ...]:
    return tuple((d * 1440 + frm, d * 1440 + to) for d in range(7))


def days(ds: list[int], frm: int, to: int) -> tuple[tuple[int, int], ...]:
    return tuple((d * 1440 + frm, d * 1440 + to) for d in ds)


def _svc(id: str, name: str, kind: Kind, x: Optional[float], y: Optional[float], contact: str, hours: str,
         windows: tuple[tuple[int, int], ...], suits: frozenset[Cohort], good_for: str) -> CareService:
    return CareService(id=id, name=name, kind=kind, x=x, y=y, contact=contact, hoursText=hours, windows=windows,
                       suits=suits, goodFor=good_for)


_GEN = frozenset([Cohort.other, Cohort.p65])
_MH = frozenset([Cohort.mh])

SERVICES: list[CareService] = [
    # Hospitals
    _svc("ed_here", "This ED", Kind.ed, 0, 0, "Call 000 in an emergency", "24 hours, 7 days", ALWAYS, ALL,
         "Emergencies and time-critical symptoms"),
    _svc("ed_riverbend", "Riverbend Hospital ED", Kind.ed, 4.9, 1.6, "Call 000 in an emergency", "24 hours, 7 days", ALWAYS,
         ALL, "Emergencies and time-critical symptoms"),
    _svc("ed_northgate", "Northgate Hospital ED", Kind.ed, -1.0, 7.6, "Call 000 in an emergency", "24 hours, 7 days", ALWAYS,
         ALL, "Emergencies and time-critical symptoms"),
    # Urgent care
    _svc("ucc_north", "Urgent Care Clinic North", Kind.urgentCare, -3.9, 4.6, "Walk in", "Every day, 8 am to 10 pm",
         daily(480, 1320), _GEN, "Minor injuries, infections, sprains, stitches, X-ray"),
    _svc("ucc_east", "Urgent Care Clinic East", Kind.urgentCare, 7.3, -1.7, "Walk in", "Every day, 8 am to 8 pm",
         daily(480, 1200), _GEN, "Minor injuries and illness"),
    _svc("ucc_south", "Urgent Care Clinic South", Kind.urgentCare, 0.9, -4.6, "Walk in", "Every day, 8 am to 8 pm",
         daily(480, 1200), _GEN, "Minor injuries and illness, X-ray"),
    # GPs
    _svc("gp_central", "Central Medical Centre", Kind.gp, 0.4, 1.0, "Book or walk in",
         "Weekdays 7:30 am to 7 pm, Saturday 8 am to 4 pm", days(WEEKDAYS, 450, 1140) + days([5], 480, 960), ALL,
         "GP care, results, referrals"),
    _svc("gp_riverbend", "Riverbend Medical Centre", Kind.gp, 4.6, 0.6, "Book",
         "Weekdays 8 am to 6 pm, Saturday 8 am to 1 pm", days(WEEKDAYS, 480, 1080) + days([5], 480, 780), ALL,
         "GP care, care plans, referrals"),
    _svc("gp_marlow", "Marlow Family Practice", Kind.gp, -3.0, 2.2, "Book",
         "Weekdays 8 am to 6 pm, Saturday 8 am to noon", days(WEEKDAYS, 480, 1080) + days([5], 480, 720), ALL,
         "GP care and mental health care plans"),
    _svc("gp_kingsford", "Kingsford Medical", Kind.gp, 1.6, 4.4, "Book",
         "Weekdays 8 am to 6 pm, Saturday 9 am to 1 pm", days(WEEKDAYS, 480, 1080) + days([5], 540, 780), ALL, "GP care"),
    _svc("gp_southmead", "Southmead GP Clinic", Kind.gp, 0.4, -4.0, "Book", "Weekdays 8 am to 6 pm",
         days(WEEKDAYS, 480, 1080), ALL, "GP care"),
    _svc("gp_after", "After-hours GP clinic", Kind.gp, 4.3, 3.1, "Book or walk in",
         "Weekdays 6 pm to 11 pm, weekends noon to 11 pm", days(WEEKDAYS, 1080, 1380) + days([5, 6], 720, 1380), ALL,
         "GP care when the usual GP is closed"),
    _svc("ams", "Aboriginal Medical Service", Kind.gp, -1.8, -1.2, "Book or walk in", "Weekdays, 8:30 am to 5 pm",
         days(WEEKDAYS, 510, 1020), ALL, "GP care and support, Aboriginal community controlled"),
    # Pharmacies
    _svc("ph_central", "Central Pharmacy", Kind.pharmacy, 0.2, 0.4, "Walk in", "Every day, 7 am to 10 pm", daily(420, 1320),
         _GEN, "Medicines, minor ailments, advice"),
    _svc("ph_riverbend", "Riverbend Pharmacy", Kind.pharmacy, 4.5, 0.9, "Walk in", "Every day, 8 am to 9 pm", daily(480, 1260),
         _GEN, "Medicines, minor ailments, advice"),
    _svc("ph_marlow", "Marlow Pharmacy", Kind.pharmacy, -3.1, 2.5, "Walk in", "Every day, 8 am to 8 pm", daily(480, 1200),
         _GEN, "Medicines, minor ailments, advice"),
    _svc("ph_south", "Southmead Pharmacy", Kind.pharmacy, 0.8, -4.3, "Walk in", "Every day, 8 am to 8 pm", daily(480, 1200),
         _GEN, "Medicines, minor ailments, advice"),
    # Mental health
    _svc("cmht", "Community mental health team", Kind.mentalHealth, 3.2, 1.5, "Referral from ED", "Weekdays, 8:30 am to 5 pm",
         days(WEEKDAYS, 510, 1020), _MH, "Follow-up care and a case manager"),
    _svc("safe_haven", "Safe Haven café", Kind.safeHaven, -3.4, -2.7, "Walk in", "Friday to Sunday, 3 pm to 7:45 pm",
         days([4, 5, 6], 900, 1185), _MH, "Calm after-hours support in distress, instead of the ED"),
    # Without travelling: real public services with their published hours.
    _svc("waved", "WA Virtual Emergency Department", Kind.virtualED, None, None, "Via 1800MEDICARE (1800 633 422)",
         "Every day, 8 am to 10 pm", daily(480, 1320), frozenset([Cohort.p65, Cohort.other]),
         "Urgent but not life-threatening problems, by video; aged-care residents"),
    _svc("mherl", "Mental Health Emergency Response Line", Kind.phone, None, None, "1300 555 788", "24 hours, 7 days", ALWAYS,
         _MH, "Mental health crisis support and assessment"),
    _svc("hith", "Hospital in the Home", Kind.homeCare, None, None, "Referral from ED", "24 hours, 7 days", ALWAYS,
         frozenset([Cohort.p65]), "Nursing and medical care at home instead of a ward bed"),
    _svc("healthdirect", "healthdirect", Kind.phone, None, None, "1800 022 222", "24 hours, 7 days", ALWAYS, ALL,
         "Nurse advice on where to go"),
]


def service(id: str) -> Optional[CareService]:
    return next((s for s in SERVICES if s.id == id), None)


def redirect_target(e: Episode) -> str:
    """Where a triage nurse would send someone who does not need this ED."""
    if e.cohort is Cohort.mh:
        return "Mental Health Emergency Response Line"
    if e.cohort is Cohort.p65:
        return "WA Virtual Emergency Department"
    return "Urgent Care Clinic North"


# Presenting problems where the ED stays the right door: the advice is to call 000, not to go elsewhere.
TIME_CRITICAL = frozenset(["chest_pain", "stroke", "sob", "seizure", "allergy", "head_injury"])
# Injuries: at triage category 3 or above they stay with the ED too.
TRAUMA = frozenset(["fall", "limb", "laceration", "head_injury"])


def ed_is_right_door(e: Episode) -> bool:
    """The ED is the right door: time-critical symptoms, category 1 or 2 (outside mental health), or an injury at
    category 3."""
    return (e.complaintKey in TIME_CRITICAL or (e.ats <= 2 and e.cohort is not Cohort.mh)
            or (e.ats == 3 and e.complaintKey in TRAUMA))


DISCLAIMER = ("Demo metro: every hospital, clinic, road and bus route is invented. Travel times come from the hexagon "
              "model, not a routing service.")


def to_dict(suburbs: Optional[list[Suburb]] = None, hospital_name: str = "This ED") -> dict:
    """The map, for drawing: suburbs (the demo metro's, or the current hospital's real names at their offsets), roads,
    bus corridors (the same polylines), services with coordinates, hex size, and the on-screen disclaimer."""
    table = SUBURBS if suburbs is None else suburbs
    return {
        "ed": {"lat": ED_LAT, "lon": ED_LON, "name": hospital_name},
        "hospitalName": hospital_name, "disclaimer": DISCLAIMER,
        "kmPerDegLat": KM_PER_DEG_LAT, "kmPerDegLon": KM_PER_DEG_LON,
        "hexSize": hexgrid.SIZE, "hexStep": hexgrid.STEP,
        "suburbs": [{"name": s.name, "x": s.x, "y": s.y, "spread": s.spread, "weight": s.weight,
                     "lat": coordinate(s.x, s.y)[0], "lon": coordinate(s.x, s.y)[1]} for s in table],
        # The arterial roads carry the bus routes, so both are the same polylines, in km east/north of the ED.
        "roads": [[[x, y] for x, y in line] for line in CORRIDORS],
        "corridors": [[[x, y] for x, y in line] for line in CORRIDORS],
        "corridorHexes": [h.to_dict() for h in sorted(CORRIDOR_HEXES)],
        "services": [s.to_dict() for s in SERVICES],
    }
