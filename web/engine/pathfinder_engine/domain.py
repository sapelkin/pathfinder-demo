"""The shared vocabulary of the engine: cohorts, outcomes, flags, vitals, follow-ups and the episode itself.

Enums carry fixed string values, so the JSON is stable. ``Episode`` and ``FollowUp`` convert to and from plain
dicts (camelCase keys) so the whole document can be stored as JSON.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, Optional


class Cohort(str, Enum):
    mh = "mh"
    p65 = "p65"
    other = "other"

    @property
    def label(self) -> str:
        return {"mh": "Mental health", "p65": "Aged 65+", "other": "General"}[self.value]

    @property
    def short(self) -> str:
        return {"mh": "MH", "p65": "65+", "other": ""}[self.value]


class Outcome(str, Enum):
    """The journey letters from the whiteboard. B stops at the ward; D and every R get follow-through."""

    admitted = "B"
    discharged = "D"
    redirected = "R1"
    didNotWait = "R2"
    leftAtOwnRisk = "R3"

    @property
    def label(self) -> str:
        return {
            "B": "Admitted",
            "D": "Discharged home",
            "R1": "Redirected at triage",
            "R2": "Did not wait",
            "R3": "Left at own risk",
        }[self.value]

    @property
    def needs_follow_up(self) -> bool:
        return self is not Outcome.admitted

    @property
    def left_before_care_finished(self) -> bool:
        return self in (Outcome.didNotWait, Outcome.leftAtOwnRisk)


class Stage(str, Enum):
    waiting = "waiting"
    inCare = "inCare"
    closed = "closed"


class TravelMode(str, Enum):
    """The ways of travelling the right-door model knows: each has its own cost per hexagon (see rightdoor.py)."""

    walk = "walk"
    bus = "bus"
    car = "car"

    @property
    def label(self) -> str:
        return {"walk": "On foot", "bus": "By bus", "car": "By car"}[self.value]

    @property
    def short(self) -> str:
        return {"walk": "on foot", "bus": "by bus", "car": "by car"}[self.value]

    @property
    def symbol(self) -> str:
        return {"walk": "figure.walk", "bus": "bus.fill", "car": "car.fill"}[self.value]


class ArrivalMode(str, Enum):
    """How the person got to the ED, from the data dictionary's mode-of-arrival codes. Private transport is split
    into "by car" and "walked in" for the demo. It sets the way of travelling that the right-door model assumes
    next time."""

    car = "By car"
    walked = "Walked in"
    publicTransport = "By bus or train"
    taxi = "By taxi"
    ambulance = "By ambulance"
    police = "With police"

    @property
    def short(self) -> str:
        return {
            "By car": "by car",
            "Walked in": "on foot",
            "By bus or train": "by bus",
            "By taxi": "by taxi",
            "By ambulance": "by ambulance",
            "With police": "with police",
        }[self.value]

    @property
    def travel(self) -> TravelMode:
        """The way they would most likely travel next time. Ambulance and police arrivals are assumed to have a car
        or a taxi; the nurse can change it on the Right door screen."""
        if self is ArrivalMode.walked:
            return TravelMode.walk
        if self is ArrivalMode.publicTransport:
            return TravelMode.bus
        return TravelMode.car

    @property
    def symbol(self) -> Optional[str]:
        return {"By ambulance": "staroflife.fill", "With police": "shield.fill"}.get(self.value)


class ClinicalFlag(str, Enum):
    suicidalIdeation = "suicidalIdeation"
    selfHarm = "selfHarm"
    mentalHealthAct = "mentalHealthAct"
    drugsAlcohol = "drugsAlcohol"
    agitation = "agitation"
    psychosis = "psychosis"
    notLikelyToWait = "notLikelyToWait"

    @property
    def label(self) -> str:
        return {
            "suicidalIdeation": "Suicidal ideation",
            "selfHarm": "Self-harm",
            "mentalHealthAct": "Mental Health Act referral",
            "drugsAlcohol": "Drugs or alcohol",
            "agitation": "Agitated",
            "psychosis": "Psychotic symptoms",
            "notLikelyToWait": "Not likely to wait",
        }[self.value]

    @property
    def is_high_risk(self) -> bool:
        return self in (ClinicalFlag.suicidalIdeation, ClinicalFlag.selfHarm, ClinicalFlag.mentalHealthAct)


@dataclass
class Vitals:
    pulse: Optional[int] = None
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    spo2: Optional[int] = None
    resp: Optional[int] = None
    temp: Optional[float] = None
    gcs: Optional[int] = None
    pain: Optional[int] = None

    @property
    def is_empty(self) -> bool:
        return (self.pulse is None and self.systolic is None and self.spo2 is None and self.resp is None
                and self.temp is None and self.gcs is None and self.pain is None)

    def merge(self, other: "Vitals") -> None:
        for f in fields(self):
            v = getattr(other, f.name)
            if v is not None:
                setattr(self, f.name, v)

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: Optional[dict[str, Any]]) -> "Vitals":
        if not d:
            return cls()
        return cls(**{f.name: d.get(f.name) for f in fields(cls)})


class FollowTier(int, Enum):
    callNow = 1
    callToday = 2
    within24h = 3
    autoMessage = 4

    @property
    def title(self) -> str:
        return {1: "Call now", 2: "Call today", 3: "Check within 24 hours", 4: "Automatic day-2 message"}[self.value]

    @property
    def short_title(self) -> str:
        return {1: "Call now", 2: "Call today", 3: "Within 24 h", 4: "Auto message"}[self.value]

    @property
    def due_minutes(self) -> int:
        return {1: 60, 2: 8 * 60, 3: 24 * 60, 4: 48 * 60}[self.value]

    @property
    def policy(self) -> str:
        return {
            1: "High risk: contact immediately (WACHS did-not-wait policy, high risk).",
            2: "Moderate risk: contact the same day. The policy says next business hours; Pathfinder runs 7 days.",
            3: "Check the person got the care they need: message first, call if no reply.",
            4: "Routine: a day-2 check-in message with where to go next time.",
        }[self.value]


class FollowStatus(str, Enum):
    open = "open"
    noAnswer = "noAnswer"
    closed = "closed"


@dataclass
class FollowUp:
    tier: FollowTier
    reasons: list[str]
    risk7: Optional[float] = None
    risk28: Optional[float] = None
    riskN: Optional[int] = None
    riskBasis: str = ""
    status: FollowStatus = FollowStatus.open
    attempts: int = 0
    lastAttemptAt: Optional[int] = None
    result: Optional[str] = None
    nextStep: Optional[str] = None
    closedAt: Optional[int] = None
    aloOffered: bool = False
    messageSent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": int(self.tier),
            "tierTitle": self.tier.title,
            "reasons": list(self.reasons),
            "risk7": self.risk7,
            "risk28": self.risk28,
            "riskN": self.riskN,
            "riskBasis": self.riskBasis,
            "status": self.status.value,
            "attempts": self.attempts,
            "lastAttemptAt": self.lastAttemptAt,
            "result": self.result,
            "nextStep": self.nextStep,
            "closedAt": self.closedAt,
            "aloOffered": self.aloOffered,
            "messageSent": self.messageSent,
            "dueMinutes": self.tier.due_minutes,
            "policy": self.tier.policy,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FollowUp":
        return cls(
            tier=FollowTier(int(d["tier"])), reasons=list(d.get("reasons", [])), risk7=d.get("risk7"),
            risk28=d.get("risk28"), riskN=d.get("riskN"), riskBasis=d.get("riskBasis", ""),
            status=FollowStatus(d.get("status", "open")), attempts=int(d.get("attempts", 0)),
            lastAttemptAt=d.get("lastAttemptAt"), result=d.get("result"), nextStep=d.get("nextStep"),
            closedAt=d.get("closedAt"), aloOffered=bool(d.get("aloOffered", False)),
            messageSent=bool(d.get("messageSent", False)),
        )


_INF = float("inf")


@dataclass
class Episode:
    id: int
    name: str
    age: int
    sex: str
    cohort: Cohort
    complaint: str
    complaintKey: str
    ats: int
    arrival: int
    arrivalMode: ArrivalMode
    priorVisits: int = 0
    daysSinceLast: Optional[int] = None
    priorDNW: bool = False
    flags: set[ClinicalFlag] = field(default_factory=set)
    homeLat: float = 0.0
    homeLon: float = 0.0
    homeSuburb: str = ""
    patience: float = _INF
    holdFromCall: bool = False
    holdReason: Optional[str] = None
    stage: Stage = Stage.waiting
    calledAt: Optional[int] = None
    careEnds: Optional[int] = None
    plannedOutcome: Optional[Outcome] = None
    scriptedCareMinutes: Optional[int] = None
    outcome: Optional[Outcome] = None
    outcomeAt: Optional[int] = None
    leaveReason: Optional[str] = None
    redirectService: Optional[str] = None
    vitals: Optional[Vitals] = None
    etaConsent: bool = True
    etaSentAt: Optional[int] = None
    isHero: bool = False
    intakeSeconds: Optional[float] = None
    descriptor: Optional[str] = None
    transcript: Optional[str] = None
    followUp: Optional[FollowUp] = None
    # The bot channel (Messenger or Teams) the person messaged from, if any; absent in the apps.
    channelUserId: Optional[str] = None
    channelId: Optional[str] = None
    channelServiceUrl: Optional[str] = None
    channelConversationId: Optional[str] = None

    @property
    def home(self) -> tuple[float, float]:
        return (self.homeLat, self.homeLon)

    @property
    def first_name(self) -> str:
        parts = [p for p in self.name.split(" ") if p]
        return parts[0] if parts else ""

    @property
    def problem(self) -> str:
        """The presenting problem without its duration: "Shortness of breath for a day" is "Shortness of breath"."""
        p = self.complaint
        if " for " in p:
            p = p[: p.index(" for ")]
        if "," in p:
            p = p[: p.index(",")]
        return p.strip(" \t")

    def to_dict(self) -> dict[str, Any]:
        """Every field, camelCase; keys whose value is None are left out to keep the document small."""
        d = {
            "id": self.id, "name": self.name, "age": self.age, "sex": self.sex, "cohort": self.cohort.value,
            "complaint": self.complaint, "complaintKey": self.complaintKey, "ats": self.ats, "arrival": self.arrival,
            "arrivalMode": self.arrivalMode.value,
            "patience": None if math.isinf(self.patience) else float(self.patience),
            "holdFromCall": self.holdFromCall, "holdReason": self.holdReason, "stage": self.stage.value,
            "calledAt": self.calledAt, "careEnds": self.careEnds,
            "plannedOutcome": self.plannedOutcome.value if self.plannedOutcome else None,
            "scriptedCareMinutes": self.scriptedCareMinutes,
            "outcome": self.outcome.value if self.outcome else None, "outcomeAt": self.outcomeAt,
            "leaveReason": self.leaveReason, "redirectService": self.redirectService,
            "priorVisits": self.priorVisits, "daysSinceLast": self.daysSinceLast, "priorDNW": self.priorDNW,
            "flags": sorted(f.value for f in self.flags),
            "vitals": self.vitals.to_dict() if self.vitals else None,
            "etaConsent": self.etaConsent, "etaSentAt": self.etaSentAt, "isHero": self.isHero,
            "intakeSeconds": self.intakeSeconds, "descriptor": self.descriptor, "transcript": self.transcript,
            "homeLat": self.homeLat, "homeLon": self.homeLon, "homeSuburb": self.homeSuburb,
            "followUp": self.followUp.to_dict() if self.followUp else None,
            "channelUserId": self.channelUserId, "channelId": self.channelId,
            "channelServiceUrl": self.channelServiceUrl, "channelConversationId": self.channelConversationId,
        }
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Episode":
        patience = d.get("patience")
        return cls(
            id=int(d["id"]), name=d["name"], age=int(d["age"]), sex=d["sex"], cohort=Cohort(d["cohort"]),
            complaint=d["complaint"], complaintKey=d["complaintKey"], ats=int(d["ats"]), arrival=int(d["arrival"]),
            arrivalMode=ArrivalMode(d["arrivalMode"]), priorVisits=int(d.get("priorVisits", 0)),
            daysSinceLast=d.get("daysSinceLast"), priorDNW=bool(d.get("priorDNW", False)),
            flags={ClinicalFlag(f) for f in d.get("flags", [])}, homeLat=float(d.get("homeLat", 0.0)),
            homeLon=float(d.get("homeLon", 0.0)), homeSuburb=d.get("homeSuburb", ""),
            patience=_INF if patience is None else float(patience), holdFromCall=bool(d.get("holdFromCall", False)),
            holdReason=d.get("holdReason"), stage=Stage(d.get("stage", "waiting")), calledAt=d.get("calledAt"),
            careEnds=d.get("careEnds"),
            plannedOutcome=Outcome(d["plannedOutcome"]) if d.get("plannedOutcome") else None,
            scriptedCareMinutes=d.get("scriptedCareMinutes"),
            outcome=Outcome(d["outcome"]) if d.get("outcome") else None, outcomeAt=d.get("outcomeAt"),
            leaveReason=d.get("leaveReason"), redirectService=d.get("redirectService"),
            vitals=Vitals.from_dict(d["vitals"]) if d.get("vitals") else None,
            etaConsent=bool(d.get("etaConsent", True)), etaSentAt=d.get("etaSentAt"), isHero=bool(d.get("isHero", False)),
            intakeSeconds=d.get("intakeSeconds"), descriptor=d.get("descriptor"), transcript=d.get("transcript"),
            followUp=FollowUp.from_dict(d["followUp"]) if d.get("followUp") else None,
            channelUserId=d.get("channelUserId"), channelId=d.get("channelId"),
            channelServiceUrl=d.get("channelServiceUrl"), channelConversationId=d.get("channelConversationId"),
        )


@dataclass
class Banner:
    text: str
    systemImage: str
    tone: str  # "info" | "warning" | "success"
    episodeId: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "systemImage": self.systemImage, "tone": self.tone, "episodeId": self.episodeId}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Banner":
        return cls(text=d["text"], systemImage=d["systemImage"], tone=d["tone"], episodeId=d.get("episodeId"))
