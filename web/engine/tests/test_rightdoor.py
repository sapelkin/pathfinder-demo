"""The hexagon grid, the right-door model and the redirect gate."""
from __future__ import annotations

from conftest import SAT_1430, SAT_1500, episode
from pathfinder_engine import hexgrid, network, rightdoor
from pathfinder_engine.domain import ArrivalMode, Cohort, TravelMode
from pathfinder_engine.network import Kind
from pathfinder_engine.rightdoor import Purpose


def test_hexagon_round_trip_and_rings():
    for x, y in [(3.3, -1.7), (2.3, -1.7), (0.0, 0.0), (-5.2, 4.1)]:
        hx = hexgrid.hex_at(x, y)
        cx, cy = hexgrid.center(hx)
        assert hexgrid.hex_at(cx, cy) == hx, "hexagon round trip"
    hx = hexgrid.hex_at(3.3, -1.7)
    ring = hexgrid.ring(hx, 3)
    assert len(ring) == 18 and all(hexgrid.distance(h, hx) == 3 for h in ring), "ring 3 has 18 hexagons at distance 3"
    assert hexgrid.ring(hx, 0) == [hx]
    assert len(hexgrid.neighbors(hx)) == 6 and all(hexgrid.distance(n, hx) == 1 for n in hexgrid.neighbors(hx))
    assert len(hexgrid.corners(hx)) == 6


def test_metro_coordinates_round_trip():
    lat, lon = network.coordinate(5.3, -0.5)
    x, y = network.xy(lat, lon)
    assert abs(x - 5.3) < 1e-9 and abs(y + 0.5) < 1e-9
    assert network.suburb(5.3, -0.5) == "Riverbend" and network.suburb(-3.7, 2.0) == "Marlow"


def test_right_door_for_alan(alan):
    plan = rightdoor.plan(alan, TravelMode.car, SAT_1500)
    assert plan.search.complete and plan.search.k >= rightdoor.MIN_RINGS, f"the search met every need (k = {plan.search.k})"
    assert plan.edFirst and plan.options[0].service.kind is Kind.ed, "chest pain pins an ED first"
    assert plan.field.minutes[plan.search.home] == 0, "home is at zero minutes"
    ed = plan.options[0]
    walk = rightdoor.plan(alan, TravelMode.walk, SAT_1500)
    on_foot = next((o.minutes for o in walk.options if o.id == ed.id), None)
    assert ed.minutes is not None and on_foot is not None, "the nearest ED is reachable on foot and by car"
    assert on_foot > ed.minutes, f"walking takes longer than driving to the same ED ({on_foot} vs {ed.minutes})"
    assert plan.field.route(ed.service.hex)[0] == plan.search.home and plan.field.route(ed.service.hex)[-1] == ed.service.hex


def test_right_door_for_jess(alan):
    jess = alan
    jess.cohort = Cohort.mh
    jess.complaintKey = "anxiety"
    jess.ats = 4
    jess.age = 24
    plan = rightdoor.plan(jess, TravelMode.bus, SAT_1500)
    assert not plan.edFirst, "a panic attack does not pin the ED"
    assert any(o.service.kind in (Kind.safeHaven, Kind.mentalHealth) for o in plan.options), "mental health options for Jess"
    assert all(o.service.kind not in (Kind.urgentCare, Kind.pharmacy) for o in plan.options)
    marlow = episode("Jess T.", 24, Cohort.mh, "anxiety", 4, ArrivalMode.publicTransport, -3.7, 2.0)
    bus = rightdoor.plan(marlow, TravelMode.bus, SAT_1430)
    assert not bus.edFirst and any(o.service.kind in (Kind.safeHaven, Kind.mentalHealth) for o in bus.options)


def test_open_text():
    assert rightdoor.open_text(0, SAT_1500) == "Open now" and rightdoor.open_text(180, SAT_1500) == "Opens 6 pm", "open text"
    assert rightdoor.open_text(17 * 60, SAT_1500) == "Opens tomorrow 8 am"
    assert rightdoor.open_text(1440 + 17 * 60, SAT_1500) == "Opens Mon 8 am"
    assert rightdoor.open_text(210, SAT_1500) == "Opens 6:30 pm"
    assert rightdoor.bus_wait(SAT_1500) == 7.5 and rightdoor.bus_wait(9 * 60) == 5 and rightdoor.bus_wait(6 * 1440) == 15


def test_redirect_gate_for_alan(alan):
    assert rightdoor.blockers(alan) and not rightdoor.plan(alan, TravelMode.car, SAT_1500, Purpose.redirectNow).options, \
        "chest pain at category 2 is never redirected from triage"
    assert rightdoor.blockers(alan)[0] == "Chest pain can be time-critical"


def test_major_injury_stays(alan):
    trauma = alan
    trauma.complaintKey = "fall"
    trauma.complaint = "Fall"
    trauma.ats = 3
    trauma.arrivalMode = ArrivalMode.ambulance
    evening = 5 * 1440 + 20 * 60
    assert len(rightdoor.blockers(trauma)) >= 2 and network.ed_is_right_door(trauma), \
        "an injury at category 3 by ambulance stays, and the ED is the right door"
    assert "Brought in by ambulance: stays for assessment" in rightdoor.blockers(trauma)
    assert not any(o.service.kind in (Kind.urgentCare, Kind.pharmacy) for o in rightdoor.plan(trauma, TravelMode.car, evening).options), \
        "no urgent care or pharmacy for a major injury, even next time"
    limb = episode("T.", 40, Cohort.other, "limb", 3, ArrivalMode.ambulance, 0.9, 1.3)
    assert len(rightdoor.blockers(limb)) >= 2 and network.ed_is_right_door(limb)


def test_liam_can_be_redirected_now(alan):
    liam = alan
    liam.cohort = Cohort.other
    liam.age = 29
    liam.complaintKey = "sore_throat"
    liam.complaint = "Sore throat"
    liam.ats = 5
    liam.arrivalMode = ArrivalMode.walked
    now = rightdoor.plan(liam, TravelMode.walk, SAT_1500, Purpose.redirectNow)
    assert not rightdoor.blockers(liam) and now.options, "a category-5 sore throat who walked in can be redirected now"
    assert all(o.open and o.service.kind is not Kind.ed and (o.minutes or 0) <= rightdoor.max_redirect_minutes(TravelMode.walk)
               for o in now.options), "redirect now lists only open places within 30 min on foot, never an ED"
    assert not rightdoor.plan(liam, TravelMode.walk, 5 * 1440 + 23 * 60 + 30, Purpose.redirectNow).places, \
        "late on Saturday night nothing is open to redirect to"
    marlow = episode("Liam K.", 29, Cohort.other, "sore_throat", 5, ArrivalMode.walked, -3.3, 3.9)
    assert rightdoor.plan(marlow, TravelMode.walk, SAT_1430, Purpose.redirectNow).options


def test_problem_wording_and_grace():
    grace = episode("Grace B.", 68, Cohort.p65, "sob", 3, ArrivalMode.car, 1.7, 4.8, complaint="Shortness of breath for a day")
    assert grace.problem == "Shortness of breath"
    assert rightdoor.blockers(grace)[0] == "Shortness of breath can be time-critical"
    assert rightdoor.plan(grace, TravelMode.car, SAT_1430).edFirst
    assert episode("x", 30, Cohort.other, "anxiety", 4, ArrivalMode.car, 0, 0, complaint="Panic attack, anxious").problem == "Panic attack"


def test_services_and_hours():
    assert len({s.id for s in network.SERVICES}) == len(network.SERVICES)
    gp = network.service("gp_central")
    assert gp is not None and gp.is_open(SAT_1500) and gp.opens_in(5 * 1440 + 17 * 60) == 2310
    assert network.service("safe_haven").is_open(5 * 1440 + 16 * 60) and not network.service("safe_haven").is_open(5 * 1440 + 20 * 60)
    assert network.redirect_target(episode("x", 30, Cohort.mh, "anxiety", 4, ArrivalMode.car, 0, 0)) == "Mental Health Emergency Response Line"
    assert network.redirect_target(episode("x", 70, Cohort.p65, "fall", 4, ArrivalMode.car, 0, 0)) == "WA Virtual Emergency Department"
    assert network.redirect_target(episode("x", 30, Cohort.other, "rash", 5, ArrivalMode.car, 0, 0)) == "Urgent Care Clinic North"
    net = network.to_dict()
    assert len(net["services"]) == len(network.SERVICES) and len(net["suburbs"]) == 9 and net["hexSize"] == 0.5
    assert all("lat" in s and "hex" in s for s in net["services"])


def test_minutes_text():
    assert rightdoor.minutes_text(None, TravelMode.car) == "No travel"
    assert rightdoor.minutes_text(12.5, TravelMode.walk) == "13 min on foot"
    assert rightdoor.minutes_text(7.4, TravelMode.bus) == "7 min by bus"
