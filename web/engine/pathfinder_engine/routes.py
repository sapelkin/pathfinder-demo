"""Every route of the API as a plain function over a ``Session``: the one implementation behind the in-browser
``Dispatcher`` (``dispatch.py``) and any HTTP server that hosts the same routes.

Standard library only. A handler takes ``(session, query, body)`` and returns ``{"status": int, "body": ...}``
(plus ``"contentType": "text/plain"`` for the text log); validation failures raise ``ApiError`` with the status the
HTTP API used: 422 for a missing, mistyped or out-of-range field, 400 for a semantic error, 404 for an unknown
episode. ``Session`` supplies the document (``read``/``mutate``), the wall clock and the bot channel.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional, Protocol, TypeVar

from . import __version__ as engine_version
from . import demo, metro, personas, templates, units
from .domain import Outcome, TravelMode, Vitals
from .model import AppModel, parse_iso
from .rightdoor import Purpose
from .units import Deployment

API_VERSION = "0.1.0"
TICK_CAP_MINUTES = 120
JUMP_CAP_MINUTES = 24 * 60
UNCHANGED = object()  # a mutation returns this to say nothing needs saving (an idle tick)

T = TypeVar("T")
Response = dict[str, Any]
Body = dict[str, Any]
Query = dict[str, Any]


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Session(Protocol):
    """What a handler needs from its host: the model, a way to save it, the clock and the bot channel."""

    def read(self) -> AppModel: ...

    def mutate(self, fn: Callable[[AppModel], T]) -> tuple[AppModel, T]: ...

    def now(self) -> datetime: ...

    def send_text(self, service_url: Optional[str], conversation: Optional[str], text: str,
                  recipient_id: Optional[str]) -> bool: ...


def ok(body: Any, status: int = 200) -> Response:
    return {"status": status, "body": body}


# MARK: Validation (the constraints the pydantic models carried, with the same statuses)

def _bad(key: str, msg: str) -> ApiError:
    return ApiError(422, f"body.{key}: {msg}")


def f_int(body: Body, key: str, *, required: bool = False, default: Optional[int] = None,
          lo: Optional[int] = None, hi: Optional[int] = None) -> Optional[int]:
    v = body.get(key)
    if v is None:
        if required:
            raise _bad(key, "Field required")
        return default
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (isinstance(v, float) and not v.is_integer()):
        raise _bad(key, "Input should be a valid integer")
    v = int(v)
    if lo is not None and v < lo:
        raise _bad(key, f"Input should be greater than or equal to {lo}")
    if hi is not None and v > hi:
        raise _bad(key, f"Input should be less than or equal to {hi}")
    return v


def f_float(body: Body, key: str, *, default: Optional[float] = None) -> Optional[float]:
    v = body.get(key)
    if v is None:
        return default
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise _bad(key, "Input should be a valid number")
    return float(v)


def f_bool(body: Body, key: str, *, required: bool = False, default: Optional[bool] = None) -> Optional[bool]:
    v = body.get(key)
    if v is None:
        if required:
            raise _bad(key, "Field required")
        return default
    if not isinstance(v, bool):
        raise _bad(key, "Input should be a valid boolean")
    return v


def f_str(body: Body, key: str, *, required: bool = False, default: Optional[str] = None) -> Optional[str]:
    v = body.get(key)
    if v is None:
        if required:
            raise _bad(key, "Field required")
        return default
    if not isinstance(v, str):
        raise _bad(key, "Input should be a valid string")
    return v


def f_vitals(body: Body, key: str) -> Optional[Vitals]:
    v = body.get(key)
    if v is None:
        return None
    if not isinstance(v, dict):
        raise _bad(key, "Input should be a valid dictionary")
    out = Vitals()
    for name in ("pulse", "systolic", "diastolic", "spo2", "resp", "gcs", "pain"):
        setattr(out, name, f_int(v, name))
    out.temp = f_float(v, "temp")
    return out


def f_time(body: Body, key: str, *, required: bool = False) -> Optional[datetime]:
    v = f_str(body, key, required=required)
    if not v:
        return None
    try:
        return parse_iso(v)
    except ValueError:
        raise ApiError(400, f"{key} must be an ISO 8601 timestamp")


def episode_or_404(m: AppModel, id: int):
    if not 0 <= id < len(m.sim.episodes):
        raise ApiError(404, f"no episode {id}")
    return m.sim.episodes[id]


# MARK: Handlers

def health(s: Session, q: Query, b: Body) -> Response:
    return ok({"ok": True, "version": API_VERSION, "engine": engine_version})


def get_state(s: Session, q: Query, b: Body) -> Response:
    return ok(s.read().state())


def send_eta_updates(s: Session, m: AppModel) -> None:
    """The refreshed expected times, to everyone waiting who messaged the bot."""
    for i in m.sim.waiting:
        e = m.sim.episodes[i]
        if not e.channelUserId or not e.etaConsent:
            continue
        eta = m.etas.get(e.id)
        if eta is None:
            continue
        text = (f"Hi {e.first_name}, an update from {m.hospital.name}: your expected time to be seen is now "
                f"{eta.range_text}. If you feel worse, tell the triage nurse straight away.")
        s.send_text(e.channelServiceUrl, e.channelConversationId, text, e.channelUserId)


def tick(s: Session, q: Query, b: Body) -> Response:
    client_now = f_time(b, "clientNow", required=True)

    def fn(m: AppModel) -> Any:
        before_eta, before_step, before_banner = m.last_eta, (m.demo or {}).get("step"), m.banner
        before_tick, before_running = m.last_tick_utc, m.running
        n = m.tick(client_now, cap=TICK_CAP_MINUTES)
        demo.run(m, s.now())
        if m.last_eta != before_eta:
            send_eta_updates(s, m)
        idle = (n == 0 and (m.demo or {}).get("step") == before_step and m.banner is before_banner
                and m.last_tick_utc == before_tick and m.running == before_running)
        return UNCHANGED if idle else None

    m, _ = s.mutate(fn)
    return ok(m.state())


def settings(s: Session, q: Query, b: Body) -> Response:
    speed = f_float(b, "speed")
    running = f_bool(b, "running")
    deployment = f_str(b, "deployment")
    persona_choice = f_str(b, "personaChoice")
    hospital_id = f_str(b, "hospitalId")
    show_captions = f_bool(b, "showCaptions")
    speak = f_bool(b, "speakFeedback")
    if deployment is not None and deployment not in [d.value for d in Deployment]:
        raise ApiError(400, "deployment must be minimum, standard or full")
    if persona_choice is not None and persona_choice != "random" and personas.find(persona_choice) is None:
        raise ApiError(400, "personaChoice must be random or a persona id")
    if speed is not None and not speed > 0:
        raise ApiError(400, "speed must be positive")
    if hospital_id is not None and metro.find(hospital_id, s.read().seed) is None:
        raise ApiError(400, "hospitalId must be one of GET /hospitals")

    def fn(m: AppModel) -> None:
        if hospital_id is not None and hospital_id != m.hospital.id:
            m.set_hospital(hospital_id)  # rebuilds the afternoon for that ED and stops a running demo
        if speed is not None:
            m.speed = speed
        if running is not None:
            m.set_running(running)
        if deployment is not None:
            m.deployment = Deployment(deployment)
        if persona_choice is not None:
            m.persona_choice = persona_choice
            p = personas.find(persona_choice)
            if p is not None:
                m.persona = p
        if show_captions is not None:
            m.show_captions = show_captions
        if speak is not None:
            m.speak_feedback = speak

    m, _ = s.mutate(fn)
    return ok(m.state())


def reset(s: Session, q: Query, b: Body) -> Response:
    keep = f_bool(b, "keepDemo", default=False)
    m, _ = s.mutate(lambda m: m.reset(keep_demo=bool(keep)))
    return ok(m.state())


def jump(s: Session, q: Query, b: Body) -> Response:
    minutes = f_int(b, "minutes", default=30, lo=0, hi=JUMP_CAP_MINUTES)
    m, _ = s.mutate(lambda m: m.advance(int(minutes or 0)))
    return ok(m.state())


def parse(s: Session, q: Query, b: Body) -> Response:
    transcript = f_str(b, "transcript", default="") or ""
    typed = f_str(b, "typed", default="") or ""
    monitor = f_vitals(b, "monitorVitals")
    looked_up = f_bool(b, "recordLookedUp", default=False)
    return ok(s.read().parse_intake(transcript, typed, monitor, bool(looked_up)).to_dict())


def eta(s: Session, q: Query, b: Body) -> Response:
    ats = f_int(b, "ats", required=True, lo=1, hi=5)
    e, samples = s.read().eta_for(int(ats))
    return ok({"eta": e.to_dict() if e else None, "samples": samples})


def _submit(b: Body) -> dict[str, Any]:
    return {"transcript": f_str(b, "transcript", default="") or "", "typed": f_str(b, "typed", default="") or "",
            "confirmed": f_int(b, "confirmed", lo=1, hi=5), "message_sent": bool(f_bool(b, "messageSent", default=False)),
            "started": f_time(b, "startedAt"), "monitor": f_vitals(b, "monitorVitals")}


def intake_finish(s: Session, q: Query, b: Body) -> Response:
    x = _submit(b)

    def fn(m: AppModel):
        e = m.finish_intake(x["transcript"], x["typed"], x["confirmed"], x["message_sent"], x["started"], x["monitor"])
        if e is None:
            raise ApiError(400, "no category confirmed or suggested")
        return e

    m, _ = s.mutate(fn)
    return ok(m.state())


def intake_redirect(s: Session, q: Query, b: Body) -> Response:
    x = _submit(b)
    m, _ = s.mutate(lambda m: m.redirect_from_intake(x["transcript"], x["typed"], x["confirmed"], x["started"], x["monitor"]))
    return ok(m.state())


def outcome(s: Session, q: Query, b: Body) -> Response:
    id = f_int(b, "id", required=True)
    raw = f_str(b, "outcome", required=True)
    reason = f_str(b, "reason")
    service = f_str(b, "service")
    try:
        o = Outcome(raw)
    except ValueError:
        raise ApiError(400, "outcome must be B, D, R1, R2 or R3")

    def fn(m: AppModel) -> None:
        episode_or_404(m, int(id))
        m.record_outcome(int(id), o, reason=reason, service=service)

    m, _ = s.mutate(fn)
    return ok(m.state())


def contact(s: Session, q: Query, b: Body) -> Response:
    id = f_int(b, "id", required=True)
    reached = f_bool(b, "reached", required=True)
    result = f_str(b, "result", default="") or ""
    next_step = f_str(b, "nextStep")
    reason = f_str(b, "reason")

    def fn(m: AppModel) -> None:
        episode_or_404(m, int(id))
        if not m.record_contact(int(id), bool(reached), result, next_step, reason):
            raise ApiError(400, f"episode {id} is not on the follow-through list")

    m, _ = s.mutate(fn)
    return ok(m.state())


def message(s: Session, q: Query, b: Body) -> Response:
    id = f_int(b, "id", required=True)

    def fn(m: AppModel) -> None:
        e = episode_or_404(m, int(id))
        if e.followUp is None:
            raise ApiError(400, f"episode {id} is not on the follow-through list")
        m.send_follow_message(int(id))
        if e.channelUserId:
            where = f" If you still need care: {e.redirectService}." if e.redirectService else ""
            text = (f"Hi {e.first_name}, this is the {m.hospital.name} follow-through team checking you got the care "
                    f"you need.{where} Reply here or call us; if you feel worse, call 000.")
            s.send_text(e.channelServiceUrl, e.channelConversationId, text, e.channelUserId)

    m, _ = s.mutate(fn)
    return ok(m.state())


def alo(s: Session, q: Query, b: Body) -> Response:
    id = f_int(b, "id", required=True)

    def fn(m: AppModel) -> None:
        e = episode_or_404(m, int(id))
        if e.followUp is None:
            raise ApiError(400, f"episode {id} is not on the follow-through list")
        m.toggle_alo(int(id))

    m, _ = s.mutate(fn)
    return ok(m.state())


def _query_int(q: Query, key: str) -> int:
    v = q.get(key)
    if v is None or v == "":
        raise ApiError(422, f"query.{key}: Field required")
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ApiError(422, f"query.{key}: Input should be a valid integer")


def rightdoor(s: Session, q: Query, b: Body) -> Response:
    id = _query_int(q, "id")
    purpose = q.get("purpose") or None
    mode = q.get("mode") or None
    if purpose is not None and purpose not in [p.value for p in Purpose]:
        raise ApiError(400, "purpose must be redirectNow or nextTime")
    if mode is not None and mode not in [t.value for t in TravelMode]:
        raise ApiError(400, "mode must be walk, bus or car")
    m = s.read()
    episode_or_404(m, id)
    return ok(m.right_door(id, Purpose(purpose) if purpose else None, TravelMode(mode) if mode else None))


def kpi(s: Session, q: Query, b: Body) -> Response:
    m, _ = s.mutate(lambda m: None if m.ensure_metro() else UNCHANGED)  # the measured effect is cached per hour
    return ok(m.kpi())


def get_hospitals(s: Session, q: Query, b: Body) -> Response:
    src = metro.source()
    return ok({"hospitals": [h.to_dict() for h in metro.hospitals(s.read().seed)], "takenText": src["takenText"],
               "takenAt": src["takenAt"], "url": src["url"], "note": src["note"]})


def get_units(s: Session, q: Query, b: Body) -> Response:
    return ok([u.to_dict() for u in units.ALL])


def get_personas(s: Session, q: Query, b: Body) -> Response:
    return ok([p.to_dict() for p in personas.ALL])


def get_templates(s: Session, q: Query, b: Body) -> Response:
    """Triage-note templates for typing when dictation is off, each with what the parser and rules give for it."""
    return ok({"templates": [t.to_dict() for t in templates.TEMPLATES]})


def get_network(s: Session, q: Query, b: Body) -> Response:
    return ok(s.read().network_dict())


def demo_start(s: Session, q: Query, b: Body) -> Response:
    narrated = bool(f_bool(b, "narrated", default=False))
    durations = b.get("durations")
    if durations is not None and (not isinstance(durations, list)
                                  or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in durations)):
        raise _bad("durations", "Input should be a valid list of numbers")
    if narrated and (durations is None or len(durations) not in (8, 10) or any(not x > 0 for x in durations)):
        raise ApiError(400, "the narrated demo needs durations: 8 or 10 scene lengths in seconds")
    m, _ = s.mutate(lambda m: demo.start(m, narrated=narrated, now=s.now(),
                                         durations=[float(x) for x in durations] if durations else None))
    return ok(m.state())


def demo_stop(s: Session, q: Query, b: Body) -> Response:
    m, _ = s.mutate(demo.stop)
    return ok(m.state())


def demo_log(s: Session, q: Query, b: Body) -> Response:
    lines = list((s.read().demo or {}).get("log", []))
    if q.get("format") == "text":
        return {"status": 200, "body": "\n".join(lines) + ("\n" if lines else ""), "contentType": "text/plain"}
    return ok({"lines": lines})


def bot_messages(s: Session, q: Query, b: Body) -> Response:
    """The Bot Framework endpoint (Messenger, Teams). Day 1: a message links the channel user to the current hero
    episode (the latest demo patient) and gets the expected-time text back."""
    activity = b
    if activity.get("type") != "message":
        return ok({})
    user = (activity.get("from") or {}).get("id")
    conversation = (activity.get("conversation") or {}).get("id")
    service_url = activity.get("serviceUrl")
    channel = activity.get("channelId")

    def fn(m: AppModel) -> Optional[str]:
        hero = next((e for e in reversed(m.sim.episodes) if e.isHero), None)
        if hero is None:
            return None
        hero.channelUserId = user
        hero.channelId = channel
        hero.channelServiceUrl = service_url
        hero.channelConversationId = conversation
        return m.intake_message(hero.first_name, m.etas.get(hero.id))

    _, text = s.mutate(fn)
    if text:
        s.send_text(service_url, conversation, text, user)
    return ok({})


Handler = Callable[[Session, Query, Body], Response]

#: Every route of the contract. The bot endpoint needs a server (an inbound webhook), so the in-browser dispatcher
#: leaves it out.
ROUTES: dict[tuple[str, str], Handler] = {
    ("GET", "/health"): health,
    ("GET", "/state"): get_state,
    ("POST", "/tick"): tick,
    ("POST", "/settings"): settings,
    ("POST", "/reset"): reset,
    ("POST", "/jump"): jump,
    ("POST", "/parse"): parse,
    ("POST", "/eta"): eta,
    ("POST", "/intake/finish"): intake_finish,
    ("POST", "/intake/redirect"): intake_redirect,
    ("POST", "/outcome"): outcome,
    ("POST", "/contact"): contact,
    ("POST", "/message"): message,
    ("POST", "/alo"): alo,
    ("GET", "/rightdoor"): rightdoor,
    ("GET", "/kpi"): kpi,
    ("GET", "/units"): get_units,
    ("GET", "/personas"): get_personas,
    ("GET", "/network"): get_network,
    ("GET", "/hospitals"): get_hospitals,
    ("GET", "/templates"): get_templates,
    ("POST", "/demo/start"): demo_start,
    ("POST", "/demo/stop"): demo_stop,
    ("GET", "/demo/log"): demo_log,
}
SERVER_ROUTES: dict[tuple[str, str], Handler] = {("POST", "/api/messages"): bot_messages}


def handle(session: Session, method: str, path: str, query: Optional[Query] = None, body: Optional[Body] = None,
           routes: Optional[dict[tuple[str, str], Handler]] = None) -> Response:
    """Dispatches one request. Unknown paths are 404, known paths with another method 405, errors ``{"error"}``."""
    table = routes if routes is not None else {**ROUTES, **SERVER_ROUTES}
    method = method.upper()
    path = "/" + path.strip("/") if path.strip("/") else "/"
    if body is not None and not isinstance(body, dict):
        return {"status": 422, "body": {"error": "body: Input should be a valid dictionary"}}
    handler = table.get((method, path))
    if handler is None:
        if any(p == path for _, p in table):
            return {"status": 405, "body": {"error": "Method Not Allowed"}}
        return {"status": 404, "body": {"error": "Not Found"}}
    try:
        return handler(session, query or {}, body or {})
    except ApiError as err:
        return {"status": err.status, "body": {"error": err.message}}
