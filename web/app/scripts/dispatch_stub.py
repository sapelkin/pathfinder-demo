"""An interim in-process dispatcher for the browser build: every route of docs/web_api.md over AppModel, with the
same shapes and errors as web/api/pathfinder_api/main.py, minus HTTP. Used only until the engine ships its own
``pathfinder_engine/dispatch.py`` (the asset script injects this file into the wheel when that one is missing)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from pathfinder_engine import __version__ as engine_version
from pathfinder_engine import demo, network, personas, units
from pathfinder_engine.domain import Outcome, TravelMode, Vitals
from pathfinder_engine.model import AppModel, parse_iso
from pathfinder_engine.rightdoor import Purpose
from pathfinder_engine.seed import SeedFile
from pathfinder_engine.units import Deployment

VERSION = "0.1.0"
TICK_CAP_MINUTES = 120
JUMP_CAP_MINUTES = 24 * 60


class HTTPError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _vitals(d: Any) -> Optional[Vitals]:
    if not isinstance(d, dict):
        return None
    keys = ("pulse", "systolic", "diastolic", "spo2", "resp", "temp", "gcs", "pain")
    return Vitals(**{k: d.get(k) for k in keys})


def _int(v: Any, name: str, lo: Optional[int] = None, hi: Optional[int] = None) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise HTTPError(422, f"{name}: must be an integer")
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        raise HTTPError(422, f"{name}: out of range")
    return n


class Dispatcher:
    def __init__(self, seed: Optional[SeedFile] = None):
        self.seed = seed or SeedFile.load()
        self.model = AppModel(seed=self.seed)
        self.model.version = 1

    # -- the document
    def export_document(self) -> str:
        d = self.model.to_dict()
        d["version"] = int(self.model.version)
        return json.dumps({"version": d["version"], **{k: v for k, v in d.items() if k != "version"}}, separators=(",", ":"))

    def import_document(self, text: str) -> None:
        doc = json.loads(text)
        if not isinstance(doc, dict) or "sim" not in doc and "episodes" not in doc and "now" not in doc:
            raise HTTPError(400, "not a Pathfinder document")
        m = AppModel.from_dict(doc, seed=self.seed)
        m.version = int(doc.get("version", 1))
        self.model = m

    def _bump(self) -> None:
        self.model.version = int(getattr(self.model, "version", 0)) + 1

    # -- routing
    def handle(self, method: str, path: str, query: Optional[dict] = None, body: Optional[dict] = None) -> dict[str, Any]:
        query = query or {}
        body = body if isinstance(body, dict) else {}
        method = method.upper()
        path = path.rstrip("/") or "/"
        try:
            fn = self._routes().get((method, path))
            if fn is None:
                return {"status": 404, "body": {"error": f"no route {method} {path}"}}
            return {"status": 200, "body": fn(query, body)}
        except HTTPError as e:
            return {"status": e.status, "body": {"error": e.detail}}
        except Exception as e:  # noqa: BLE001
            return {"status": 500, "body": {"error": f"{type(e).__name__}: {e}"}}

    def _routes(self):
        return {
            ("GET", "/health"): lambda q, b: {"ok": True, "version": VERSION, "engine": engine_version, "mode": "local"},
            ("GET", "/state"): lambda q, b: self.model.state(),
            ("POST", "/tick"): self.tick,
            ("POST", "/settings"): self.settings,
            ("POST", "/reset"): self.reset,
            ("POST", "/jump"): self.jump,
            ("POST", "/parse"): self.parse,
            ("POST", "/eta"): self.eta,
            ("POST", "/intake/finish"): self.intake_finish,
            ("POST", "/intake/redirect"): self.intake_redirect,
            ("POST", "/outcome"): self.outcome,
            ("POST", "/contact"): self.contact,
            ("POST", "/message"): self.message,
            ("POST", "/alo"): self.alo,
            ("GET", "/rightdoor"): self.rightdoor,
            ("GET", "/kpi"): lambda q, b: self.model.kpi(),
            ("GET", "/units"): lambda q, b: [u.to_dict() for u in units.ALL],
            ("GET", "/personas"): lambda q, b: [p.to_dict() for p in personas.ALL],
            ("GET", "/network"): lambda q, b: network.to_dict(),
            ("POST", "/demo/start"): self.demo_start,
            ("POST", "/demo/stop"): self.demo_stop,
            ("GET", "/demo/log"): lambda q, b: {"lines": list((self.model.demo or {}).get("log", []))},
            ("GET", "/speech/token"): self.speech_token,
            ("POST", "/api/messages"): lambda q, b: {},
        }

    def _episode(self, id: Any):
        n = _int(id, "id")
        if not 0 <= n < len(self.model.sim.episodes):
            raise HTTPError(404, f"no episode {n}")
        return self.model.sim.episodes[n]

    # -- handlers
    def tick(self, q, b):
        try:
            client_now = parse_iso(str(b.get("clientNow", "")))
        except (ValueError, TypeError):
            raise HTTPError(400, "clientNow must be an ISO 8601 timestamp")
        m = self.model
        before_eta, before_step, before_banner = m.last_eta, (m.demo or {}).get("step"), m.banner
        before_tick, before_running = m.last_tick_utc, m.running
        n = m.tick(client_now, cap=TICK_CAP_MINUTES)
        demo.run(m, _utcnow())
        idle = (n == 0 and (m.demo or {}).get("step") == before_step and m.banner is before_banner
                and m.last_tick_utc == before_tick and m.running == before_running)
        if not idle:
            self._bump()
        return m.state()

    def settings(self, q, b):
        m = self.model
        dep = b.get("deployment")
        if dep is not None and dep not in [d.value for d in Deployment]:
            raise HTTPError(400, "deployment must be minimum, standard or full")
        pc = b.get("personaChoice")
        if pc is not None and pc != "random" and personas.find(pc) is None:
            raise HTTPError(400, "personaChoice must be random or a persona id")
        speed = b.get("speed")
        if speed is not None and not float(speed) > 0:
            raise HTTPError(400, "speed must be positive")
        if speed is not None:
            m.speed = float(speed)
        if b.get("running") is not None:
            m.set_running(bool(b["running"]))
        if dep is not None:
            m.deployment = Deployment(dep)
        if pc is not None:
            m.persona_choice = pc
            p = personas.find(pc)
            if p is not None:
                m.persona = p
        if b.get("showCaptions") is not None:
            m.show_captions = bool(b["showCaptions"])
        if b.get("speakFeedback") is not None:
            m.speak_feedback = bool(b["speakFeedback"])
        self._bump()
        return m.state()

    def reset(self, q, b):
        self.model.reset(keep_demo=bool(b.get("keepDemo", False)))
        self._bump()
        return self.model.state()

    def jump(self, q, b):
        self.model.advance(_int(b.get("minutes", 30), "minutes", 0, JUMP_CAP_MINUTES))
        self._bump()
        return self.model.state()

    def parse(self, q, b):
        return self.model.parse_intake(str(b.get("transcript", "")), str(b.get("typed", "")), _vitals(b.get("monitorVitals")),
                                       bool(b.get("recordLookedUp", False))).to_dict()

    def eta(self, q, b):
        e, samples = self.model.eta_for(_int(b.get("ats"), "ats", 1, 5))
        return {"eta": e.to_dict() if e else None, "samples": samples}

    def _started(self, b):
        s = b.get("startedAt")
        if not s:
            return None
        try:
            return parse_iso(str(s))
        except ValueError:
            raise HTTPError(400, "startedAt must be an ISO 8601 timestamp")

    def _confirmed(self, b):
        c = b.get("confirmed")
        return None if c is None else _int(c, "confirmed", 1, 5)

    def intake_finish(self, q, b):
        e = self.model.finish_intake(str(b.get("transcript", "")), str(b.get("typed", "")), self._confirmed(b),
                                     bool(b.get("messageSent", False)), self._started(b), _vitals(b.get("monitorVitals")))
        if e is None:
            raise HTTPError(400, "no category confirmed or suggested")
        self._bump()
        return self.model.state()

    def intake_redirect(self, q, b):
        self.model.redirect_from_intake(str(b.get("transcript", "")), str(b.get("typed", "")), self._confirmed(b),
                                        self._started(b), _vitals(b.get("monitorVitals")))
        self._bump()
        return self.model.state()

    def outcome(self, q, b):
        try:
            o = Outcome(b.get("outcome"))
        except ValueError:
            raise HTTPError(400, "outcome must be B, D, R1, R2 or R3")
        self._episode(b.get("id"))
        self.model.record_outcome(int(b["id"]), o, reason=b.get("reason"), service=b.get("service"))
        self._bump()
        return self.model.state()

    def contact(self, q, b):
        self._episode(b.get("id"))
        if not self.model.record_contact(int(b["id"]), bool(b.get("reached")), str(b.get("result", "")), b.get("nextStep"), b.get("reason")):
            raise HTTPError(400, f"episode {b['id']} is not on the follow-through list")
        self._bump()
        return self.model.state()

    def message(self, q, b):
        e = self._episode(b.get("id"))
        if e.followUp is None:
            raise HTTPError(400, f"episode {b['id']} is not on the follow-through list")
        self.model.send_follow_message(int(b["id"]))
        self._bump()
        return self.model.state()

    def alo(self, q, b):
        e = self._episode(b.get("id"))
        if e.followUp is None:
            raise HTTPError(400, f"episode {b['id']} is not on the follow-through list")
        self.model.toggle_alo(int(b["id"]))
        self._bump()
        return self.model.state()

    def rightdoor(self, q, b):
        if q.get("id") in (None, ""):
            raise HTTPError(422, "id: field required")
        purpose, mode = q.get("purpose") or None, q.get("mode") or None
        if purpose is not None and purpose not in [p.value for p in Purpose]:
            raise HTTPError(400, "purpose must be redirectNow or nextTime")
        if mode is not None and mode not in [t.value for t in TravelMode]:
            raise HTTPError(400, "mode must be walk, bus or car")
        e = self._episode(q.get("id"))
        return self.model.right_door(e.id, Purpose(purpose) if purpose else None, TravelMode(mode) if mode else None)

    def demo_start(self, q, b):
        narrated = bool(b.get("narrated", False))
        durations = b.get("durations")
        if narrated and (durations is None or len(durations) not in (8, 10) or any(not x > 0 for x in durations)):
            raise HTTPError(400, "the narrated demo needs durations: 8 or 10 scene lengths in seconds")
        demo.start(self.model, narrated=narrated, now=_utcnow(), durations=durations)
        self._bump()
        return self.model.state()

    def demo_stop(self, q, b):
        demo.stop(self.model)
        self._bump()
        return self.model.state()

    def speech_token(self, q, b):
        raise HTTPError(404, "Dictation is not configured on this build")
