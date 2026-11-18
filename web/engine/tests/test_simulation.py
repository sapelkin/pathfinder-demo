"""The seeded generator, the waiting room, the wait model and the AppModel behaviour the web API reproduces."""
from __future__ import annotations

import json
from datetime import timedelta

from conftest import SAT_1430
from pathfinder_engine import clock, demo, eta, personas, simulator
from pathfinder_engine.domain import FollowStatus, FollowTier, Outcome, Stage
from pathfinder_engine.model import DAY_START, START_MINUTE, AppModel, utcnow
from pathfinder_engine.rng import SeededRNG
from pathfinder_engine.simulator import SimState


def test_splitmix_reference_vector():
    # splitmix64 as published by Vigna: seed 1234567 gives 6457827717110365317 first.
    assert SeededRNG(1234567).next() == 6457827717110365317
    assert SeededRNG(0).state == 0x9E3779B97F4A7C15, "a zero seed is replaced"
    r = SeededRNG(62)
    xs = [r.uniform() for _ in range(1000)]
    assert all(0 <= x < 1 for x in xs)
    assert SeededRNG(62).int(2, 3) in (2, 3) and SeededRNG(62).element(["a"]) == "a"
    assert SeededRNG(5).pick([0, 0, 1]) == 2 and SeededRNG(5).pick([]) == 0 and SeededRNG(5).poisson(0) == 0


def test_sim_clock():
    assert clock.hour_of_week(SAT_1430) == 134
    assert clock.text(SAT_1430) == "Sat 2:30 pm" and clock.text(0) == "Mon 12:00 am" and clock.time(12 * 60) == "12:00 pm"
    assert clock.duration(45) == "45 min" and clock.duration(120) == "2 h" and clock.duration(125) == "2 h 5 m"


def test_simulation_runs_and_is_deterministic(seed, config):
    def run() -> SimState:
        s = SimState(0, SeededRNG(seed.sim.seed))
        while s.now < SAT_1430:
            simulator.step(s, config)
        return s

    a, b = run(), run()
    assert len(a.waiting) == len(b.waiting) and len(a.episodes) == len(b.episodes)
    assert [e.name for e in a.episodes] == [e.name for e in b.episodes] and a.rng.state == b.rng.state
    assert len(a.episodes) > 500 and 3 <= len(a.waiting) <= 80
    etas = eta.estimate(a, config)
    tracked = [i for i in a.waiting if not a.episodes[i].holdFromCall]
    assert len(etas) == len(tracked)
    for e in etas.values():
        assert e.p10 <= e.p50 <= e.p90
    closed = [e for e in a.episodes if e.outcome is not None]
    dnw = sum(1 for e in closed if e.outcome is Outcome.didNotWait) / len(closed)
    assert 0.03 <= dnw <= 0.12, f"dnw {dnw}"
    assert all(e.homeSuburb and e.name.endswith(".") for e in a.episodes)


def test_eta_text():
    assert eta.ETA(2, 8, 24, 5).range_text == "under 25 min"
    assert eta.ETA(13, 31, 60, 7).range_text == "15–60 min"
    assert eta.ETA(12, 12, 13, 0).range_text == "10–15 min"
    assert eta.round5(12.5 * 2 / 2) == 15 and eta.round5(7) == 5 and eta.round5(2) == 0


def test_model_opens_on_the_demo_afternoon():
    m = AppModel()
    assert m.sim.now == START_MINUTE and m.clock_text == "Sat 2:30 pm"
    jess = next(e for e in m.sim.episodes if e.name == "Jess T.")
    liam = next(e for e in m.sim.episodes if e.isHero and e.name == "Liam K.")
    assert jess.holdFromCall and jess.isHero and jess.stage is Stage.waiting and jess.arrival == START_MINUTE - 110
    assert liam.outcome is Outcome.redirected and liam.followUp is not None and liam.followUp.tier is FollowTier.within24h
    assert m.right_door_candidates[0].isHero and m.right_door_candidates[1].isHero
    assert m.etas and all(i in m.etas for i in m.sim.waiting if not m.sim.episodes[i].holdFromCall)
    assert m.queue_history and m.queue_history[0].minute == DAY_START
    assert m.follow_cases and m.open_action_count > 0
    assert all(e.followUp.status is FollowStatus.closed for e in m.sim.episodes
               if e.followUp and e.outcomeAt is not None and e.outcomeAt < START_MINUTE - 24 * 60 and not e.isHero)
    state = m.state()
    assert state["counters"]["waiting"] == len(m.sim.waiting) and state["ed"]["name"] == "Pathfinder Demo ED"
    assert "{first}" in state["intakeMessageTemplate"] and "{eta}" in state["intakeMessageTemplate"]
    assert state["waiting"][-1]["name"] == "Jess T.", "the held patient sorts last"


def test_alan_scenario_end_to_end():
    m = AppModel()
    r = m.parse_intake(personas.ALAN.script + " Confirm category 2. Send the message.")
    assert r.suggested == 2 and r.record is not None and r.record.name == "Alan Pierce"
    assert [c.text for c in r.commands] == ["confirm:2", "send"]
    e2, samples = m.eta_for(2)
    assert e2 is not None and len(samples) == eta.FUTURES and e2.p10 <= e2.p50 <= e2.p90
    hero = m.finish_intake(personas.ALAN.script, "", 2, True, utcnow() - timedelta(seconds=30))
    assert hero is not None and hero.name == "Alan P." and hero.ats == 2 and hero.isHero and hero.homeSuburb == "Riverbend"
    assert hero.descriptor == "Chest pain of likely cardiac nature" and hero.scriptedCareMinutes == 150 and hero.priorVisits == 3
    assert hero.etaSentAt == m.sim.now and m.banner is not None and m.banner.text.startswith("Alan P. added to the waiting room, category 2.")
    assert hero.id in m.etas and m.captured_seconds and m.captured_seconds[0] >= 29
    assert m.intake_message("Alan", e2).startswith("Hi Alan, you're checked in at Pathfinder Demo ED. Expected time to be seen: ")
    m.advance(30)
    jess = next(e for e in m.sim.episodes if e.name == "Jess T.")
    assert jess.outcome is Outcome.didNotWait and jess.outcomeAt == START_MINUTE + 26, "Jess gives up at 2:56 pm"
    assert jess.followUp is not None and jess.followUp.tier is FollowTier.callToday
    assert "Has left before on an earlier visit" in jess.followUp.reasons
    m.record_outcome(hero.id, Outcome.discharged)
    h = m.sim.episodes[hero.id]
    assert h.outcome is Outcome.discharged and h.followUp is not None and h.followUp.tier is FollowTier.within24h
    assert h.followUp.reasons == ["Aged 72 with 3 earlier visits: confirm a named next step"]
    assert m.due_text(h).startswith("Due by ")
    assert m.record_contact(hero.id, True, personas.ALAN.callResult, personas.ALAN.nextStep)
    assert h.followUp.status is FollowStatus.closed and h.followUp.nextStep == personas.ALAN.nextStep and m.due_text(h).startswith("Done ")
    rd = m.right_door(hero.id)
    assert rd["purpose"] == "nextTime" and rd["mode"] == "car" and rd["edFirst"] and rd["message"] == "For follow-up, from Riverbend by car"
    assert rd["options"][0]["service"]["kind"] == "ed" and rd["options"][0]["pinned000"] and rd["options"][0]["rank"] == 1
    assert rd["search"]["hexCount"] > 0 and rd["field"] and rd["home"] == rd["field"][0]["hex"]
    k = m.kpi()
    assert k["captureSeconds"] and k["rContactShare"]["total"] >= 0 and len(k["arrivalsByHour"]) == 24 and "median_wait_min" in k["baselines"]
    m.record_contact(jess.id, False, "")
    assert jess.followUp.status is FollowStatus.noAnswer and jess.followUp.messageSent and m.due_text(jess).startswith("Try again at ")
    m.toggle_alo(jess.id)
    assert jess.followUp.aloOffered


def test_redirect_from_intake_and_message_text():
    m = AppModel()
    e = m.redirect_from_intake("29 year old man, sore throat for 3 days, walked in")
    assert e.outcome is Outcome.redirected and e.redirectService == "Urgent Care Clinic North" and e.followUp is not None
    assert m.banner is not None and "redirected to Urgent Care Clinic North" in m.banner.text
    liam = next(x for x in m.sim.episodes if x.isHero and x.name == "Liam K.")
    rd = m.right_door(liam.id, purpose=None, mode=None)
    assert rd["purpose"] == "nextTime" and rd["mode"] == "walk" and rd["message"] == "Where to go next time, from Marlow on foot"
    assert m.redirect_message(liam).startswith("Open now, within 30 min on foot of Marlow")


def test_tick_steps_by_elapsed_time_and_speed():
    m = AppModel()
    t0 = m.last_tick_utc
    assert m.tick(t0 + timedelta(seconds=30)) == 5 and m.sim.now == START_MINUTE + 5, "30 s at speed 10 is 5 minutes"
    assert m.tick(t0 + timedelta(seconds=33)) == 0, "nothing lost: the half minute carries over"
    assert m.tick(t0 + timedelta(seconds=36)) == 1
    m.speed = 1200
    assert m.tick(m.last_tick_utc + timedelta(seconds=600)) == 120, "capped at 120 minutes per call"
    m.set_running(False)
    assert m.tick(m.last_tick_utc + timedelta(seconds=600)) == 0, "never steps while paused"


def test_document_round_trip():
    m = AppModel()
    m.finish_intake(personas.GRACE.script, "", 3, True, utcnow())
    m.advance(20)
    doc = json.dumps(m.to_dict())
    m2 = AppModel.from_dict(json.loads(doc))
    assert json.dumps(m2.to_dict()) == doc
    m.advance(60)
    m2.advance(60)
    assert m.sim.rng.state == m2.sim.rng.state and m.state()["counters"] == m2.state()["counters"]
    assert json.dumps(m.state(), default=str) == json.dumps(m2.state(), default=str)


def test_guided_demo_runs_to_the_end():
    m = AppModel()
    now = utcnow()
    demo.start(m, now=now)
    assert m.demo is not None and m.demo["running"] and m.demo_view()["caption"].startswith("Saturday 2:30 pm at a busy metro ED.")
    seen_captions = []
    for sec in range(0, 160):
        t = now + timedelta(seconds=sec)
        m.tick(t)
        demo.run(m, t)
        v = m.demo_view()
        if v["caption"] and (not seen_captions or seen_captions[-1] != v["caption"]):
            seen_captions.append(v["caption"])
        if not v["running"]:
            break
    assert v["finished"] and v["tab"] == "frontDoor" and m.speed == 10
    assert "Jess leaves without being seen. Pathfinder puts her straight on the follow-through list." in seen_captions
    assert v["transcriptSoFar"].endswith("Confirm category 2. Send the message. Add to the waiting room.")
    hero = next(e for e in m.sim.episodes if e.isHero and e.name == "Alan P.")
    jess = next(e for e in m.sim.episodes if e.name == "Jess T.")
    assert hero.outcome is Outcome.discharged and hero.followUp.status is FollowStatus.closed and hero.followUp.nextStep == personas.ALAN.nextStep
    assert jess.followUp.status is FollowStatus.closed and jess.leaveReason == "Wait too long"
    assert v["rightDoorId"] == hero.id and v["intake"]["heroId"] == hero.id and v["intake"]["messageSent"]
    assert sec < 120, "the story plays in about 80 seconds"
