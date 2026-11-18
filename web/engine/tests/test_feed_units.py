"""The public feed and the wait model over it, and the unit catalogue."""
from __future__ import annotations

from pathfinder_engine import clock, eta, feed, units
from pathfinder_engine.units import AppTab, Deployment, UnitKind


def test_feed_snapshot_and_forecast(config):
    snap = feed.FeedSnapshot.load()
    assert len(snap.hospitals) == 10 and clock.hour_of_week(snap.minute_of_week) == 167, "the snapshot has ten hospitals and is Sunday 11 pm"
    fsh = next(h for h in snap.hospitals if h.short == "Fiona Stanley")
    f1 = feed.forecast(fsh, config, snap.minute_of_week)
    f2 = feed.forecast(fsh, config, snap.minute_of_week)
    assert f1 is not None and f2 is not None
    assert abs(f1.seenPerHour - fsh.waiting / fsh.t4_avg_wait_min * 60) < 1e-9, "Little's law: waiting / average wait is the throughput"
    assert sorted(f1.byCategory) == [3, 4, 5] and len(f1.samples[4]) == eta.FUTURES, "a range for categories 3, 4 and 5 from 100 futures"
    for a in (3, 4, 5):
        e = f1.eta(a)
        assert e.p10 <= e.p50 <= e.p90, f"percentiles in order for category {a}"
    assert f1.eta(3).p50 <= f1.eta(4).p50 <= f1.eta(5).p50, "a more urgent category is seen sooner"
    assert f1.byCategory == f2.byCategory, "the forecast is deterministic"
    king_edward = next(h for h in snap.hospitals if h.short == "King Edward")
    assert feed.forecast(king_edward, config, snap.minute_of_week) is None, "nobody waiting means no forecast"
    assert f1.range_text(4) is not None and ("–" in f1.range_text(4) or f1.range_text(4).endswith("+"))


def test_fnv_is_stable():
    assert feed.fnv("") == 0xcbf29ce484222325
    assert feed.fnv("a") == 0xaf63dc4c8601ec8c


def test_unit_catalogue():
    assert len({u.id for u in units.ALL}) == len(units.ALL), "unit ids are unique"
    assert units.ids_in(Deployment.minimum) <= units.ids_in(Deployment.standard) <= units.ids_in(Deployment.full), \
        "deployments nest: minimum within standard within full"
    assert units.ids_in(Deployment.minimum) == {"adt", "episodes", "aggregates", "wait", "messages", "sms", "patient"} \
        and len(units.ids_in(Deployment.full)) == len(units.ALL), "the minimum is seven units and the full deployment is all of them"
    assert sum(1 for u in units.units_in(Deployment.minimum) if u.kind is UnitKind.connector and not u.frm) == 1, \
        "the minimum needs one inbound interface"
    assert all(units.unit(a) is not None and units.unit(b) is not None for a, b in units.edges()), "every connection joins two known units"
    assert all((u.kind is UnitKind.connector and not u.frm) or u.frm or units.consumers(u.id) for u in units.ALL), "every unit is wired to another"
    for d in Deployment:
        ids = units.ids_in(d)
        assert all(not u.frm or any(x in ids for x in u.frm) or u.id == "aggregates" for u in units.units_in(d)), \
            f"in the {d.value} deployment every unit has at least one of its inputs (the aggregates store ships pre-built)"
    assert AppTab.tabs(Deployment.minimum) == [AppTab.frontDoor] and len(AppTab.tabs(Deployment.full)) == 5, "the minimum shows the queue alone"
    assert [u.kind for u in units.layer(Deployment.standard)][:1] == [UnitKind.connector]
    assert units.ALL[0].to_dict()["plugsInto"].startswith("HL7 v2 ADT")
    assert Deployment.full.label == "Full" and Deployment.minimum.layer_title == "The foundation: minimum, 7 units"
