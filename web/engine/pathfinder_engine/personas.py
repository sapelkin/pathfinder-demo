"""The demo's own patients, and the fictional records the demo can "find" when a name is spoken.

``DemoRecords`` are the records a spoken name can match. Every device
can run a different persona (``personaChoice``), or a random one each run; anyone else is a new patient.
"""
from __future__ import annotations

import random as _random
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Record:
    name: str
    age: int
    sex: str
    priorVisits: int
    daysSinceLast: Optional[int]
    lastOutcome: Optional[str]
    priorDNW: bool
    note: str
    homeX: Optional[float] = None  # km from the demo ED; None puts them near it
    homeY: Optional[float] = None
    scriptedCareMinutes: Optional[int] = None  # the demo's own patients are seen, treated and sent home

    def to_dict(self) -> dict:
        return {"name": self.name, "age": self.age, "sex": self.sex, "priorVisits": self.priorVisits,
                "daysSinceLast": self.daysSinceLast, "lastOutcome": self.lastOutcome, "priorDNW": self.priorDNW,
                "note": self.note, "homeX": self.homeX, "homeY": self.homeY,
                "scriptedCareMinutes": self.scriptedCareMinutes}


@dataclass(frozen=True)
class Persona:
    id: str
    name: str  # as dictated
    age: int
    sex: str  # "M" or "F"
    script: str  # what the nurse says at the front door
    category: int  # the category the rules suggest, confirmed by voice
    priorVisits: int
    daysSinceLast: Optional[int]
    lastOutcome: str
    note: str  # the "we have seen you before" line
    homeX: float  # km east of the demo ED
    homeY: float  # km north
    careMinutes: int  # the scripted stay: seen, treated, sent home
    callResult: str  # what the follow-up call records
    nextStep: str

    @property
    def first(self) -> str:
        parts = [p for p in self.name.split(" ") if p]
        return parts[0] if parts else ""

    @property
    def short(self) -> str:
        """The name as the waiting room shows it: first name and initial."""
        p = [x for x in self.name.split(" ") if x]
        return f"{p[0]} {p[1][:1]}." if len(p) > 1 else self.name

    @property
    def he(self) -> str:
        return "he" if self.sex == "M" else "she"

    @property
    def his(self) -> str:
        return "his" if self.sex == "M" else "her"

    @property
    def label(self) -> str:
        return f"{self.name}, {self.age}"

    @property
    def record(self) -> Record:
        return Record(name=self.name, age=self.age, sex=self.sex, priorVisits=self.priorVisits,
                      daysSinceLast=self.daysSinceLast, lastOutcome=self.lastOutcome, priorDNW=False, note=self.note,
                      homeX=self.homeX, homeY=self.homeY, scriptedCareMinutes=self.careMinutes)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "age": self.age, "sex": self.sex, "script": self.script,
                "category": self.category, "note": self.note, "label": self.label, "short": self.short,
                "first": self.first, "priorVisits": self.priorVisits, "daysSinceLast": self.daysSinceLast,
                "lastOutcome": self.lastOutcome, "homeX": self.homeX, "homeY": self.homeY,
                "careMinutes": self.careMinutes, "callResult": self.callResult, "nextStep": self.nextStep}


ALAN = Persona(
    id="alan", name="Alan Pierce", age=72, sex="M",
    script="Name is Alan Pierce, 72 year old man, chest pain for 2 hours, worse when breathing in. Came by car. Pulse 104, BP 150 over 90, sats 95 percent, pain 6 out of 10.",
    category=2, priorVisits=3, daysSinceLast=12, lastOutcome="Discharged home",
    note="Chest pain in June and August, discharged both times; GP letter sent", homeX=5.3, homeY=-0.5, careMinutes=150,
    callResult="Home and well. GP appointment booked for Monday; cardiology clinic referral sent.",
    nextStep="GP on Monday. If the chest pain comes back: call 000")
GRACE = Persona(
    id="grace", name="Grace Bennett", age=68, sex="F",
    script="Name is Grace Bennett, 68 year old woman, short of breath for a day, hurts to breathe. Came by car. Pulse 96, BP 138 over 84, sats 92 percent, resp rate 24, pain 5 out of 10.",
    category=3, priorVisits=2, daysSinceLast=41, lastOutcome="Discharged home",
    note="Short of breath in May, discharged; asthma and COPD plan with her GP", homeX=1.7, homeY=4.8, careMinutes=150,
    callResult="Home and breathing easier. GP appointment booked for Monday; respiratory clinic referral sent.",
    nextStep="GP on Monday. If the breathlessness comes back: call 000")
MARGARET = Persona(
    id="margaret", name="Margaret Reid", age=79, sex="F",
    script="Name is Margaret Reid, 79 year old woman, had a fall at home and hurt her wrist, she is on blood thinners. Came by taxi. Pulse 88, BP 145 over 85, sats 97 percent, pain 5 out of 10.",
    category=3, priorVisits=2, daysSinceLast=58, lastOutcome="Discharged home",
    note="A fall in July, discharged; lives alone, home care package under review", homeX=0.6, homeY=-4.3, careMinutes=150,
    callResult="Home with her daughter for the week. Falls clinic referral sent; GP on Tuesday.",
    nextStep="GP on Tuesday, falls clinic within two weeks. If she falls again: call 000")
ROBERT = Persona(
    id="robert", name="Robert Hale", age=71, sex="M",
    script="Name is Robert Hale, 71 year old man, new confusion for a day, not making sense, his daughter drove him in. Temp 38.2, pulse 98, BP 150 over 88, sats 96 percent.",
    category=3, priorVisits=2, daysSinceLast=23, lastOutcome="Discharged home",
    note="Urinary infection in August, discharged with antibiotics; carer is his daughter", homeX=5.4, homeY=-3.2, careMinutes=150,
    callResult="Home with his daughter, antibiotics started, delirium screen done; GP on Wednesday.",
    nextStep="GP on Wednesday. If the confusion gets worse: call 000")

ALL: list[Persona] = [ALAN, GRACE, MARGARET, ROBERT]


def find(id: str) -> Optional[Persona]:
    return next((p for p in ALL if p.id == id), None)


def random(excluding: Optional[str] = None) -> Persona:
    """A different person each run."""
    pool = [p for p in ALL if p.id != excluding]
    return _random.choice(pool) if pool else ALAN


# Every persona the guided demo can bring in, plus Jess, who is already in the room.
DEMO_RECORDS: list[Record] = [p.record for p in ALL] + [
    Record(name="Jess Tran", age=24, sex="F", priorVisits=2, daysSinceLast=19, lastOutcome="Did not wait",
           priorDNW=True, note="Known to the community mental health team"),
]


def find_record(name: Optional[str]) -> Optional[Record]:
    if name is None:
        return None
    return next((r for r in DEMO_RECORDS if r.name.lower() == name.lower()), None)
