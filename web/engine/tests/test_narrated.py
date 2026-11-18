"""The narrated demo driven by 250 ms ticks on a simulated clock: every PATHFINDER_* line that
tools/make_explainer.py's read_log() reads, parsed the way read_log() parses it (same separators and field counts)."""
from __future__ import annotations

import contextlib
import io
from datetime import timedelta

import pytest

from pathfinder_engine import demo
from pathfinder_engine.model import AppModel, utcnow

ALL_TAGS = {"PATHFINDER_MARK", "PATHFINDER_WAITING", "PATHFINDER_ETA_SAMPLES", "PATHFINDER_ETA", "PATHFINDER_CAPTURE",
            "PATHFINDER_JESS", "PATHFINDER_FOLLOW", "PATHFINDER_JESSCASE", "PATHFINDER_HOME", "PATHFINDER_RING",
            "PATHFINDER_NEED", "PATHFINDER_CORRIDOR", "PATHFINDER_HEX", "PATHFINDER_PLACE", "PATHFINDER_ROUTE",
            "PATHFINDER_ROOM", "PATHFINDER_QUEUE", "PATHFINDER_PROBE", "PATHFINDER_UNIT"}
TEN_SCENE_ONLY = {"PATHFINDER_ROOM", "PATHFINDER_QUEUE", "PATHFINDER_PROBE", "PATHFINDER_UNIT"}


def read_log(lines: list[str]) -> dict:
    """tools/make_explainer.py read_log(), line for line, so a format drift fails here first."""
    info: dict = {"marks": []}
    for line in lines:
        tag, _, rest = line.partition(" ")
        if tag == "PATHFINDER_MARK":
            name, ep = rest.split()
            info["marks"].append((name, float(ep)))
        elif tag == "PATHFINDER_ETA_SAMPLES":
            info["samples"] = [int(x) for x in rest.split(",") if x]
        elif tag == "PATHFINDER_ETA":
            info["eta"] = [int(x) for x in rest.split(",")]
        elif tag == "PATHFINDER_WAITING":
            info["waiting"], info["in_care"] = (int(x) for x in rest.split())
        elif tag == "PATHFINDER_CAPTURE":
            info["capture"] = float(rest)
        elif tag == "PATHFINDER_JESS":
            left, contact = (int(x) for x in rest.split())
            info["jess_minutes"] = contact - left
        elif tag == "PATHFINDER_FOLLOW":
            rank, name, tier, r7, r28, n, left, due, hero, cohort, ats, prior, total = rest.split("|")
            info.setdefault("follow", []).append(dict(rank=int(rank), name=name, tier=int(tier), r7=None if r7 == "-" else float(r7),
                                                      r28=None if r28 == "-" else float(r28), n=None if n == "-" else int(n),
                                                      left=int(left), due=int(due), hero=hero == "1", cohort=cohort, ats=int(ats),
                                                      prior=int(prior), total=int(total)))
        elif tag == "PATHFINDER_JESSCASE":
            tier, r7, r28, n, basis, left, due, arrival, ats, reasons = rest.split("|")
            info["jesscase"] = dict(tier=int(tier), r7=None if r7 == "-" else float(r7), r28=None if r28 == "-" else float(r28),
                                    n=None if n == "-" else int(n), basis=basis, left=int(left), due=int(due), arrival=int(arrival),
                                    ats=int(ats), reasons=reasons.split(";"))
        elif tag == "PATHFINDER_HOME":
            q, r, suburb, mode, k, n, complete = rest.split()
            rd = info.setdefault("rightdoor", {"rings": [], "hex": {}, "places": [], "routes": {}, "corridor": set()})
            rd.update(home=(int(q), int(r)), suburb=suburb, mode=mode, k=int(k), hexes=int(n), complete=complete == "1")
        elif tag == "PATHFINDER_RING":
            k, ids = rest.split()
            info["rightdoor"]["rings"].append((int(k), [] if ids == "-" else ids.split(",")))
        elif tag == "PATHFINDER_NEED":
            info["rightdoor"]["need"] = rest.split()
        elif tag == "PATHFINDER_CORRIDOR":
            info["rightdoor"]["corridor"] = {tuple(int(v) for v in x.split(",")) for x in rest.split()}
        elif tag == "PATHFINDER_HEX":
            q, r, m = rest.split()
            info["rightdoor"]["hex"][(int(q), int(r))] = float(m)
        elif tag == "PATHFINDER_PLACE":
            rank, sid, kind, q, r, m, opens, fit, score, name = rest.split("|")
            info["rightdoor"]["places"].append(dict(rank=int(rank), id=sid, kind=kind, hex=None if q == "-" else (int(q), int(r)),
                                                   minutes=None if m == "-" else float(m), opens=int(opens), fit=float(fit),
                                                   score=float(score), name=name))
        elif tag == "PATHFINDER_ROUTE":
            sid, *pts = rest.split()
            info["rightdoor"]["routes"][sid] = [tuple(int(v) for v in x.split(",")) for x in pts]
        elif tag == "PATHFINDER_ROOM":
            now, waiting, in_care, longest = (int(x) for x in rest.split())
            info["room"] = dict(now=now, waiting=waiting, in_care=in_care, longest=longest)
        elif tag == "PATHFINDER_QUEUE":
            pid, name, ats, waited, hold, r = rest.split("|")
            info.setdefault("queue", []).append(dict(id=int(pid), name=name, ats=int(ats), waited=int(waited), hold=hold == "1",
                                                     r=None if r == "-" else tuple(int(v) for v in r.split(","))))
        elif tag == "PATHFINDER_PROBE":
            ats, eta, xs = rest.split("|")
            p10, p50, p90, ahead = (int(v) for v in eta.split(","))
            info["probe"] = dict(ats=int(ats), p10=p10, p50=p50, p90=p90, ahead=ahead, samples=[int(v) for v in xs.split(",") if v])
        elif tag == "PATHFINDER_UNIT":
            uid, name, kind, tier, frm, connects, gives = rest.split("|")
            info.setdefault("units", []).append(dict(id=uid, name=name, kind=kind, tier=tier, frm=[x for x in frm.split(",") if x],
                                                     connects=connects, gives=gives))
        else:
            raise AssertionError(f"unknown tag {tag!r}")
    return info


def play(durations: list[float]) -> tuple[AppModel, list[str], str]:
    m = AppModel()
    now = utcnow()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        demo.start(m, narrated=True, durations=durations, now=now)
        t = 0.0
        while m.demo["running"] and t < sum(durations) + 10:
            t += 0.25
            at = now + timedelta(seconds=t)
            m.tick(at)
            demo.run(m, at)
    return m, list(m.demo["log"]), out.getvalue()


def test_ten_scenes_emit_every_tag_the_renderer_reads():
    # Scene 7 gets 8 s so Alan's 150-minute stay is over before his call, as in a real narration.
    m, log, printed = play([3.0] * 6 + [8.0] + [3.0] * 3)
    assert m.demo["finished"] and not m.demo["running"] and m.speed == 10 and m.show_captions is False
    assert printed.splitlines() == log, "the log is printed to stdout line for line"
    assert all(" " in line and line.startswith("PATHFINDER_") for line in log)
    tags = {line.split(" ", 1)[0] for line in log}
    assert tags == ALL_TAGS
    info = read_log(log)
    names = [n for n, _ in info["marks"]]
    assert names == ["start", "scene1", "scene2", "scene3", "scene4", "scene5", "jessLeft", "scene6", "scene7", "rightDoor",
                     "scene8", "scene9", "scene10", "end"]
    times = [t for _, t in info["marks"]]
    assert times == sorted(times), "marks are monotonic"
    assert all(len(f"{t:.3f}".split(".")[1]) == 3 for t in times)
    assert info["waiting"] >= 3 and info["in_care"] >= 1
    assert len(info["samples"]) == 100 and len(info["eta"]) == 4 and info["eta"][0] <= info["eta"][1] <= info["eta"][2]
    assert 8 <= info["capture"] <= 11, "the capture time is the scripted dictation time (begin at 2.3 s, add at ~11.8 s)"
    assert info["jess_minutes"] >= 0 and info["jesscase"]["tier"] == 2 and info["jesscase"]["arrival"] == 5 * 1440 + 14 * 60 + 30 - 110
    assert info["jesscase"]["left"] == info["jesscase"]["arrival"] + 136 and info["jesscase"]["due"] == info["jesscase"]["left"] + 480
    assert info["jesscase"]["basis"].startswith("Return-risk table") and info["jesscase"]["reasons"][1] == "Has left before on an earlier visit"
    assert info["follow"][0]["name"] == "Jess T." and info["follow"][0]["hero"] and info["follow"][0]["total"] >= len(info["follow"])
    rd = info["rightdoor"]
    assert rd["suburb"] == "Riverbend" and rd["mode"] == "car" and rd["complete"] and rd["k"] == len(rd["rings"]) - 1
    assert rd["hexes"] == 1 + sum(6 * k for k in range(1, rd["k"] + 1))
    assert rd["need"] == ["1xed", "2xgp"] and rd["hex"][rd["home"]] == 0.0 and rd["corridor"] <= set(rd["hex"])
    assert rd["places"][0]["kind"] == "ed" and rd["places"][0]["rank"] == 1 and all(p["rank"] == i + 1 for i, p in enumerate(rd["places"]))
    assert set(rd["routes"]) == {p["id"] for p in rd["places"] if p["hex"] is not None}
    assert all(r[0] == rd["home"] for r in rd["routes"].values())
    assert len(info["units"]) == 26 and info["units"][0]["id"] == "adt" and info["units"][0]["frm"] == [] and info["units"][6]["frm"] == ["messages"]
    assert info["room"]["waiting"] == len(info["queue"]) and info["probe"]["ats"] == 4 and len(info["probe"]["samples"]) == 100
    assert any(q["hold"] for q in info["queue"]) is False or all(q["r"] is None for q in info["queue"] if q["hold"])
    assert m.demo_view()["logLines"] == len(log) and m.demo_view()["mode"] == "narrated"
    alan = next(e for e in m.sim.episodes if e.isHero and e.name == "Alan P.")
    assert alan.followUp is not None and alan.followUp.nextStep == "GP on Monday. If the chest pain comes back: call 000"


def test_eight_scenes_skip_the_architecture_and_queue():
    m, log, _ = play([2.0] * 8)
    tags = {line.split(" ", 1)[0] for line in log}
    assert tags == ALL_TAGS - TEN_SCENE_ONLY
    names = [n for n, _ in read_log(log)["marks"]]
    assert names == ["start", "scene1", "scene2", "scene3", "scene4", "scene5", "jessLeft", "scene6", "scene7", "rightDoor", "scene8", "end"]
    assert m.demo["finished"]


def test_number_formats():
    _, log, _ = play([3.0] * 10)
    hexes = [l for l in log if l.startswith("PATHFINDER_HEX ")]
    assert all(len(l.split(" ")[3].split(".")[1]) == 1 for l in hexes), "%.1f minutes"
    places = [l.split(" ", 1)[1].split("|") for l in log if l.startswith("PATHFINDER_PLACE ")]
    assert all(len(p[7].split(".")[1]) == 2 and len(p[8].split(".")[1]) == 3 for p in places), "%.2f fit, %.3f score"
    follow = [l.split(" ", 1)[1].split("|") for l in log if l.startswith("PATHFINDER_FOLLOW ")]
    assert all(f[3] == "-" or len(f[3].split(".")[1]) == 3 for f in follow), "%.3f risk"
    capture = next(l for l in log if l.startswith("PATHFINDER_CAPTURE ")).split(" ")[1]
    assert len(capture.split(".")[1]) == 1
    mark = next(l for l in log if l.startswith("PATHFINDER_MARK start ")).split(" ")[2]
    assert len(mark.split(".")[1]) == 3


def test_narrated_needs_scene_lengths():
    m = AppModel()
    with pytest.raises(ValueError):
        demo.start(m, narrated=True, durations=[3.0] * 7)
    with pytest.raises(ValueError):
        demo.start(m, narrated=True)
