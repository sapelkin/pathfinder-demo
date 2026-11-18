"""The pitch story, played by the server itself so every run is identical (about 80 seconds).

A step machine driven by wall-clock time: the client ticks,
and each tick applies every step whose moment has come. Dictation goes through the same parser as live dictation,
commands through the same handlers, and the waiting room keeps running. The patient is the model's persona; the
narrated variant is the explainer film's version: scenes whose lengths come from the
narration clips, every step timed from the start, and ``PATHFINDER_*`` log lines in the exact format
``tools/make_explainer.py`` reads, stored under ``demo.log`` and printed to stdout.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from . import eta as eta_engine, network, parser, personas, rightdoor
from .domain import Outcome, Vitals
from .eta import ETA
from .model import MONITOR_VITALS, AppModel, iso, ms, parse_iso
from .units import ALL as UNITS, Deployment

WORD_SECONDS = 0.26
HERO_SCRIPT = personas.ALAN.script

Step = dict[str, Any]


def _caption(text: Optional[str]) -> Step:
    return {"do": "caption", "text": text}


def _pause(seconds: float) -> Step:
    return {"do": "pause", "seconds": seconds}


def _dictate(text: str) -> Step:
    return {"do": "dictate", "text": text}


def _wait_until(cond: str, timeout: float) -> Step:
    return {"do": "waitUntil", "cond": cond, "timeout": timeout}


def _set(**kw: Any) -> Step:
    return {"do": "set", **kw}


def _jess(m: AppModel):
    return next((e for e in m.sim.episodes if e.name == "Jess T."), None)


def _hero(m: AppModel):
    p = m.persona
    return next((e for e in m.sim.episodes if e.isHero and e.name == p.short), None)


def script(m: AppModel) -> list[Step]:
    """The steps, in order. Built fresh on every tick so captions can read the live state when they are applied."""
    p = m.persona
    hero = _hero(m)
    travel = hero.arrivalMode.travel.short if hero else "by car"
    return [
        _caption(f"Saturday 2:30 pm at a busy metro ED. {len(m.sim.waiting)} people are waiting to be seen."),
        _pause(4),
        # 1. Front door: dictation fills the form and finds the record.
        {"do": "beginIntake"},
        _pause(1.5),
        _caption("The triage nurse speaks. Pathfinder fills the form and finds the record."),
        _dictate(p.script),
        _pause(2.5),
        # 2. The nurse confirms the suggested category by voice.
        _caption(f"It suggests category {p.category} with the published descriptor. The nurse confirms by voice."),
        _dictate(f" Confirm category {p.category}."),
        _pause(3.5),
        # 3. Expected time to be seen, sent by text.
        _caption(f"{p.first} gets {p.his} expected time to be seen by text, from simulated futures of this waiting room."),
        _dictate(" Send the message."),
        _pause(4),
        {"do": "hideMessage"},
        _pause(0.8),
        _dictate(" Add to the waiting room."),
        _pause(2.5),
        # 4. Time passes. Jess, waiting for the mental health team after a panic attack, gives up and leaves.
        _caption("Time-lapse. Jess, 24, came in with a panic attack and has waited almost two hours for the mental health team."),
        _set(speed=300),
        _wait_until("jessLeft", 20),
        _set(speed=10),
        _caption("Jess leaves without being seen. Pathfinder puts her straight on the follow-through list."),
        _pause(3.5),
        # 5. Follow-through: the call happens within the hour, not the next business day.
        _set(tab="followThrough"),
        _caption("One ranked list for everyone who went home or left, highest risk first."),
        _pause(4),
        {"do": "requireJess"},
        _set(followId="jess"),
        _caption("A mental health presentation, and she has left before: moderate risk under the WA did-not-wait policy. Call today."),
        _pause(5),
        _set(callingId="jess"),
        _caption("The follow-up nurse calls, with the script and the right door on screen."),
        _pause(3),
        _set(callingId=None),
        {"do": "contact", "who": "jess", "reached": True,
         "result": "Safe at home and calmer. Left because the wait felt too long. Going to the Safe Haven café tonight.",
         "nextStep": "GP on Monday for a mental health care plan", "reason": "Wait too long"},
        _caption("Reached within minutes: safe, reason recorded, GP booked for a care plan."),
        _pause(5),
        # 6. The persona is seen, treated and sent home, and gets a named next step.
        _set(followId=None),
        _caption(f"Meanwhile {p.first} is seen within {p.his} range, treated, and sent home."),
        _set(speed=1200),
        _wait_until("heroDischarged", 25),
        _set(speed=10),
        _pause(2),
        {"do": "requireHero"},
        _set(followId="hero"),
        _caption(f"{p.first}, {p.age}, third visit this year: Pathfinder checks {p.he} has a named next step, not just a discharge letter."),
        _pause(6),
        {"do": "contact", "who": "hero", "reached": True, "result": p.callResult, "nextStep": p.nextStep, "reason": None},
        _pause(3.5),
        # 7. The right door: a ride-share style search from the persona's home, then the numbers.
        _set(followId=None),
        {"do": "openRightDoor"},
        _caption(f"Next time, the right door: from {p.first}'s home, ring by ring like a ride-share search, then travel time {travel}."),
        _pause(7.5),
        _set(tab="impact"),
        _caption("Every step is counted: capture time, expected times sent, walk-outs, contacts within 24 hours."),
        _pause(6),
        _caption(None),
        {"do": "end"},
    ]


CONDITIONS: dict[str, Callable[[AppModel], bool]] = {
    "jessLeft": lambda m: any(e.name == "Jess T." and e.outcome is Outcome.didNotWait for e in m.sim.episodes),
    "heroDischarged": lambda m: any(e.isHero and e.name == m.persona.short and e.outcome is Outcome.discharged
                                    for e in m.sim.episodes),
}


# MARK: Control

def start(m: AppModel, narrated: bool = False, now: Optional[datetime] = None,
          durations: Optional[list[float]] = None) -> None:
    """``runGuidedDemo``, or ``runNarratedDemo(durations)`` when ``narrated`` (8 or 10 scene lengths in seconds)."""
    now = ms(now) if now else m.now_utc()
    if narrated:
        if durations is None or len(durations) not in (8, 10) or any(not x > 0 for x in durations):
            raise ValueError("the narrated demo needs 8 or 10 scene lengths in seconds")
        m.persona = personas.ALAN
        m.show_captions = False
    elif m.persona_choice == "random":
        m.persona = personas.random(excluding=m.persona.id)
    m.reset(keep_demo=True)
    m.speed = 10
    m.running = True
    m.last_tick_utc = now
    m.demo = {
        "running": True, "finished": False, "narrated": narrated, "personaId": m.persona.id, "step": 0,
        "stepStartedUtc": iso(now), "caption": None, "tab": "frontDoor", "followId": None, "callingId": None,
        "rightDoorId": None, "listening": False, "intake": None, "showUnits": False,
        "mode": "narrated" if narrated else "guided", "startedUtc": iso(now),
        "durations": [float(x) for x in durations] if narrated else None, "log": [],
    }
    if narrated:
        _mark(m, "start")
        _emit(m, "PATHFINDER_WAITING", f"{len(m.sim.waiting)} {m.in_care_count}")
    run(m, now)


def stop(m: AppModel) -> None:
    if m.demo is not None:
        m.demo["running"] = False
        m.demo["caption"] = None
        m.demo["listening"] = False
    m.speed = 10


def _finish(m: AppModel, d: dict[str, Any]) -> None:
    d["running"] = False
    d["finished"] = True
    d["caption"] = None
    d["listening"] = False
    d["tab"] = "frontDoor"


def run(m: AppModel, now: datetime) -> None:
    """Applies every step whose moment has come. Call after the simulation has been stepped for this tick."""
    d = m.demo
    if not d or not d.get("running"):
        return
    d["nowUtc"] = iso(now)
    if d.get("mode") == "narrated":
        _run_narrated(m, d, now)
        return
    guard = 0
    while guard < 500:
        guard += 1
        steps = script(m)
        i = int(d["step"])
        if i >= len(steps):
            _finish(m, d)
            return
        st = steps[i]
        started = parse_iso(d["stepStartedUtc"])
        elapsed = (now - started).total_seconds()
        kind = st["do"]
        if kind == "pause":
            if elapsed < st["seconds"]:
                return
            _next(d, started + timedelta(seconds=st["seconds"]))
        elif kind == "dictate":
            words = [w for w in st["text"].split(" ") if w]
            done = min(len(words), int(elapsed / WORD_SECONDS) + 1)
            intake = d.get("intake")
            if intake is not None and intake.get("open"):
                d["listening"] = True
                base = intake.get("dictatedFrom", "")
                current = base
                for w in words[:done]:
                    current += ("" if not current else " ") + w
                _update_transcript(m, d, current)
            if elapsed < len(words) * WORD_SECONDS:
                return
            d["listening"] = False
            if intake is not None:
                intake["dictatedFrom"] = intake.get("transcript", "")
            _next(d, started + timedelta(seconds=len(words) * WORD_SECONDS))
        elif kind == "waitUntil":
            if CONDITIONS[st["cond"]](m) or elapsed > st["timeout"]:
                _next(d, now)
            else:
                return
        else:
            if not _apply(m, d, st, now):
                _finish(m, d)
                return
            _next(d, started)


def _next(d: dict[str, Any], started_at: datetime) -> None:
    d["step"] = int(d["step"]) + 1
    d["stepStartedUtc"] = iso(started_at)


def _apply(m: AppModel, d: dict[str, Any], st: Step, now: datetime) -> bool:
    """An instantaneous step. Returns False when the demo must end (a guard failed, or the script is over)."""
    kind = st["do"]
    if kind == "caption":
        d["caption"] = st["text"]
    elif kind == "beginIntake":
        d["intake"] = {"open": True, "scripted": True, "startedAtUtc": iso(now), "transcript": "", "dictatedFrom": "",
                       "commandsRun": 0, "confirmed": None, "eta": None, "messageSent": False, "showMessage": False,
                       "monitor": None, "heroId": None}
    elif kind == "hideMessage":
        if d.get("intake"):
            d["intake"]["showMessage"] = False
    elif kind == "set":
        for k, v in st.items():
            if k == "do":
                continue
            if k == "speed":
                m.speed = float(v)
            elif k in ("followId", "callingId"):
                d[k] = _resolve(m, v)
            else:
                d[k] = v
    elif kind == "requireJess":
        return _jess(m) is not None
    elif kind == "requireHero":
        return _hero(m) is not None
    elif kind == "contact":
        e = _jess(m) if st["who"] == "jess" else _hero(m)
        if e is None:
            return False
        m.record_contact(e.id, reached=st["reached"], result=st["result"], next_step=st.get("nextStep"),
                         reason=st.get("reason"))
    elif kind == "openRightDoor":
        e = _hero(m)
        if e is None:
            return False
        m.right_door_id = e.id
        d["rightDoorId"] = e.id
        d["followId"] = None
        d["tab"] = "rightDoor"
    elif kind == "end":
        return False
    return True


def _resolve(m: AppModel, who: Optional[str]) -> Optional[int]:
    if who is None:
        return None
    e = _jess(m) if who == "jess" else _hero(m)
    return e.id if e else None


# MARK: The scripted intake

def _update_transcript(m: AppModel, d: dict[str, Any], text: str) -> None:
    """``updateTranscript``: reparse, then run the commands not run yet."""
    intake = d["intake"]
    intake["transcript"] = text
    commands = parser.commands(text)
    ran = int(intake.get("commandsRun", 0))
    if len(commands) <= ran:
        return
    fresh = commands[ran:]
    intake["commandsRun"] = len(commands)
    for c in fresh:
        _execute(m, d, c)


def _execute(m: AppModel, d: dict[str, Any], c: parser.VoiceCommand) -> None:
    intake = d["intake"]
    if not intake.get("open"):
        return
    if c.kind is parser.CommandKind.confirm:
        intake["confirmed"] = c.value
        e, _ = m.eta_for(int(c.value or 0))
        intake["eta"] = e.to_dict() if e else None
    elif c.kind is parser.CommandKind.send:
        if intake.get("confirmed") is not None:
            intake["messageSent"] = True
            intake["showMessage"] = True
    elif c.kind is parser.CommandKind.finish:
        eta = ETA.from_dict(intake["eta"]) if intake.get("eta") else None
        e = m.finish_intake(intake["transcript"], "", intake.get("confirmed"), bool(intake.get("messageSent")),
                            parse_iso(intake["startedAtUtc"]), _monitor(intake), eta=eta,
                            now=parse_iso(d["nowUtc"]) if d.get("nowUtc") else None)
        if e is not None:
            intake["heroId"] = e.id
            intake["open"] = False
    elif c.kind is parser.CommandKind.fromMonitor:
        intake["monitor"] = MONITOR_VITALS.to_dict()
    elif c.kind is parser.CommandKind.redirect:
        e = m.redirect_from_intake(intake["transcript"], "", intake.get("confirmed"), parse_iso(intake["startedAtUtc"]),
                                   _monitor(intake))
        intake["heroId"] = e.id
        intake["open"] = False


def _monitor(intake: dict[str, Any]) -> Optional[Vitals]:
    return Vitals.from_dict(intake["monitor"]) if intake.get("monitor") else None


def view(m: AppModel) -> Optional[dict[str, Any]]:
    """The demo as the client sees it: ``demoCaption``, ``demoStep`` and the scripted intake in progress."""
    d = m.demo
    if d is None:
        return None
    intake = d.get("intake")
    intake_view = None
    if intake is not None:
        r = m.parse_intake(intake.get("transcript", ""), "", _monitor(intake))
        intake_view = r.to_dict()
        intake_view.update({"open": bool(intake.get("open")), "transcript": intake.get("transcript", ""),
                            "confirmed": intake.get("confirmed"), "eta": intake.get("eta"),
                            "messageSent": bool(intake.get("messageSent")), "showMessage": bool(intake.get("showMessage")),
                            "heroId": intake.get("heroId"), "startedAtUtc": intake.get("startedAtUtc"),
                            "message": m.intake_message(
                                (r.record.name.split(" ")[0] if r.record else (r.form.name or "").split(" ")[0]),
                                ETA.from_dict(intake["eta"]) if intake.get("eta") else None)})
    return {
        "running": bool(d.get("running")), "finished": bool(d.get("finished")), "narrated": bool(d.get("narrated")),
        "personaId": d.get("personaId"), "step": int(d.get("step", 0)), "caption": d.get("caption"),
        "transcriptSoFar": intake.get("transcript") if intake else None, "listening": bool(d.get("listening")),
        "tab": d.get("tab"), "followId": d.get("followId"), "callingId": d.get("callingId"),
        "rightDoorId": d.get("rightDoorId"), "intake": intake_view,
        "mode": d.get("mode", "guided"), "durations": d.get("durations"), "showUnits": bool(d.get("showUnits")),
        "logLines": len(d.get("log", [])),
    }


# MARK: The narrated demo

def _emit(m: AppModel, tag: str, value: str) -> None:
    line = f"{tag} {value}"
    if m.demo is not None:
        m.demo.setdefault("log", []).append(line)
    print(line, flush=True)


def _mark(m: AppModel, name: str) -> None:
    _emit(m, "PATHFINDER_MARK", f"{name} {time.time():.3f}")


def _alan(m: AppModel):
    return next((e for e in m.sim.episodes if e.isHero and e.name == "Alan P."), None)


def _fmt(x: Optional[float], spec: str) -> str:
    return "-" if x is None else format(x, spec)


def narrated_script(d: list[float]) -> list[Step]:
    """``playNarrated`` as a sequential list of actions, each with the moment (seconds from the start) it may run
    at, each step timed from the start; a wait action blocks until its condition or its deadline."""
    starts: list[float] = []
    acc = 0.0
    for x in d:
        starts.append(acc)
        acc += x

    def dictate(text: str, a: float, b: float, continuing: bool) -> list[Step]:
        words = [w for w in text.split(" ") if w]
        n = max(1, len(words))
        return [{"do": "word", "at": a + (b - a) * k / n, "word": w, "continuing": continuing, "first": k == 0,
                 "last": k == len(words) - 1} for k, w in enumerate(words)]

    steps: list[Step] = []
    # 1. The waiting room on a Saturday afternoon.
    steps.append({"do": "mark", "at": 0, "name": "scene1"})
    steps.append({"do": "beginIntake", "at": starts[1] - 0.7})
    # 2. The nurse speaks; the record builds itself.
    steps.append({"do": "mark", "at": starts[1], "name": "scene2"})
    steps += dictate(HERO_SCRIPT, starts[1] + 0.25, starts[1] + d[1] - 0.7, False)
    # 3. The rules suggest category 2; the nurse confirms by voice.
    steps.append({"do": "mark", "at": starts[2], "name": "scene3"})
    steps += dictate("Confirm category 2.", starts[2] + d[2] * 0.42, starts[2] + d[2] * 0.42 + 0.7, True)
    steps.append({"do": "emitEta", "at": 0})
    # 4. The expected time goes to Alan's phone.
    steps.append({"do": "mark", "at": starts[3], "name": "scene4"})
    steps += dictate("Send the message.", starts[3] + 0.1, starts[3] + 0.7, True)
    steps.append({"do": "hideMessage", "at": starts[3] + d[3] * 0.72})
    steps += dictate("Add to the waiting room.", starts[3] + d[3] * 0.78, starts[3] + d[3] * 0.93, True)
    # 5. Time passes; Jess gives up and leaves.
    steps.append({"do": "mark", "at": starts[4], "name": "scene5"})
    steps.append({"do": "scene5", "at": 0, "seconds": max(1.0, d[4] * 0.55)})
    steps.append({"do": "waitJess", "at": 0, "deadline": starts[4] + d[4] * 0.9})
    steps.append({"do": "set", "at": 0, "speed": 10})
    steps.append({"do": "mark", "at": 0, "name": "jessLeft"})
    # 6. Follow-through: Jess is first on the list and is reached within minutes.
    steps.append({"do": "mark", "at": starts[5], "name": "scene6"})
    steps.append({"do": "set", "at": 0, "tab": "followThrough"})
    steps.append({"do": "emitFollowList", "at": 0})
    steps.append({"do": "requireJess", "at": 0})
    steps.append({"do": "set", "at": starts[5] + d[5] * 0.22, "followId": "jess"})
    steps.append({"do": "set", "at": starts[5] + d[5] * 0.45, "callingId": "jess"})
    steps.append({"do": "set", "at": starts[5] + d[5] * 0.70, "callingId": None})
    steps.append({"do": "contact", "at": 0, "who": "jess", "reached": True,
                  "result": "Safe at home and calmer. Left because the wait felt too long. Going to the Safe Haven café tonight.",
                  "nextStep": "GP on Monday for a mental health care plan", "reason": "Wait too long"})
    steps.append({"do": "emitJess", "at": 0})
    # 7. Alan goes home; the right-door search runs from his home, ring by ring, then travel time by car.
    steps.append({"do": "mark", "at": starts[6], "name": "scene7"})
    steps.append({"do": "set", "at": 0, "followId": None})
    steps.append({"do": "waitAlan", "at": 0, "dischargeBy": starts[6] + d[6] * 0.2, "deadline": starts[6] + d[6] * 0.34})
    steps.append({"do": "set", "at": 0, "speed": 10})
    steps.append({"do": "requireAlan", "at": 0})
    steps.append({"do": "rightDoor", "at": starts[6] + d[6] * 0.24})
    steps.append({"do": "mark", "at": 0, "name": "rightDoor"})
    steps.append({"do": "contact", "at": starts[6] + d[6] * 0.86, "who": "alan", "reached": True,
                  "result": "Home and well. GP appointment booked for Monday; cardiology clinic referral sent.",
                  "nextStep": "GP on Monday. If the chest pain comes back: call 000", "reason": None})
    if len(d) == 10:
        # 8. The architecture: the units as a stack, from the foundation up to the full deployment.
        steps.append({"do": "mark", "at": starts[7], "name": "scene8"})
        steps.append({"do": "set", "at": 0, "followId": None, "tab": "frontDoor"})
        steps.append({"do": "emitUnits", "at": 0})
        steps.append({"do": "set", "at": 0, "deployment": "minimum", "showUnits": True})
        steps.append({"do": "set", "at": starts[7] + d[7] * 0.40, "deployment": "standard"})
        steps.append({"do": "set", "at": starts[7] + d[7] * 0.70, "deployment": "full"})
        # 9. The foundation at work: the wait model on the room as it is.
        steps.append({"do": "mark", "at": starts[8], "name": "scene9"})
        steps.append({"do": "set", "at": 0, "showUnits": False, "tab": "frontDoor"})
        steps.append({"do": "emitQueue", "at": 0})
    # The results.
    last = len(d) - 1
    steps.append({"do": "mark", "at": starts[last], "name": f"scene{last + 1}"})
    steps.append({"do": "set", "at": 0, "showUnits": False, "followId": None, "tab": "impact"})
    steps.append({"do": "mark", "at": starts[last] + d[last], "name": "end"})
    steps.append({"do": "end", "at": 0})
    return steps


def _run_narrated(m: AppModel, d: dict[str, Any], now: datetime) -> None:
    t0 = parse_iso(d["startedUtc"])
    elapsed = (now - t0).total_seconds()
    steps = narrated_script(d["durations"])
    guard = 0
    while guard < 1000:
        guard += 1
        i = int(d["step"])
        if i >= len(steps):
            _finish(m, d)
            return
        st = steps[i]
        if elapsed < st["at"]:
            return
        kind = st["do"]
        if kind == "waitJess":
            if CONDITIONS["jessLeft"](m) or elapsed > st["deadline"]:
                d["step"] = i + 1
                continue
            return
        if kind == "waitAlan":
            if _alan_discharged(m) or elapsed > st["deadline"]:
                d["step"] = i + 1
                continue
            alan = _alan(m)
            if alan is not None:
                remaining = max(1, (alan.careEnds if alan.careEnds is not None else m.sim.now + 160) - m.sim.now)
                seconds_left = max(0.4, st["dischargeBy"] - elapsed)
                m.speed = min(6000, max(10, remaining / seconds_left * 60))
            return
        d["step"] = i + 1
        if not _apply_narrated(m, d, st, now):
            _finish(m, d)
            return


def _alan_discharged(m: AppModel) -> bool:
    return any(e.isHero and e.name == "Alan P." and e.outcome is Outcome.discharged for e in m.sim.episodes)


def _apply_narrated(m: AppModel, d: dict[str, Any], st: Step, now: datetime) -> bool:
    kind = st["do"]
    if kind == "mark":
        _mark(m, st["name"])
    elif kind == "word":
        intake = d.get("intake")
        if intake is None or not intake.get("open"):
            return True
        if st["first"]:
            intake["dictatedFrom"] = intake.get("transcript", "") if st["continuing"] else ""
            d["listening"] = True
        current = intake.get("dictatedFrom", "")
        current += ("" if not current else " ") + st["word"]
        intake["dictatedFrom"] = current
        _update_transcript(m, d, current)
        if st["last"]:
            d["listening"] = False
    elif kind == "emitEta":
        _emit(m, "PATHFINDER_ETA_SAMPLES", ",".join(str(x) for x in m.last_intake_samples))
        intake = d.get("intake") or {}
        if intake.get("eta"):
            e = ETA.from_dict(intake["eta"])
            _emit(m, "PATHFINDER_ETA", f"{e.p10},{e.p50},{e.p90},{e.ahead}")
    elif kind == "scene5":
        if m.captured_seconds:
            _emit(m, "PATHFINDER_CAPTURE", f"{m.captured_seconds[-1]:.1f}")
        jess = _jess(m)
        if jess is not None:
            leave_at = jess.arrival + int(jess.patience) + 1
            m.speed = max(10, max(1, leave_at - m.sim.now) / st["seconds"] * 60)
    elif kind == "emitJess":
        jess = _jess(m)
        if jess is not None and jess.outcomeAt is not None:
            _emit(m, "PATHFINDER_JESS", f"{jess.outcomeAt} {m.sim.now}")
    elif kind == "emitFollowList":
        _emit_follow_list(m)
    elif kind == "requireAlan":
        return _alan(m) is not None
    elif kind == "rightDoor":
        alan = _alan(m)
        if alan is None:
            return False
        m.right_door_id = alan.id
        d["rightDoorId"] = alan.id
        d["followId"] = None
        d["tab"] = "rightDoor"
        _emit_right_door(m, rightdoor.plan(alan, alan.arrivalMode.travel, m.sim.now), alan)
    elif kind == "emitUnits":
        for u in UNITS:
            _emit(m, "PATHFINDER_UNIT", "|".join([u.id, u.name, u.kind.value, u.tier.value, ",".join(u.frm), u.connects, u.gives]))
    elif kind == "emitQueue":
        _emit_queue(m)
    elif kind == "set" and ("deployment" in st or "showUnits" in st):
        for k, v in st.items():
            if k == "deployment":
                m.deployment = Deployment(v)
            elif k in ("showUnits", "tab"):
                d[k] = v
            elif k == "followId":
                d[k] = _resolve(m, v)
        return True
    elif kind == "contact" and st["who"] == "alan":
        alan = _alan(m)
        if alan is None:
            return False
        m.record_contact(alan.id, reached=st["reached"], result=st["result"], next_step=st.get("nextStep"),
                         reason=st.get("reason"))
    else:
        return _apply(m, d, st, now)
    return True


def _emit_follow_list(m: AppModel) -> None:
    """The follow-through list as ranked at this moment, and Jess's case, for the explainer's step 6."""
    open_cases = [e for e in m.follow_cases if e.followUp is None or e.followUp.status.value != "closed"]
    for k, e in enumerate(open_cases[:6]):
        f = e.followUp
        if f is None:
            continue
        left = e.outcomeAt or 0
        _emit(m, "PATHFINDER_FOLLOW", "|".join([str(k + 1), e.name, str(int(f.tier)), _fmt(f.risk7, ".3f"), _fmt(f.risk28, ".3f"),
                                                "-" if f.riskN is None else str(f.riskN), str(left),
                                                str(left + f.tier.due_minutes), "1" if e.isHero else "0", e.cohort.value,
                                                str(e.ats), str(e.priorVisits), str(len(open_cases))]))
    jess = _jess(m)
    if jess is not None and jess.followUp is not None:
        f = jess.followUp
        left = jess.outcomeAt or 0
        _emit(m, "PATHFINDER_JESSCASE", "|".join([str(int(f.tier)), _fmt(f.risk7, ".3f"), _fmt(f.risk28, ".3f"),
                                                  "-" if f.riskN is None else str(f.riskN), f.riskBasis, str(left),
                                                  str(left + f.tier.due_minutes), str(jess.arrival), str(jess.ats),
                                                  ";".join(f.reasons)]))


def _emit_right_door(m: AppModel, p: rightdoor.Result, e) -> None:
    """The right-door model as computed for the recording, so tools/make_explainer.py can draw exactly it."""
    s = p.search
    _emit(m, "PATHFINDER_HOME", f"{s.home.q} {s.home.r} {e.homeSuburb} {p.mode.value} {s.k} {s.hex_count} {1 if s.complete else 0}")
    for r in s.rings:
        ids = ",".join(x.id for x in r.found)
        _emit(m, "PATHFINDER_RING", f"{r.k} {ids or '-'}")
    _emit(m, "PATHFINDER_NEED", " ".join(f"{n.count}x{'/'.join(k.value for k in n.kinds)}" for n in s.need))
    _emit(m, "PATHFINDER_CORRIDOR", " ".join(f"{h.q},{h.r}" for h in p.field.order if h in network.CORRIDOR_HEXES))
    for h in p.field.order:
        if h in p.field.minutes:
            _emit(m, "PATHFINDER_HEX", f"{h.q} {h.r} {p.field.minutes[h]:.1f}")
    for k, o in enumerate(p.options):
        h = o.service.hex
        _emit(m, "PATHFINDER_PLACE", "|".join([str(k + 1), o.service.id, o.service.kind.value, "-" if h is None else str(h.q),
                                               "-" if h is None else str(h.r), _fmt(o.minutes, ".1f"), str(o.opensIn),
                                               f"{o.fit:.2f}", f"{o.score:.3f}", o.service.name]))
        if o.route:
            _emit(m, "PATHFINDER_ROUTE", f"{o.service.id} " + " ".join(f"{h.q},{h.r}" for h in o.route))


def _emit_queue(m: AppModel) -> None:
    """The waiting room as it stands, with each person's range, and the 100 futures behind a category-4 arrival."""
    m.refresh_etas(force=True)
    now = m.sim.now
    _emit(m, "PATHFINDER_ROOM", f"{now} {len(m.sim.waiting)} {m.in_care_count} {m.longest_wait}")
    for e in m.waiting_sorted:
        r = m.etas.get(e.id)
        _emit(m, "PATHFINDER_QUEUE", "|".join([str(e.id), e.name, str(e.ats), str(now - e.arrival), "1" if e.holdFromCall else "0",
                                               f"{r.p10},{r.p50},{r.p90}" if r else "-"]))
    etas, samples = eta_engine.estimate_with_samples(m.sim, m.config, extra=m.probe_episode(4))
    e = etas.get(-1)
    if e is not None:
        _emit(m, "PATHFINDER_PROBE", f"4|{e.p10},{e.p50},{e.p90},{e.ahead}|" + ",".join(str(x) for x in samples.get(-1, [])))
