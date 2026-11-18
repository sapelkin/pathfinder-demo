"""Everything in Pathfinder is a unit of one of five kinds, wired to other units; a site runs the units it needs.

``AppTab``, ``UnitKind``, ``Deployment``, ``Unit`` and ``Units``: the catalogue the architecture view draws.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AppTab(str, Enum):
    frontDoor = "frontDoor"
    followThrough = "followThrough"
    rightDoor = "rightDoor"
    impact = "impact"
    dashboard = "dashboard"

    @staticmethod
    def tabs(d: "Deployment") -> list["AppTab"]:
        """The minimum and standard deployments have only the front door; follow-through, the right door, the
        measures and the live dashboard are full units."""
        if d is Deployment.full:
            return [AppTab.frontDoor, AppTab.followThrough, AppTab.rightDoor, AppTab.impact, AppTab.dashboard]
        return [AppTab.frontDoor]


class UnitKind(str, Enum):
    connector = "connector"
    store = "store"
    model = "model"
    function = "function"
    surface = "surface"

    @property
    def label(self) -> str:
        return {"connector": "Connectors", "store": "Stores", "model": "Models", "function": "Functions",
                "surface": "Screens"}[self.value]

    @property
    def blurb(self) -> str:
        return {
            "connector": "One interface each, in or out",
            "store": "The data the units share",
            "model": "Turn data into a number, a rank or a list, and show their working",
            "function": "What a person gets",
            "surface": "Where they get it",
        }[self.value]

    @property
    def singular(self) -> str:
        return "screen" if self is UnitKind.surface else self.value


class Deployment(str, Enum):
    minimum = "minimum"
    standard = "standard"
    full = "full"

    @property
    def label(self) -> str:
        return self.value.capitalize()

    @property
    def summary(self) -> str:
        return {
            "minimum": "Seven units, one interface: the ED system's own messages. Everyone who consents knows their wait; no new screen for staff.",
            "standard": "Adds the front door: voice intake, the triage rules, history, the nurse app and an audit log.",
            "full": "Adds follow-through and the right door: alerts, the directory, travel times, the ranker, the search, the worklist, the six measures and write-back.",
        }[self.value]

    @property
    def rank(self) -> int:
        return list(Deployment).index(self)

    @property
    def layer_title(self) -> str:
        return {"minimum": "The foundation: minimum, 7 units", "standard": "Second layer: standard, adds 6",
                "full": "Third layer: full, adds 13"}[self.value]

    @property
    def layer_blurb(self) -> str:
        return {
            "minimum": "One interface, the ED system's own messages. Every patient who consents knows their wait; no new screen for staff.",
            "standard": "The front door: the nurse speaks, the rules suggest, the nurse confirms, the message goes.",
            "full": "Follow-through and the right door, the six measures, and write-back to the record.",
        }[self.value]


@dataclass(frozen=True)
class Unit:
    id: str
    name: str
    kind: UnitKind
    tier: Deployment  # the smallest deployment that includes it
    connects: str  # what it is, or what it plugs into
    gives: str  # what the rest of the system gets from it
    frm: tuple[str, ...]  # the units it takes its input from
    symbol: str

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "kind": self.kind.value, "tier": self.tier.value,
                "plugsInto": self.connects, "gives": self.gives, "from": list(self.frm), "symbol": self.symbol}


def _u(id: str, name: str, kind: UnitKind, tier: Deployment, connects: str, gives: str, frm: list[str], symbol: str) -> Unit:
    return Unit(id, name, kind, tier, connects, gives, tuple(frm), symbol)


ALL: list[Unit] = [
    # Connectors
    _u("adt", "ED system messages", UnitKind.connector, Deployment.minimum,
       "HL7 v2 ADT from EDIS or any vendor's ED system; FHIR from the state EMR",
       "Every arrival, category and departure, as it happens", [], "arrow.left.arrow.right"),
    _u("history", "Patient history", UnitKind.connector, Deployment.standard,
       "webPAS and the data collection: prior visits, prior did-not-wait",
       "The \"we have seen you before\" snapshot", [], "clock.arrow.circlepath"),
    _u("psolis", "Mental health alerts", UnitKind.connector, Deployment.full,
       "PSOLIS", "Alerts and the policy tier", [], "brain.head.profile"),
    _u("eddc", "Data collection extract", UnitKind.connector, Deployment.full,
       "The EDDC every WA ED reports to; a monthly refresh (the demo ships aggregates built from published figures)",
       "Recalibration: template, mix, patience, return risk", [], "tray.and.arrow.down"),
    _u("directory", "Service directory", UnitKind.connector, Deployment.full,
       "National Health Services Directory, healthdirect",
       "Open services, their hours and what they take", [], "list.bullet.rectangle"),
    _u("routing", "Travel times", UnitKind.connector, Deployment.full,
       "A routing provider over H3 cells: car, bus, on foot",
       "Minutes from home to each service", [], "map"),
    _u("sms", "SMS gateway", UnitKind.connector, Deployment.minimum,
       "Any SMS provider; later Manage My Care",
       "Delivers the messages; nothing to install", ["messages"], "paperplane"),
    _u("writeback", "Write-back", UnitKind.connector, Deployment.full,
       "FHIR to the ED system or the state EMR",
       "Expected time, follow-up outcome and reason, on the record", ["frontdoor", "followthrough"], "square.and.arrow.down"),
    # Stores
    _u("episodes", "Episode store", UnitKind.store, Deployment.minimum,
       "One row per presentation: who is waiting, since when, what happened; synthetic ids in the demo",
       "The live queue and each person's timeline", ["adt", "history", "psolis"], "cylinder"),
    _u("aggregates", "Aggregates store", UnitKind.store, Deployment.minimum,
       "Hour-of-week template, triage mix, patience calibration, return-risk table; counts under 5 suppressed",
       "What every model is calibrated to", ["eddc"], "cylinder.split.1x2"),
    _u("places", "Places store", UnitKind.store, Deployment.full,
       "Services with hours and the fit table, indexed by hexagon",
       "What the right-door search searches", ["directory"], "mappin.and.ellipse"),
    _u("audit", "Audit log", UnitKind.store, Deployment.standard,
       "Every suggestion, confirmation and message, with user and time; Entra ID sign-on",
       "What governance asks for", ["frontdoor", "followthrough", "messages"], "lock.doc"),
    # Models
    _u("wait", "Wait model", UnitKind.model, Deployment.minimum,
       "100 simulated futures of the queue, by the room's own rules",
       "An expected wait as a range, per person", ["episodes", "aggregates"], "clock.badge.questionmark"),
    _u("intake", "Voice intake", UnitKind.model, Deployment.standard,
       "On-device speech to a structured note",
       "The record without typing", ["nurse"], "waveform"),
    _u("triage", "Triage rules", UnitKind.model, Deployment.standard,
       "Published ATS descriptors, printable for governance",
       "A suggested category with its source; the nurse decides", ["intake"], "list.clipboard"),
    _u("followrank", "Follow-through ranker", UnitKind.model, Deployment.full,
       "The did-not-wait policy tiers, then the return-risk table",
       "Who to call first, and by when", ["episodes", "aggregates"], "arrow.triangle.2.circlepath"),
    _u("rightdoor", "Right-door search", UnitKind.model, Deployment.full,
       "Hexagon rings from home, then shortest paths, hours and fit",
       "The ranked places, by the person's own transport", ["episodes", "places", "routing"], "signpost.right.and.left"),
    # Functions
    _u("messages", "Patient messages", UnitKind.function, Deployment.minimum,
       "Consent at the door; two templates; no clinical content; refreshed every 10 minutes",
       "Everyone who consents knows their wait", ["wait", "episodes"], "message"),
    _u("frontdoor", "Front door", UnitKind.function, Deployment.standard,
       "Speak, suggest, confirm, send",
       "The record in under three minutes", ["intake", "triage", "wait"], "door.left.hand.open"),
    _u("followthrough", "Follow-through", UnitKind.function, Deployment.full,
       "The ranked list, the call script, the outcome and the reason",
       "No one who leaves is lost", ["followrank", "rightdoor"], "checklist"),
    _u("redirect", "Redirect and next time", UnitKind.function, Deployment.full,
       "A redirect at triage when the gate allows; the right door for next time after",
       "Everyone gets the right door", ["rightdoor"], "figure.walk.motion"),
    _u("kpi", "Six measures", UnitKind.function, Deployment.full,
       "Capture time, know-your-wait, did not wait, contacted, returns, named next step",
       "The pilot's scorecard", ["episodes"], "chart.bar.xaxis"),
    # Screens
    _u("patient", "Patient's phone", UnitKind.surface, Deployment.minimum,
       "A text message; nothing to install",
       "The expected time, and a check-in after", ["sms"], "iphone.radiowaves.left.and.right"),
    _u("nurse", "Nurse app", UnitKind.surface, Deployment.standard,
       "iOS, web, or a Power App in Teams",
       "The front door, hands free", ["frontdoor", "redirect"], "iphone"),
    _u("worklist", "Worklist", UnitKind.surface, Deployment.full,
       "The same app, or Teams",
       "The follow-through list and each case", ["followthrough"], "list.bullet.clipboard"),
    _u("dashboard", "Dashboard", UnitKind.surface, Deployment.full,
       "Power BI, or the existing dashboard",
       "The six measures, every week", ["kpi"], "rectangle.3.group"),
]


def units_in(d: Deployment) -> list[Unit]:
    return [u for u in ALL if u.tier.rank <= d.rank]


def layer(d: Deployment) -> list[Unit]:
    """The units a deployment adds on top of the one below it, connectors first."""
    order = list(UnitKind)
    return sorted([u for u in ALL if u.tier is d], key=lambda u: order.index(u.kind))


def ids_in(d: Deployment) -> set[str]:
    return {u.id for u in units_in(d)}


def units_of(kind: UnitKind) -> list[Unit]:
    return [u for u in ALL if u.kind is kind]


def unit(id: str) -> Unit | None:
    return next((u for u in ALL if u.id == id), None)


def consumers(id: str) -> list[Unit]:
    """The units that take this one's output."""
    return [u for u in ALL if id in u.frm]


def edges() -> list[tuple[str, str]]:
    """Every edge, from a unit to the unit it feeds."""
    return [(src, u.id) for u in ALL for src in u.frm]
