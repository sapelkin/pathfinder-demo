"""The whole document: the simulated department, the clock, settings, the demo, and every action a nurse takes.

A pure-Python class with no UI, timers or speech. The intake
conversation is stateless here (the web client holds the transcript and sends it whole); the guided demo keeps its
own scripted intake in ``demo.py``. ``to_dict``/``from_dict`` round-trip the entire state, RNG included, so a store
can hold it as one JSON document.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from . import clock, eta as eta_engine, metro, network, parser, personas, ranker as ranker_mod, rightdoor, simulator, triage
from .domain import (ArrivalMode, Banner, ClinicalFlag, Cohort, Episode, FollowStatus, FollowTier, Outcome, Stage,
                     TravelMode, Vitals)
from .eta import ETA
from .parser import IntakeForm, VoiceCommand
from .personas import Persona, Record
from .rng import SeededRNG
from .seed import SeedFile
from .simulator import SimConfig, SimEvent, SimState
from .triage import RuleHit
from .units import AppTab, Deployment

START_MINUTE = 5 * 1440 + 14 * 60 + 30  # Saturday 2:30 pm
DAY_START = 5 * 1440  # Saturday 00:00
SPEEDS = [1.0, 10.0, 60.0, 300.0, 1200.0]
BANNER_SECONDS = 6.0

CLOSED_RESULTS = ["Safe at home, will see own GP", "Got care at an urgent care clinic",
                  "Referred to the community team", "Came back and was seen", "Declined follow-up"]

# What "obs from the monitor" reads for the demo.
MONITOR_VITALS = Vitals(pulse=104, systolic=150, diastolic=90, spo2=95, resp=20, temp=36.9, gcs=15, pain=None)


def ms(dt: datetime) -> datetime:
    """Truncated to the millisecond the document stores, so the in-memory clock and the stored one agree."""
    return dt.replace(microsecond=dt.microsecond // 1000 * 1000)


def utcnow() -> datetime:
    return ms(datetime.now(timezone.utc))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class IntakeResult:
    """One parse of the transcript: ``reparse`` plus the voice commands found in it."""

    form: IntakeForm
    hits: list[RuleHit]
    suggested: Optional[int]
    record: Optional[Record]
    commands: list[VoiceCommand]
    monitorVitals: Optional[Vitals]

    def to_dict(self) -> dict[str, Any]:
        return {"form": self.form.to_dict(), "hits": [h.to_dict() for h in self.hits], "suggested": self.suggested,
                "record": self.record.to_dict() if self.record else None, "commands": [c.text for c in self.commands],
                "monitorVitals": self.monitorVitals.to_dict() if self.monitorVitals else None}


@dataclass
class QueuePoint:
    minute: int
    waiting: int


class AppModel:
    def __init__(self, seed: Optional[SeedFile] = None, persona_choice: str = "alan", warm_up: bool = True,
                 hospital_id: str = metro.DEMO_ID):
        self.seed: SeedFile = seed or SeedFile.load()
        self.hospital: metro.Hospital = metro.find(hospital_id, self.seed) or metro.demo_hospital(self.seed)
        self.config = SimConfig(self.seed)
        self.rate_scale = metro.configure(self.config, self.hospital)
        self.metro_cache: Optional[dict[str, Any]] = None  # the measured effect, keyed by hospital and hour
        self.ranker = ranker_mod.FollowUpRanker(self.seed.aggregates.returns, self.seed.aggregates.returns_by_cohort)
        self.sim = SimState(0, SeededRNG(self.seed.sim.seed))
        self.etas: dict[int, ETA] = {}
        self.eta_samples: dict[int, list[int]] = {}
        self.queue_history: list[QueuePoint] = []
        self.deployment = Deployment.full
        self.last_eta = -10_000
        self.staff_rng = SeededRNG(7)
        self.speed = 10.0
        self.running = True
        self.banner: Optional[Banner] = None
        self.banner_at: Optional[datetime] = None
        self.captured_seconds: list[float] = []
        self.last_intake_samples: list[int] = []
        self.persona_choice = persona_choice
        self.persona: Persona = personas.find(persona_choice) or (personas.random() if persona_choice == "random" else personas.ALAN)
        self.speak_feedback = True
        self.show_captions = True
        self.right_door_id: Optional[int] = None
        self.demo: Optional[dict[str, Any]] = None  # the guided demo's state, run by demo.py
        self.wall: Optional[datetime] = None  # an injected wall clock (the browser's), else the system clock
        self.last_tick_utc: datetime = self.now_utc()
        self.version = 0
        if warm_up:
            self.reset()

    def now_utc(self) -> datetime:
        """The wall clock: ``wall`` when a caller set it (Pyodide passes the browser's clientNow), else the system's."""
        return self.wall if self.wall is not None else utcnow()

    # MARK: - Reset and warm-up

    def reset(self, keep_demo: bool = False) -> None:
        """Rebuilds the same Saturday afternoon every time: the week is simulated from Monday 00:00 with a fixed
        seed."""
        if not keep_demo:
            self.demo = None
        s = SimState(0, SeededRNG(self.seed.sim.seed))
        history: list[QueuePoint] = []
        jess_at = START_MINUTE - 110
        liam_at = START_MINUTE - 12
        while s.now < START_MINUTE:
            if s.now == jess_at:
                self._add_jess(s)
            if s.now == liam_at:
                self._add_liam(s)
            simulator.step(s, self.config)
            if s.now >= DAY_START and s.now % 15 == 0:
                history.append(QueuePoint(s.now, len(s.waiting)))
        if self.hospital.id != metro.DEMO_ID:
            metro.apply_room(s, self.hospital, self.config, START_MINUTE)
            if history and history[-1].minute == START_MINUTE:
                history[-1] = QueuePoint(START_MINUTE, len(s.waiting))
        self.sim = s
        self.queue_history = history
        self.metro_cache = None
        self._process_events(announce=False)
        self._resolve_earlier_follow_ups()
        self.staff_rng = SeededRNG(7)
        self.captured_seconds = []
        self.last_intake_samples = []
        self.banner = None
        self.banner_at = None
        self.right_door_id = None
        self.etas, self.eta_samples = eta_engine.estimate_with_samples(self.sim, self.config)
        self.last_eta = self.sim.now
        self.last_tick_utc = self.now_utc()

    def set_hospital(self, hospital_id: str) -> None:
        """Switches the simulated ED: a fresh configuration for that hospital and a rebuilt afternoon. Stops a demo."""
        h = metro.find(hospital_id, self.seed)
        if h is None:
            raise ValueError(f"unknown hospital {hospital_id!r}")
        self.hospital = h
        self.config = SimConfig(self.seed)
        self.rate_scale = metro.configure(self.config, h)
        self.reset(keep_demo=False)

    def _add_jess(self, s: SimState) -> None:
        """Jess came by bus with a panic attack, waits for the mental health team (not the general queue), and gives
        up at 2:56 pm. She lives in Marlow."""
        lat, lon = network.coordinate(-3.7, 2.0)
        e = Episode(id=len(s.episodes), name="Jess T.", age=24, sex="F", cohort=Cohort.mh,
                    complaint="Panic attack, anxious", complaintKey="anxiety", ats=4, arrival=s.now,
                    arrivalMode=ArrivalMode.publicTransport, priorVisits=2, daysSinceLast=19, priorDNW=True,
                    flags=set(), homeLat=lat, homeLon=lon, homeSuburb=network.suburb(-3.7, 2.0, self.config.suburbs))
        e.patience = 136
        e.holdFromCall = True
        e.holdReason = "Waiting for the mental health team"
        e.isHero = True
        e.etaSentAt = s.now + 3
        e.descriptor = "Semi-urgent mental health problem, no immediate risk to self or others"
        s.episodes.append(e)
        s.waiting.append(e.id)

    def _add_liam(self, s: SimState) -> None:
        """Liam was sent to an urgent care clinic from triage, 12 minutes before the demo starts."""
        lat, lon = network.coordinate(-3.3, 3.9)
        e = Episode(id=len(s.episodes), name="Liam K.", age=29, sex="M", cohort=Cohort.other,
                    complaint="Sore throat for 3 days", complaintKey="sore_throat", ats=5, arrival=s.now,
                    arrivalMode=ArrivalMode.walked, priorVisits=0, daysSinceLast=None, priorDNW=False, flags=set(),
                    homeLat=lat, homeLon=lon, homeSuburb=network.suburb(-3.3, 3.9, self.config.suburbs))
        e.stage = Stage.closed
        e.outcome = Outcome.redirected
        e.outcomeAt = s.now
        e.redirectService = network.redirect_target(e)
        e.isHero = True
        s.episodes.append(e)
        s.events.append(SimEvent("redirected", e.id))

    def _resolve_earlier_follow_ups(self) -> None:
        """Follow-ups from earlier in the day are shown as already done, so the list opens on today's live work."""
        rng = SeededRNG(99)
        cutoff = START_MINUTE - 150
        for e in self.sim.episodes:
            f = e.followUp
            at = e.outcomeAt
            if f is None or at is None or e.isHero:
                continue
            if f.tier is FollowTier.autoMessage:
                if at + 60 < START_MINUTE:
                    f.status = FollowStatus.closed
                    f.messageSent = True
                    f.result = "Day-2 check-in message scheduled"
                    f.closedAt = at + 5
            elif at < START_MINUTE - 24 * 60:
                f.attempts = 1 if rng.chance(0.74) else 3
                f.status = FollowStatus.closed
                f.result = rng.element(CLOSED_RESULTS) if f.attempts == 1 else "Not reached after 3 attempts; letter sent to the GP"
                f.closedAt = at + int(rng.uniform() * f.tier.due_minutes)
            elif at < cutoff or at + f.tier.due_minutes * 2 // 3 < START_MINUTE:
                f.attempts = 1
                f.lastAttemptAt = min(START_MINUTE - 5, at + 20 + int(rng.uniform() * 60))
                if rng.chance(0.74):
                    f.status = FollowStatus.closed
                    f.result = rng.element(CLOSED_RESULTS)
                    f.closedAt = at + int(rng.uniform() * (f.tier.due_minutes // 2))
                else:
                    f.status = FollowStatus.noAnswer
                    f.result = "No answer, message sent"
                    f.messageSent = True
                    f.attempts = 2
                    f.lastAttemptAt = START_MINUTE - 10 - int(rng.uniform() * 90)

    # MARK: - Clock

    def advance(self, minutes: int) -> None:
        s = self.sim
        for _ in range(minutes):
            simulator.step(s, self.config)
            if s.now % 15 == 0:
                self.queue_history.append(QueuePoint(s.now, len(s.waiting)))
        self._process_events(announce=True)
        self._work_follow_up_list()
        self.refresh_etas()

    def tick(self, now: datetime, cap: int = 120) -> int:
        """Steps ``floor(elapsed_seconds * speed / 60)`` simulated minutes since the last tick, at most ``cap``, and
        never while paused. The time consumed is kept, so slow speeds accumulate across calls; anything beyond the
        cap is dropped. Returns the minutes stepped."""
        now = ms(now)
        elapsed = (now - self.last_tick_utc).total_seconds()
        if elapsed < 0:
            self.last_tick_utc = now
            return 0
        if not self.running:
            self.last_tick_utc = now
            return 0
        n = int(elapsed * self.speed / 60.0)
        if n <= 0:
            return 0
        if n > cap:
            n = cap
            self.last_tick_utc = now
        else:
            self.last_tick_utc = ms(self.last_tick_utc + timedelta(seconds=n * 60.0 / self.speed))
        self.advance(n)
        if self.banner is not None and self.banner_at is not None and (now - self.banner_at).total_seconds() > BANNER_SECONDS:
            self.banner = None
        return n

    def set_running(self, running: bool) -> None:
        if running and not self.running:
            self.last_tick_utc = self.now_utc()
        self.running = running

    def _work_follow_up_list(self) -> None:
        """The simulated follow-up nurse: works the list for everyone except the demo's own patients, so cases are
        contacted before they fall due (two thirds of the way to the due time)."""
        now = self.sim.now
        for e in self.sim.episodes:
            f = e.followUp
            if f is None or e.isHero or f.status is not FollowStatus.open or f.tier is FollowTier.autoMessage:
                continue
            at = e.outcomeAt
            if at is None or now < at + f.tier.due_minutes * 2 // 3:
                continue
            f.attempts = 1
            f.lastAttemptAt = now
            if self.staff_rng.chance(0.74):
                f.status = FollowStatus.closed
                f.closedAt = now
                f.result = self.staff_rng.element(CLOSED_RESULTS)
            else:
                f.status = FollowStatus.noAnswer
                f.result = "No answer, message sent"
                f.messageSent = True

    def refresh_etas(self, force: bool = False) -> bool:
        """Re-estimates every waiting person's range; every 10 simulated minutes unless forced. Returns whether it ran."""
        if not force and self.sim.now - self.last_eta < 10:
            return False
        self.last_eta = self.sim.now
        self.etas, self.eta_samples = eta_engine.estimate_with_samples(self.sim, self.config)
        return True

    @property
    def clock_text(self) -> str:
        return clock.text(self.sim.now)

    # MARK: - Events

    def _process_events(self, announce: bool) -> None:
        events = list(self.sim.events)
        self.sim.events.clear()
        for ev in events:
            f = self.ranker.assign(self.sim.episodes[ev.id])
            if f is not None:
                self.sim.episodes[ev.id].followUp = f
            if announce:
                self._announce(ev)

    def _announce(self, ev: SimEvent) -> None:
        e = self.sim.episodes[ev.id]
        if ev.kind == "left":
            if self.demo_running and not e.isHero:
                return
            waited = clock.duration((e.outcomeAt if e.outcomeAt is not None else self.sim.now) - e.arrival)
            tier = e.followUp.tier.title.lower() if e.followUp else "follow-through"
            self.show(Banner(f"{e.name} left before being seen, after {waited}. Follow-through: {tier}.",
                             "figure.walk.departure", "warning", ev.id))
        elif ev.kind == "finished":
            if e.isHero and e.outcome is not None:
                self.show(Banner(f"{e.name}: {e.outcome.label.lower()}. Added to Follow-through.", "house.fill", "info", ev.id))

    def show(self, b: Banner) -> None:
        self.banner = b
        self.banner_at = self.now_utc()

    @property
    def demo_running(self) -> bool:
        return bool(self.demo and self.demo.get("running"))

    # MARK: - The right door

    @property
    def right_door_candidates(self) -> list[Episode]:
        """People the right-door screen can plan for: the demo's own patients first, then today's other cases."""
        xs = [e for e in self.sim.episodes
              if e.arrival >= DAY_START or (e.followUp is None or e.followUp.status is not FollowStatus.closed)]
        return sorted(xs, key=lambda e: (0 if e.isHero else 1, -(e.outcomeAt if e.outcomeAt is not None else e.arrival)))

    @property
    def right_door_patient(self) -> Optional[Episode]:
        if self.right_door_id is not None and 0 <= self.right_door_id < len(self.sim.episodes):
            return self.sim.episodes[self.right_door_id]
        c = self.right_door_candidates
        return c[0] if c else None

    def redirect_options(self, e: Episode) -> list[rightdoor.Option]:
        """Open services the triage nurse could redirect to now, ranked for the person by the way they travel; empty
        when the person should stay (see ``redirect_message``)."""
        return rightdoor.plan(e, e.arrivalMode.travel, self.sim.now, rightdoor.Purpose.redirectNow).options[:5]

    def redirect_message(self, e: Episode) -> str:
        b = rightdoor.blockers(e)
        if b:
            return ". ".join(b) + ". Stays in the ED."
        mode = e.arrivalMode.travel
        where = e.homeSuburb or "home"
        if not self.redirect_options(e):
            return f"Nothing suitable is open within {int(rightdoor.max_redirect_minutes(mode))} min {mode.short} of {where} right now."
        return f"Open now, within {int(rightdoor.max_redirect_minutes(mode))} min {mode.short} of {where}."

    def right_door(self, id: int, purpose: Optional[rightdoor.Purpose] = None, mode: Optional[TravelMode] = None
                   ) -> dict[str, Any]:
        """The right-door screen's data for one person: the plan, its blockers, the ring search and the travel field.
        The app decides both defaults from the record: travel follows how the person got to the ED, and someone still
        waiting is a "redirect now" question while everyone else is asked about next time."""
        e = self.sim.episodes[id]
        self.right_door_id = id
        mode = mode or e.arrivalMode.travel
        purpose = purpose or (rightdoor.Purpose.redirectNow if e.stage is Stage.waiting else rightdoor.Purpose.nextTime)
        plan = rightdoor.plan(e, mode, self.sim.now, purpose)
        where = e.homeSuburb or "home"
        if purpose is rightdoor.Purpose.redirectNow:
            limit = int(rightdoor.max_redirect_minutes(mode))
            if plan.blockers:
                message = ". ".join(plan.blockers) + ". Stays in the ED."
            elif not plan.options:
                message = f"Nothing suitable is open within {limit} min {mode.short} of {where} right now."
            else:
                message = f"Open now, within {limit} min {mode.short} of {where}."
        else:
            message = (f"For follow-up, from {where} {mode.short}" if plan.edFirst
                       else f"Where to go next time, from {where} {mode.short}")
        t = self.sim.now
        ed_index = next((i for i, o in enumerate(plan.options) if o.service.kind is network.Kind.ed), None)
        options = [o.to_dict(mode, t, i + 1, pinned=plan.edFirst and i == ed_index) for i, o in enumerate(plan.options)]
        px, py = network.xy(e.homeLat, e.homeLon)
        return {
            "episode": self.episode_view(e), "purpose": purpose.value, "mode": mode.value, "blockers": plan.blockers,
            "message": message, "edFirst": plan.edFirst, "busWait": rightdoor.bus_wait(t),
            "options": [o for o in options if o["minutes"] is not None],
            "remote": [o for o in options if o["minutes"] is None],
            "search": plan.search.to_dict(),
            "field": [{"hex": h.to_dict(), "minutes": plan.field.minutes[h]} for h in plan.field.order],
            "home": plan.search.home.to_dict(), "homeCoord": [e.homeLat, e.homeLon], "homeXY": [px, py],
        }

    # MARK: - Lists for the screens

    @property
    def waiting_sorted(self) -> list[Episode]:
        now = self.sim.now
        c = self.config
        xs = [self.sim.episodes[i] for i in self.sim.waiting]
        return sorted(xs, key=lambda e: (1 if e.holdFromCall else 0, -simulator.priority(e, now, c), e.ats))

    @property
    def in_care_count(self) -> int:
        return len(self.sim.inCare)

    @property
    def longest_wait(self) -> int:
        return max((self.sim.now - self.sim.episodes[i].arrival for i in self.sim.waiting), default=0)

    def may_leave_soon(self, e: Episode) -> bool:
        waited = self.sim.now - e.arrival
        median = self.config.patienceMedian[e.ats - 1]
        return e.stage is Stage.waiting and e.ats >= 3 and waited > 0.6 * median

    @property
    def follow_cases(self) -> list[Episode]:
        """Follow-through cases from the last 24 hours, plus anything still open."""
        now = self.sim.now
        xs = [e for e in self.sim.episodes if e.followUp is not None and e.outcomeAt is not None
              and (now - e.outcomeAt <= 24 * 60 or e.followUp.status is not FollowStatus.closed)]
        return ranker_mod.sort(xs)

    def open_cases(self, tier: FollowTier) -> list[Episode]:
        return [e for e in self.follow_cases if e.followUp and e.followUp.tier is tier and e.followUp.status is not FollowStatus.closed]

    @property
    def closed_cases(self) -> list[Episode]:
        xs = [e for e in self.follow_cases if e.followUp and e.followUp.status is FollowStatus.closed
              and e.followUp.tier is not FollowTier.autoMessage]
        return sorted(xs, key=lambda e: -(e.followUp.closedAt or 0))

    @property
    def open_action_count(self) -> int:
        return sum(1 for e in self.follow_cases
                   if (e.followUp.tier if e.followUp else FollowTier.autoMessage) is not FollowTier.autoMessage
                   and (e.followUp is None or e.followUp.status is not FollowStatus.closed))

    def due_text(self, e: Episode) -> str:
        f = e.followUp
        at = e.outcomeAt
        if f is None or at is None:
            return ""
        due = at + f.tier.due_minutes
        if f.status is FollowStatus.closed:
            return f"Done {clock.time(f.closedAt if f.closedAt is not None else due)}"
        if f.status is FollowStatus.noAnswer and f.lastAttemptAt is not None:
            retry = f.lastAttemptAt + 120
            return f"Try again now (attempt {f.attempts + 1})" if retry <= self.sim.now else f"Try again at {clock.time(retry)}"
        if f.tier is FollowTier.autoMessage:
            return f"Sends {clock.text(due)}"
        return f"Overdue by {clock.duration(self.sim.now - due)}" if due < self.sim.now else f"Due by {clock.time(due)}"

    # MARK: - Intake

    def parse_intake(self, transcript: str, typed: str = "", monitor: Optional[Vitals] = None,
                     record_looked_up: bool = False) -> IntakeResult:
        """``reparse`` and ``IntakeParser.commands`` for one transcript. The record is found by the name heard;
        ``record_looked_up`` is accepted for parity with the app's one-shot lookup and changes nothing. If the
        commands include "obs from the monitor" and no monitor vitals were given, the demo monitor's are used."""
        commands = parser.commands(transcript)
        if monitor is None and any(c.kind is parser.CommandKind.fromMonitor for c in commands):
            monitor = Vitals(**MONITOR_VITALS.to_dict())
        f = parser.parse(transcript + " " + typed)
        if monitor is not None:
            merged = Vitals(**monitor.to_dict())
            merged.merge(f.vitals)
            f.vitals = merged
        record = personas.find_record(f.name)
        if record is not None:
            f.age = f.age if f.age is not None else record.age
            f.sex = f.sex if f.sex is not None else record.sex
        hits = triage.evaluate(f)
        return IntakeResult(form=f, hits=hits, suggested=triage.suggestion(hits), record=record, commands=commands,
                            monitorVitals=monitor)

    def probe_episode(self, ats: int) -> Episode:
        """A new arrival at this category, arriving now, for the wait model to follow (id -1)."""
        return Episode(id=-1, name="", age=0, sex="", cohort=Cohort.other, complaint="", complaintKey="", ats=ats,
                       arrival=self.sim.now, arrivalMode=ArrivalMode.car, priorVisits=0, daysSinceLast=None,
                       priorDNW=False, flags=set(), homeLat=0, homeLon=0)

    def eta_for(self, ats: int) -> tuple[Optional[ETA], list[int]]:
        """``confirmATS``: the range for a new arrival at this category, from the room as it stands."""
        etas, samples = eta_engine.estimate_with_samples(self.sim, self.config, extra=self.probe_episode(ats))
        self.last_intake_samples = samples.get(-1, [])
        return etas.get(-1), self.last_intake_samples

    @staticmethod
    def spoken(e: ETA) -> str:
        lo = eta_engine.round5(e.p10)
        hi = max(lo + 5, eta_engine.round5(e.p90))
        return f"under {hi} minutes" if lo == 0 else f"{lo} to {hi} minutes"

    @property
    def intake_message_template(self) -> str:
        return (f"Hi {{first}}, you're checked in at {self.hospital.name}. Expected time to be seen: {{eta}}. "
                "We'll text you if that changes. If you feel worse, tell the triage nurse straight away. "
                "If you decide to leave, please tell us first.")

    def intake_message(self, first: str, e: Optional[ETA]) -> str:
        hello = "Hi" if not first else f"Hi {first}"
        return (f"{hello}, you're checked in at {self.hospital.name}. Expected time to be seen: "
                f"{e.range_text if e else 'soon'}. We'll text you if that changes. If you feel worse, tell the "
                "triage nurse straight away. If you decide to leave, please tell us first.")

    def finish_intake(self, transcript: str, typed: str = "", confirmed: Optional[int] = None, message_sent: bool = False,
                      started_at: Optional[datetime] = None, monitor: Optional[Vitals] = None,
                      eta: Optional[ETA] = None, now: Optional[datetime] = None) -> Optional[Episode]:
        """``finishIntake``: adds the person to the waiting room. Returns None when no category is confirmed or
        suggested. ``now`` is the wall clock the capture time is measured against (the request time by default)."""
        r = self.parse_intake(transcript, typed, monitor)
        a = confirmed if confirmed is not None else r.suggested
        if a is None:
            return None
        if eta is None and confirmed is not None:
            eta, _ = self.eta_for(confirmed)
        f = r.form
        rec = r.record
        age = f.age if f.age is not None else (rec.age if rec else 40)
        cohort = Cohort.mh if triage.is_mental_health(f) else (Cohort.p65 if age >= 65 else Cohort.other)
        flags: set[ClinicalFlag] = set()
        if "suicidal" in f.mh:
            flags.add(ClinicalFlag.suicidalIdeation)
        if "self_harm_act" in f.mh:
            flags.add(ClinicalFlag.selfHarm)
        if "psychosis" in f.mh:
            flags.add(ClinicalFlag.psychosis)
        if "agitation" in f.mh or "aggression" in f.mh:
            flags.add(ClinicalFlag.agitation)
        if "wont_wait" in f.mh:
            flags.add(ClinicalFlag.notLikelyToWait)
        if f.complaintKey == "intox":
            flags.add(ClinicalFlag.drugsAlcohol)
        full_name = f.name or (rec.name if rec else None)
        if full_name is None:
            short = "New patient"
        else:
            parts = [p for p in full_name.split(" ") if p]
            short = f"{parts[0]} {parts[1][:1]}." if len(parts) > 1 else full_name
        id = len(self.sim.episodes)
        # A known record carries an address; anyone else new is placed near the ED for the demo.
        if rec is not None and rec.homeX is not None and rec.homeY is not None:
            hx, hy = rec.homeX, rec.homeY
        else:
            hx, hy = 0.9, 1.3
        lat, lon = network.coordinate(hx, hy)
        suburb = network.suburb(hx, hy, self.config.suburbs)
        complaint = " ".join(x for x in [f.complaint or "Unwell", f"for {f.duration}" if f.duration else None] if x)
        e = Episode(id=id, name=short, age=age, sex=f.sex or (rec.sex if rec else "F"), cohort=cohort, complaint=complaint,
                    complaintKey=f.complaintKey or "unwell", ats=a, arrival=self.sim.now,
                    arrivalMode=f.arrivalMode or ArrivalMode.car, priorVisits=rec.priorVisits if rec else 0,
                    daysSinceLast=rec.daysSinceLast if rec else None, priorDNW=rec.priorDNW if rec else False,
                    flags=flags, homeLat=lat, homeLon=lon, homeSuburb=suburb)
        e.patience = 100_000
        e.isHero = True
        e.vitals = f.vitals
        e.descriptor = next((h.text for h in r.hits if h.ats == a), None)
        e.transcript = transcript
        e.intakeSeconds = max(0.0, ((now or self.now_utc()) - started_at).total_seconds()) if started_at else 0.0
        e.etaConsent = message_sent
        e.etaSentAt = self.sim.now if message_sent else None
        if rec is not None and rec.scriptedCareMinutes is not None:
            e.plannedOutcome = Outcome.discharged
            e.scriptedCareMinutes = rec.scriptedCareMinutes
        self.sim.episodes.append(e)
        self.sim.waiting.append(id)
        self.captured_seconds.append(e.intakeSeconds or 0.0)
        self.refresh_etas(force=True)
        tail = f" Expected to be seen in {eta.range_text}." if eta else ""
        self.show(Banner(f"{e.name} added to the waiting room, category {a}.{tail}", "checkmark.circle.fill", "success", id))
        return e

    def redirect_from_intake(self, transcript: str, typed: str = "", confirmed: Optional[int] = None,
                             started_at: Optional[datetime] = None, monitor: Optional[Vitals] = None) -> Episode:
        """``redirectFromIntake``: the person is sent elsewhere from triage and follow-through checks they got there."""
        r = self.parse_intake(transcript, typed, monitor)
        f = r.form
        age = f.age if f.age is not None else (r.record.age if r.record else 40)
        cohort = Cohort.mh if triage.is_mental_health(f) else (Cohort.p65 if age >= 65 else Cohort.other)
        id = len(self.sim.episodes)
        lat, lon = network.coordinate(0.9, 1.3)
        a = confirmed if confirmed is not None else (r.suggested if r.suggested is not None else 5)
        e = Episode(id=id, name=f.name or "New patient", age=age, sex=f.sex or "F", cohort=cohort,
                    complaint=f.complaint or "Unwell", complaintKey=f.complaintKey or "unwell", ats=a,
                    arrival=self.sim.now, arrivalMode=f.arrivalMode or ArrivalMode.car, priorVisits=0, daysSinceLast=None,
                    priorDNW=False, flags=set(), homeLat=lat, homeLon=lon,
                    homeSuburb=network.suburb(0.9, 1.3, self.config.suburbs))
        e.stage = Stage.closed
        e.outcome = Outcome.redirected
        e.outcomeAt = self.sim.now
        e.redirectService = network.redirect_target(e)
        e.isHero = True
        e.intakeSeconds = max(0.0, (self.now_utc() - started_at).total_seconds()) if started_at else 0.0
        e.followUp = self.ranker.assign(e)
        self.sim.episodes.append(e)
        self.captured_seconds.append(e.intakeSeconds or 0.0)
        self.show(Banner(f"{e.name} redirected to {e.redirectService or 'another service'}. Follow-through will check they got there.",
                         "arrow.uturn.right.circle.fill", "info", id))
        return e

    # MARK: - Outcomes and follow-through actions

    def record_outcome(self, id: int, outcome: Outcome, reason: Optional[str] = None, service: Optional[str] = None) -> None:
        if id in self.sim.waiting:
            self.sim.waiting.remove(id)
        if id in self.sim.inCare:
            self.sim.inCare.remove(id)
        e = self.sim.episodes[id]
        e.stage = Stage.closed
        e.outcome = outcome
        e.outcomeAt = self.sim.now
        if reason is not None:
            e.leaveReason = reason
        if service is not None:
            e.redirectService = service
        e.followUp = self.ranker.assign(e)
        self.refresh_etas(force=True)

    def record_contact(self, id: int, reached: bool, result: str, next_step: Optional[str] = None,
                       reason: Optional[str] = None) -> bool:
        e = self.sim.episodes[id]
        f = e.followUp
        if f is None:
            return False
        f.attempts += 1
        f.lastAttemptAt = self.sim.now
        if reached:
            f.status = FollowStatus.closed
            f.result = result
            f.nextStep = next_step
            f.closedAt = self.sim.now
        else:
            f.status = FollowStatus.noAnswer
            f.result = "No answer, message sent. Try again in 2 hours."
            f.messageSent = True
        if reason is not None:
            e.leaveReason = reason
        return True

    def send_follow_message(self, id: int) -> None:
        f = self.sim.episodes[id].followUp
        if f is not None:
            f.messageSent = True

    def toggle_alo(self, id: int) -> None:
        f = self.sim.episodes[id].followUp
        if f is not None:
            f.aloOffered = not f.aloOffered

    # MARK: - Impact numbers (today, in the simulated ED)

    @property
    def today_arrivals(self) -> list[Episode]:
        return [e for e in self.sim.episodes if e.arrival >= DAY_START]

    @property
    def arrivals_by_hour(self) -> list[dict[str, Any]]:
        """Arrivals in each hour of the simulated day so far, and what the weekly template expects for that hour."""
        now_hour = (self.sim.now - DAY_START) // 60
        counts = [0] * 24
        for e in self.today_arrivals:
            h = (e.arrival - DAY_START) // 60
            if 0 <= h < 24:
                counts[h] += 1
        return [{"hour": h, "actual": counts[h] if h <= now_hour else 0,
                 "expected": self.config.weekly * self.config.shape[clock.hour_of_week(DAY_START + h * 60)]}
                for h in range(24)]

    @property
    def next_to_be_called(self) -> Optional[tuple[Episode, list[int]]]:
        """The person the room will call next, and the wait model's futures for them."""
        for e in self.waiting_sorted:
            if not e.holdFromCall and self.eta_samples.get(e.id):
                return e, self.eta_samples[e.id]
        return None

    @property
    def today_dnw_rate(self) -> float:
        a = self.today_arrivals
        if not a:
            return 0.0
        return sum(1 for e in a if e.outcome is Outcome.didNotWait) / len(a)

    @property
    def eta_share_waiting(self) -> float:
        if not self.sim.waiting:
            return 0.0
        return sum(1 for i in self.sim.waiting if self.sim.episodes[i].etaSentAt is not None) / len(self.sim.waiting)

    @property
    def r_contact_share(self) -> tuple[int, int, int]:
        """People who left or were redirected in the last 24 hours: contacted (reached or tried), out of those whose
        contact is due, plus how many are not yet due."""
        r = [e for e in self.follow_cases if e.outcome in (Outcome.didNotWait, Outcome.leftAtOwnRisk, Outcome.redirected)]

        def contacted(e: Episode) -> bool:
            return (e.followUp.attempts if e.followUp else 0) > 0 or (e.followUp is not None and e.followUp.status is FollowStatus.closed)

        due = [e for e in r if contacted(e) or (e.outcomeAt or 0) + (e.followUp.tier.due_minutes if e.followUp else 0) <= self.sim.now]
        return (sum(1 for e in due if contacted(e)), len(due), len(r) - len(due))

    @property
    def named_next_step_share(self) -> tuple[int, int]:
        d = [e for e in self.follow_cases if e.outcome is Outcome.discharged and e.cohort is Cohort.p65]
        done = sum(1 for e in d if e.followUp and e.followUp.status is FollowStatus.closed)
        return (done, len(d))

    @property
    def metro_key(self) -> str:
        return f"{self.hospital.id}:{self.sim.now // 60}"

    def ensure_metro(self) -> bool:
        """Measures the redirect gate's effect for this hospital and hour unless it is cached. Returns whether it ran."""
        if self.metro_cache is not None and self.metro_cache.get("key") == self.metro_key:
            return False
        self.metro_cache = {"key": self.metro_key, "result": metro.measure_effect(self)}
        return True

    def kpi(self) -> dict[str, Any]:
        self.ensure_metro()
        done, total, not_due = self.r_contact_share
        n_done, n_total = self.named_next_step_share
        return {
            "captureSeconds": list(self.captured_seconds),
            "etaShareWaiting": self.eta_share_waiting,
            "todayDNWRate": self.today_dnw_rate,
            "rContactShare": {"done": done, "total": total, "notYetDue": not_due},
            "namedNextStepShare": {"done": n_done, "total": n_total},
            "returns": None,
            "arrivalsByHour": self.arrivals_by_hour,
            "baselines": dict(self.seed.kpi_statewide.raw),
            "weekly": None,
            "queueHistory": [{"minute": p.minute, "waiting": p.waiting} for p in self.queue_history],
            "metro": dict(self.metro_cache["result"]) if self.metro_cache else None,
        }

    # MARK: - Views and the document

    def episode_view(self, e: Episode) -> dict[str, Any]:
        d = e.to_dict()
        eta = self.etas.get(e.id)
        d["eta"] = eta.to_dict() if eta else None
        if e.stage is Stage.waiting:
            seen_at = self.sim.now
        elif e.calledAt is not None:
            seen_at = e.calledAt
        else:
            seen_at = e.outcomeAt if e.outcomeAt is not None else self.sim.now
        d["waitedMinutes"] = max(0, seen_at - e.arrival)
        d["targetMinutes"] = int(self.config.targets[e.ats - 1])
        d["mayLeaveSoon"] = self.may_leave_soon(e)
        d["dueText"] = self.due_text(e) if e.followUp else None
        d["outcomeLabel"] = e.outcome.label if e.outcome else None
        d["arrivalModeShort"] = e.arrivalMode.short
        d["travel"] = e.arrivalMode.travel.value
        d["problem"] = e.problem
        d["firstName"] = e.first_name
        d["cohortLabel"] = e.cohort.label
        d["flagLabels"] = [f.label for f in sorted(e.flags, key=lambda f: f.value)]
        d["isHighRisk"] = any(f.is_high_risk for f in e.flags)
        return d

    def settings_dict(self) -> dict[str, Any]:
        return {"speed": self.speed, "running": self.running, "deployment": self.deployment.value,
                "personaChoice": self.persona_choice, "showCaptions": self.show_captions, "speakFeedback": self.speak_feedback}

    def state(self) -> dict[str, Any]:
        """The published properties, as the contract's ``State``."""
        waiting = [self.episode_view(e) for e in self.waiting_sorted]
        follow = [self.episode_view(e) for e in self.follow_cases]
        nxt = self.next_to_be_called
        return {
            "now": self.sim.now, "clockText": self.clock_text, "speed": self.speed, "running": self.running,
            "deployment": self.deployment.value, "lastTickUtc": iso(self.last_tick_utc), "version": self.version,
            "ed": {"name": self.hospital.name, "simulated": True},
            "hospital": self.hospital_dict(),
            "counters": {"waiting": len(self.sim.waiting), "inCare": self.in_care_count, "longestWait": self.longest_wait,
                         "mayLeave": sum(1 for v in waiting if v["mayLeaveSoon"])},
            "waiting": waiting, "followCases": follow, "openActionCount": self.open_action_count,
            "rightDoorCandidates": [{"id": e.id, "name": e.name, "age": e.age, "isHero": e.isHero,
                                     "outcome": e.outcome.value if e.outcome else None, "stage": e.stage.value,
                                     "homeSuburb": e.homeSuburb, "arrivalModeShort": e.arrivalMode.short}
                                    for e in self.right_door_candidates],
            "rightDoorId": self.right_door_patient.id if self.right_door_patient else None,
            "queueHistory": [{"minute": p.minute, "waiting": p.waiting} for p in self.queue_history],
            "nextToBeCalled": {"id": nxt[0].id, "samples": list(nxt[1])} if nxt else None,
            "banner": self.banner.to_dict() if self.banner else None,
            "persona": self.persona.to_dict(), "personaChoice": self.persona_choice,
            "showCaptions": self.show_captions, "speakFeedback": self.speak_feedback,
            "tabs": [t.value for t in AppTab.tabs(self.deployment)],
            "demo": self.demo_view(),
            "intakeMessageTemplate": self.intake_message_template,
        }

    def hospital_dict(self) -> dict[str, Any]:
        h = self.hospital
        return {"id": h.id, "name": h.name, "short": h.short,
                "published": {"waiting": h.waiting, "inEd": h.in_ed, "t4AvgWaitMin": h.t4_avg_wait_min},
                "source": metro.source(), "rateScale": round(self.rate_scale, 3)}

    def network_dict(self) -> dict[str, Any]:
        return network.to_dict(self.config.suburbs, self.hospital.name)

    def demo_view(self) -> Optional[dict[str, Any]]:
        from .demo import view  # the demo module builds on this one
        return view(self) if self.demo else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sim": self.sim.to_dict(),
            "etas": {str(k): v.to_dict() for k, v in self.etas.items()},
            "etaSamples": {str(k): v for k, v in self.eta_samples.items()},
            "queueHistory": [[p.minute, p.waiting] for p in self.queue_history],
            "deployment": self.deployment.value, "lastETA": self.last_eta, "staffRNG": self.staff_rng.state,
            "speed": self.speed, "running": self.running,
            "banner": self.banner.to_dict() if self.banner else None,
            "bannerAt": iso(self.banner_at) if self.banner_at else None,
            "capturedSeconds": list(self.captured_seconds), "lastIntakeSamples": list(self.last_intake_samples),
            "personaChoice": self.persona_choice, "personaId": self.persona.id,
            "speakFeedback": self.speak_feedback, "showCaptions": self.show_captions,
            "rightDoorId": self.right_door_id, "demo": self.demo,
            "lastTickUtc": iso(self.last_tick_utc), "version": self.version,
            "hospitalId": self.hospital.id, "metroCache": self.metro_cache,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], seed: Optional[SeedFile] = None) -> "AppModel":
        m = cls(seed=seed, persona_choice=d.get("personaChoice", "alan"), warm_up=False,
                hospital_id=d.get("hospitalId", metro.DEMO_ID))
        m.metro_cache = d.get("metroCache")
        m.sim = SimState.from_dict(d["sim"])
        m.etas = {int(k): ETA.from_dict(v) for k, v in d.get("etas", {}).items()}
        m.eta_samples = {int(k): list(v) for k, v in d.get("etaSamples", {}).items()}
        m.queue_history = [QueuePoint(int(a), int(b)) for a, b in d.get("queueHistory", [])]
        m.deployment = Deployment(d.get("deployment", "full"))
        m.last_eta = int(d.get("lastETA", -10_000))
        m.staff_rng.state = int(d.get("staffRNG", SeededRNG(7).state))
        m.speed = float(d.get("speed", 10.0))
        m.running = bool(d.get("running", True))
        m.banner = Banner.from_dict(d["banner"]) if d.get("banner") else None
        m.banner_at = parse_iso(d["bannerAt"]) if d.get("bannerAt") else None
        m.captured_seconds = [float(x) for x in d.get("capturedSeconds", [])]
        m.last_intake_samples = [int(x) for x in d.get("lastIntakeSamples", [])]
        m.persona = personas.find(d.get("personaId", "alan")) or personas.ALAN
        m.speak_feedback = bool(d.get("speakFeedback", True))
        m.show_captions = bool(d.get("showCaptions", True))
        m.right_door_id = d.get("rightDoorId")
        m.demo = d.get("demo")
        m.last_tick_utc = ms(parse_iso(d["lastTickUtc"])) if d.get("lastTickUtc") else m.now_utc()
        m.version = int(d.get("version", 0))
        return m
