"""Metro mode: every hospital in the snapshot builds its published room, deterministically and within budget, and the
measured effect returns both arms; the narrated demo still plays on a real hospital."""
from __future__ import annotations

import contextlib
import io
import time
from datetime import timedelta

import pytest

from pathfinder_engine import demo, metro
from pathfinder_engine.domain import Cohort, Outcome, Stage
from pathfinder_engine.model import START_MINUTE, AppModel, utcnow
from pathfinder_engine.seed import SeedFile
from test_narrated import ALL_TAGS, read_log

SEED = SeedFile.load()
HOSPITALS = metro.hospitals(SEED)
REAL = [h for h in HOSPITALS if h.id != metro.DEMO_ID]


def test_catalogue():
    assert HOSPITALS[0].id == "demo" and HOSPITALS[0].name == "Pathfinder Demo ED" and HOSPITALS[0].waiting == 10
    assert HOSPITALS[0].in_ed == 54 and HOSPITALS[0].t4_avg_wait_min == 40
    assert [h.id for h in REAL] == ["armadale", "fiona-stanley", "joondalup", "king-edward", "peel", "perth-children-s",
                                    "rockingham", "royal-perth", "sir-charles-gairdner", "midland"]
    assert all(6 <= len(h.suburbs) <= 9 for h in HOSPITALS)
    assert metro.find("fiona-stanley", SEED).suburbs[0].name == "Murdoch" and metro.find("nope", SEED) is None
    src = metro.source()
    assert src["takenText"].startswith("Sunday") and "2:30 pm" in src["note"] and src["url"].startswith("https://")


@pytest.mark.parametrize("h", REAL, ids=[h.id for h in REAL])
def test_each_hospital_builds_its_published_room(h):
    t0 = time.perf_counter()
    m = AppModel(seed=SEED, hospital_id=h.id)
    built = time.perf_counter() - t0
    assert built <= 1.5, f"switching to {h.id} took {built:.2f} s"
    waiting = [m.sim.episodes[i] for i in m.sim.waiting]
    in_care = [m.sim.episodes[i] for i in m.sim.inCare]
    if h.waiting > 0:
        assert len(waiting) == h.waiting, "the published count, Jess included"
        t4 = [m.sim.now - e.arrival for e in waiting if e.ats == 4]
        assert abs(sum(t4) / len(t4) - h.t4_avg_wait_min) <= 5
    else:
        assert [e.name for e in waiting] == ["Jess T."], "nobody published waiting: only the demo's own patient"
    assert len(in_care) == h.in_ed - h.waiting
    assert all(e.stage is Stage.waiting and m.sim.now - e.arrival < e.patience for e in waiting)
    assert all(e.stage is Stage.inCare and e.careEnds > m.sim.now and e.calledAt <= m.sim.now and e.plannedOutcome for e in in_care)
    names = {s.name for s in h.suburbs}
    assert {e.homeSuburb for e in m.sim.episodes} <= names
    assert m.hospital.id == h.id and m.state()["ed"]["name"] == h.name and m.state()["hospital"]["published"]["waiting"] == h.waiting
    assert any(e.isHero and e.name == "Jess T." for e in waiting) and any(e.isHero and e.name == "Liam K." for e in m.sim.episodes)
    assert m.follow_cases and m.queue_history[-1].minute == START_MINUTE and m.queue_history[-1].waiting == len(waiting)
    tracked = [i for i in m.sim.waiting if not m.sim.episodes[i].holdFromCall]
    assert all(i in m.etas for i in tracked) and (bool(m.etas) == bool(tracked))
    assert m.network_dict()["hospitalName"] == h.name and {s["name"] for s in m.network_dict()["suburbs"]} == names
    assert m.network_dict()["disclaimer"].startswith("Demo metro")


def test_cohort_shares_follow_the_published_bands(config):
    mh_n = p65_n = n = 0
    for h in REAL:
        m = AppModel(seed=SEED, hospital_id=h.id)
        for i in m.sim.waiting:
            e = m.sim.episodes[i]
            if e.isHero:
                continue
            n += 1
            mh_n += e.cohort is Cohort.mh
            p65_n += e.cohort is Cohort.p65
    assert n > 150
    assert min(config.mhByATS) - 0.03 <= mh_n / n <= max(config.mhByATS) + 0.03
    assert min(config.p65ByATS) - 0.08 <= p65_n / n <= max(config.p65ByATS) + 0.08


def test_switching_is_deterministic_and_keeps_rhythm():
    a = AppModel(seed=SEED, hospital_id="joondalup")
    b = AppModel(seed=SEED, hospital_id="demo")
    b.set_hospital("joondalup")
    assert [e.name for e in a.sim.episodes] == [e.name for e in b.sim.episodes] and a.sim.rng.state == b.sim.rng.state
    assert a.rate_scale == b.rate_scale and 1.0 < a.rate_scale < 2.0
    assert a.config.arrivals_per_minute(START_MINUTE) == pytest.approx(b.config.arrivals_per_minute(START_MINUTE))
    demo_cfg = AppModel(seed=SEED, hospital_id="demo").config
    assert a.config.calls_per_minute(START_MINUTE) == pytest.approx(demo_cfg.calls_per_minute(START_MINUTE) * a.rate_scale)
    a.advance(60)
    b.advance(60)
    assert a.state()["counters"] == b.state()["counters"]
    assert all(e.homeSuburb in {s.name for s in a.hospital.suburbs} for e in a.sim.episodes)
    b.reset()
    assert b.hospital.id == "joondalup", "/reset keeps the hospital"
    b.set_hospital("demo")
    assert len(b.sim.waiting) == 10 and b.rate_scale == 1.0


def test_document_round_trip_keeps_the_hospital():
    import json
    m = AppModel(seed=SEED, hospital_id="peel")
    m.ensure_metro()
    doc = json.dumps(m.to_dict())
    m2 = AppModel.from_dict(json.loads(doc), seed=SEED)
    assert m2.hospital.id == "peel" and m2.config.weekly == pytest.approx(m.config.weekly) and m2.metro_cache == m.metro_cache
    assert [s.name for s in m2.config.suburbs] == [s.name for s in m.config.suburbs]
    assert json.dumps(m2.to_dict()) == doc


@pytest.mark.parametrize("hid", ["fiona-stanley", "joondalup", "demo"])
def test_measured_effect(hid):
    m = AppModel(seed=SEED, hospital_id=hid)
    t0 = time.perf_counter()
    assert m.ensure_metro()
    took = time.perf_counter() - t0
    assert took <= 3.0, f"the effect measurement took {took:.2f} s"
    r = m.kpi()["metro"]
    assert r["publishedT4AvgWaitMin"] == m.hospital.t4_avg_wait_min and r["horizonMinutes"] == 360 and r["replicas"] == 3
    for key in ("simulatedT4WaitMin", "newArrivalT4WaitMin", "waitingNow"):
        assert set(r[key]) == {"baseline", "withRedirects"} and all(v is not None for v in r[key].values())
    assert 0 < r["redirectedShare"] < 1 and r["takenText"].startswith("Sunday") and "same seeds" in r["method"]
    assert r["waitingNow"]["withRedirects"] < r["waitingNow"]["baseline"]
    assert r["newArrivalT4WaitMin"]["withRedirects"] <= r["newArrivalT4WaitMin"]["baseline"]
    assert not m.ensure_metro(), "cached for this hospital and hour"
    m.advance(60)
    assert m.ensure_metro(), "a new hour measures again"
    assert all(e.outcome is not Outcome.redirected or e.redirectService for e in m.sim.episodes), "the measurement does not touch the state"


def test_narrated_demo_on_a_real_hospital():
    m = AppModel(seed=SEED, hospital_id="fiona-stanley")
    now = utcnow()
    durations = [3.0] * 6 + [8.0] + [3.0] * 3
    with contextlib.redirect_stdout(io.StringIO()):
        demo.start(m, narrated=True, durations=durations, now=now)
        t = 0.0
        while m.demo["running"] and t < 50:
            t += 0.25
            at = now + timedelta(seconds=t)
            m.tick(at)
            demo.run(m, at)
    log = list(m.demo["log"])
    assert {line.split(" ", 1)[0] for line in log} == ALL_TAGS
    info = read_log(log)
    assert info["waiting"] == 45 and info["rightdoor"]["suburb"] in {s.name for s in m.hospital.suburbs}
    assert [n for n, _ in info["marks"]][-1] == "end" and info["follow"][0]["name"] == "Jess T."
    assert m.hospital.id == "fiona-stanley"
