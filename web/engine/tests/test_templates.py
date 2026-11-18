"""The typed triage-note templates: each parses to what it says it does, none speaks a command, the categories spread
2–5 in each half, and the elbow case passes the redirect gate once it is in the demo room."""
from __future__ import annotations

from collections import Counter

import pytest

from pathfinder_engine import parser, personas, rightdoor, templates, triage
from pathfinder_engine.domain import ArrivalMode
from pathfinder_engine.model import AppModel
from pathfinder_engine.routes import ROUTES

STYLES = {"shorthand", "narrative", "carer", "list", "spoken numbers"}


def _cohort(f: parser.IntakeForm) -> str:
    age = f.age if f.age is not None else 40
    return "mh" if triage.is_mental_health(f) else ("p65" if age >= 65 else "other")


@pytest.mark.parametrize("t", templates.TEMPLATES, ids=[t.id for t in templates.TEMPLATES])
def test_template_parses_as_expected(t):
    f = parser.parse(t.text)
    hits = triage.evaluate(f)
    assert f.complaintKey == t.complaintKey
    assert triage.suggestion(hits) == t.suggested, [(h.ats, h.text) for h in hits]
    assert _cohort(f) == t.cohort
    assert parser.commands(t.text) == [], "a template must not speak a voice command"
    assert personas.find_record(f.name) is None, "no demo record fires"
    assert t.style in STYLES and t.to_dict()["expect"] == {"complaintKey": t.complaintKey, "suggested": t.suggested, "cohort": t.cohort}
    if t.id != "case-elbow":
        assert f.name and f.age and f.sex and f.arrivalMode is not None and not f.vitals.is_empty


def test_catalogue_shape_and_spread():
    assert len(templates.TEMPLATES) == 11 and len({t.id for t in templates.TEMPLATES}) == 11
    for cohort in ("p65", "mh"):
        half = [t for t in templates.TEMPLATES if t.cohort == cohort]
        assert len(half) == 5 and len({t.style for t in half}) == 5, "five styles per half"
        counts = Counter(t.suggested for t in half)
        assert counts[2] >= 1 and counts[3] >= 1 and counts[4] >= 2 and counts[5] >= 1
        assert len({parser.parse(t.text).name for t in half}) == 5 and len({t.complaintKey for t in half}) == 5
    forms = [parser.parse(t.text) for t in templates.TEMPLATES]
    assert len({f.arrivalMode for f in forms}) >= 5 and len({f.sex for f in forms if f.sex}) == 2
    # The vocabulary exercised: the aged-care and mental-health complaints the parser knows.
    text = " ".join(t.text.lower() for t in templates.TEMPLATES)
    for word in ("fall", "chest pain", "short of breath", "abdominal", "dizzy", "wrist", "panic", "low mood", "suicidal",
                 "tablets", "hearing voices", "agitated", "intoxicated", "kicked out", "willing to wait", "won't wait"):
        assert word in text, word
    mh_flags = set().union(*(parser.parse(t.text).mh for t in templates.TEMPLATES if t.cohort == "mh"))
    assert {"self_harm_act", "suicidal", "psychosis", "agitation", "crisis", "anxiety", "low_mood", "wont_wait", "willing_wait", "medication"} <= mh_flags
    red = set().union(*(parser.parse(t.text).redFlags for t in templates.TEMPLATES))
    assert {"radiating", "sweaty", "cardiac_history", "blood_thinners"} <= red
    assert ("GET", "/templates") in ROUTES


def test_elbow_case_is_faithful_and_passes_the_gate():
    t = templates.find("case-elbow")
    f = parser.parse(t.text)
    assert f.age is None and f.vitals.pain is None and f.sex is None, "the case gives no age, sex or pain score"
    assert f.arrivalMode is ArrivalMode.walked and f.complaintKey == "fall" and not f.redFlags and not f.mh
    assert [h.text for h in triage.evaluate(f)] == ["Minor fall"]
    m = AppModel(hospital_id="demo")
    e = m.finish_intake(t.text)
    assert e is not None and e.ats == 4 and e.descriptor == "Minor fall" and e.arrivalMode is ArrivalMode.walked
    assert rightdoor.blockers(e) == [] and m.redirect_options(e), "category 4, walked in, no red flags: the gate opens"
    assert m.redirect_message(e).startswith("Open now, within 30 min on foot of ")


def test_negated_allergies_are_not_a_reaction():
    for text in ("fell on the elbow, no known allergies", "nil allergies, sore throat", "denies any allergies. pulse 80"):
        assert parser.parse(text).complaintKey != "allergy", text
    assert parser.parse("nil allergies, sore throat").complaintKey == "sore_throat"
    assert parser.parse("no known allergies, pulse 80").vitals.pulse == 80
    assert parser.parse("allergic reaction to peanuts, swollen lips").complaintKey == "allergy"
    assert parser.parse("anaphylaxis, swollen tongue, no known drug allergies").complaintKey == "allergy"
