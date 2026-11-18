"""The server-less API: the Dispatcher over an in-memory document, its clock, its export/import, and its imports."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from pathfinder_engine.dispatch import Dispatcher
from pathfinder_engine.personas import ALAN
from pathfinder_engine.routes import ROUTES

T0 = "2026-11-07T06:30:00.000Z"


def test_every_contract_route_is_served():
    d = Dispatcher()
    for (method, path) in ROUTES:
        body = {"clientNow": T0} if path == "/tick" else ({"ats": 2} if path == "/eta" else {})
        query = {"id": 1028} if path == "/rightdoor" else {}
        if path in ("/intake/finish", "/outcome", "/contact", "/message", "/alo"):
            continue  # need a real episode; covered below
        r = d.handle(method, path, query, body)
        assert r["status"] == 200, (method, path, r)
        json.dumps(r["body"])
    assert d.handle("POST", "/api/messages", {}, {"type": "message"})["status"] == 404
    assert d.handle("GET", "/speech/token")["status"] == 404
    assert d.handle("GET", "/tick")["status"] == 405
    assert d.handle("POST", "/eta", {}, {"ats": 9}) == {"status": 422, "body": {"error": "body.ats: Input should be less than or equal to 5"}}
    assert d.handle("POST", "/eta", {}, {})["status"] == 422
    assert d.handle("POST", "/outcome", {}, {"id": 10 ** 6, "outcome": "D"}) == {"status": 404, "body": {"error": "no episode 1000000"}}
    assert d.handle("POST", "/tick", {}, {"clientNow": "yesterday"}) == {"status": 400, "body": {"error": "clientNow must be an ISO 8601 timestamp"}}
    assert d.handle("GET", "/rightdoor", {"id": "x"})["status"] == 422


def test_alan_scenario_on_the_browser_clock():
    fresh = Dispatcher(now=T0)
    s = fresh.handle("GET", "/state")["body"]
    assert s["lastTickUtc"] == T0, "a fresh afternoon is dated by the browser's clock"
    assert s["hospital"]["id"] == "fiona-stanley" and s["ed"]["name"] == "Fiona Stanley Hospital" and s["counters"]["waiting"] == 45
    assert fresh.handle("POST", "/tick", {}, {"clientNow": "2026-11-07T06:30:06.000Z"})["body"]["clockText"] == "Sat 2:31 pm"
    hs = fresh.handle("GET", "/hospitals")["body"]
    assert hs["hospitals"][0]["id"] == "demo" and len(hs["hospitals"]) == 11 and hs["takenText"].startswith("Sunday")
    assert fresh.handle("POST", "/settings", {}, {"hospitalId": "nowhere"})["status"] == 400
    d = Dispatcher()
    s = d.handle("POST", "/settings", {}, {"hospitalId": "demo"}, now=T0)["body"]
    assert s["hospital"]["id"] == "demo" and s["counters"]["waiting"] == 10
    s = d.handle("POST", "/reset", {}, {}, now=T0)["body"]
    assert s["lastTickUtc"] == T0 and s["version"] == 3 and s["clockText"] == "Sat 2:30 pm" and s["hospital"]["id"] == "demo"
    s = d.handle("POST", "/intake/finish", {}, {"transcript": ALAN.script, "typed": "", "confirmed": 2, "messageSent": True,
                                               "startedAt": "2026-11-07T06:29:20.000Z"})["body"]
    alan = next(w for w in s["waiting"] if w["name"] == "Alan P.")
    assert alan["intakeSeconds"] == 40.0, "the capture time is measured on the browser's clock"
    s = d.handle("POST", "/tick", {}, {"clientNow": "2026-11-07T06:30:30.000Z"})["body"]
    assert s["clockText"] == "Sat 2:35 pm" and s["lastTickUtc"] == "2026-11-07T06:30:30.000Z"
    v = s["version"]
    assert d.handle("POST", "/tick", {}, {"clientNow": "2026-11-07T06:30:30.000Z"})["body"]["version"] == v, "an idle tick saves nothing"
    s = d.handle("POST", "/outcome", {}, {"id": alan["id"], "outcome": "D"})["body"]
    s = d.handle("POST", "/contact", {}, {"id": alan["id"], "reached": True, "result": ALAN.callResult, "nextStep": ALAN.nextStep})["body"]
    assert next(f for f in s["followCases"] if f["id"] == alan["id"])["followUp"]["status"] == "closed"
    rd = d.handle("GET", "/rightdoor", {"id": str(alan["id"]), "purpose": "nextTime", "mode": "car"})["body"]
    assert rd["message"] == "For follow-up, from Riverbend by car" and rd["options"][0]["pinned000"]
    text = d.export_document()
    d2 = Dispatcher(document=text)
    assert d2.handle("GET", "/state")["body"] == d.handle("GET", "/state", now="2026-11-07T06:30:30.000Z")["body"]
    d.import_document(text)
    assert d.export_document() == text
    for bad in ("not json", "[]", json.dumps({"sim": {}}), json.dumps({"version": -1, "sim": {}})):
        with pytest.raises(ValueError):
            d.import_document(bad)


def test_narrated_demo_through_the_dispatcher():
    d = Dispatcher()
    r = d.handle("POST", "/demo/start", {}, {"narrated": True, "durations": [1] * 8}, now=T0)
    assert r["status"] == 200 and r["body"]["demo"]["mode"] == "narrated"
    assert d.handle("POST", "/demo/start", {}, {"narrated": True})["status"] == 400
    for ms in range(250, 9001, 250):
        d.handle("POST", "/tick", {}, {"clientNow": f"2026-11-07T06:30:{ms // 1000:02d}.{ms % 1000:03d}Z"})
    log = d.handle("GET", "/demo/log")["body"]["lines"]
    assert log[0].startswith("PATHFINDER_MARK start ") and any(l.startswith("PATHFINDER_MARK end ") for l in log)
    txt = d.handle("GET", "/demo/log", {"format": "text"})
    assert txt["contentType"] == "text/plain" and txt["body"].splitlines() == log
    assert d.handle("GET", "/state")["body"]["demo"]["finished"]


def test_dispatch_imports_only_stdlib_and_the_engine():
    out = subprocess.run([sys.executable, "-X", "importtime", "-c", "import pathfinder_engine.dispatch"],
                         capture_output=True, text=True, check=True).stderr
    modules = {line.split("|")[-1].strip() for line in out.splitlines() if line.startswith("import time:")}
    forbidden = {m for m in modules if m.split(".")[0] in ("fastapi", "pydantic", "starlette", "jwt", "azure", "numpy", "httpx", "uvicorn")}
    assert not forbidden, forbidden
    assert "threading" not in {m for m in modules if m.startswith("pathfinder")} and "pathfinder_engine.routes" in modules
    assert "pathfinder_engine.metro" in modules
