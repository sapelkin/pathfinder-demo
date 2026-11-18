"""The dictation parser and the triage rules against spoken phrasing, including variants of the same note."""
from __future__ import annotations

import pytest

from pathfinder_engine import parser, personas, triage
from pathfinder_engine.domain import ArrivalMode
from pathfinder_engine.parser import FINISH, SEND, confirm


def suggestion(text: str):
    return triage.suggestion(triage.evaluate(parser.parse(text)))


# Numbers as speech recognition writes them, and as words.

def test_hero_sentence_with_digits():
    f = parser.parse("72-year-old man, chest pain for 2 hours, worse when breathing in. Pulse 104, BP 150/90, sats 95%, pain 6 out of 10.")
    assert f.age == 72 and f.sex == "M", "age and sex from digits"
    assert f.complaintKey == "chest_pain" and f.duration == "2 hours", "complaint and duration"
    assert f.vitals.pulse == 104 and f.vitals.systolic == 150 and f.vitals.diastolic == 90, "pulse and BP with a slash"
    assert f.vitals.spo2 == 95 and f.vitals.pain == 6, "sats with % and pain out of 10"
    assert "pleuritic" in f.redFlags, "worse when breathing in"
    assert triage.suggestion(triage.evaluate(f)) == 2, "72-year-old with chest pain suggests category 2"


def test_numbers_in_words():
    f = parser.parse("seventy two year old woman, blood pressure one fifty over ninety, heart rate one hundred and ten, temperature thirty eight point five, looks lethargic")
    assert f.age == 72 and f.sex == "F", "age in words"
    assert f.vitals.systolic == 150 and f.vitals.diastolic == 90, "one fifty over ninety"
    assert f.vitals.pulse == 110, "one hundred and ten"
    assert f.vitals.temp == 38.5, "thirty eight point five"
    assert any(h.ats == 2 and "lethargy" in h.text for h in triage.evaluate(f)), "fever with lethargy is category 2"


def test_numbers_in_words_variant():
    f = parser.parse("seventy two year old woman, fever, lethargic, blood pressure one fifty over ninety, pulse one hundred and ten, temp thirty eight point five")
    assert (f.age, f.sex) == (72, "F")
    assert (f.vitals.systolic, f.vitals.diastolic, f.vitals.pulse) == (150, 90, 110)
    assert f.vitals.temp == pytest.approx(38.5)
    assert any(h.ats == 2 and "lethargy" in h.text for h in triage.evaluate(f))


def test_bp_heard_as_a_time():
    f = parser.parse("BP 1:50 over 90, sats ninety one per cent, resp rate 26")
    assert f.vitals.systolic == 150, "BP heard as a time, 1:50"
    assert f.vitals.spo2 == 91 and f.vitals.resp == 26, "per cent and resp rate"
    assert triage.suggestion(triage.evaluate(f)) == 3, "SpO2 91 suggests category 3"
    assert parser.parse("short of breath, bp 1:50 over 90, sats 91 per cent, resp rate 26").vitals.systolic == 150


def test_words_to_numbers_helpers():
    assert parser.words_to_numbers("a hundred and four") == "104"
    assert parser.words_to_numbers("one forty five, then") == "145, then"
    assert parser.words_to_numbers("thirty eight point five.") == "38.5."
    assert parser.normalise("Sats 95%, per cent, Sp O2 96") == "sats 95 percent, percent, spo2 96"


# Mental health phrasing.

def test_suicidal_and_distressed():
    f = parser.parse("24 year old woman, suicidal thoughts, very distressed, says she won't wait")
    assert f.complaintKey == "suicidal" and "suicidal" in f.mh and "distress" in f.mh, "suicidal and distressed"
    assert "wont_wait" in f.mh, "won't wait"
    assert triage.suggestion(triage.evaluate(f)) == 2, "suicidal and unable to wait safely suggests category 2"
    f = parser.parse("24 year old woman, suicidal thoughts, very distressed and crying, says she won't wait")
    assert "distress" in f.mh and "wont_wait" in f.mh and triage.suggestion(triage.evaluate(f)) == 2


def test_anxiety_without_suicidal_ideation():
    assert suggestion("anxious, panic attack, calm now, happy to wait") == 4, "anxiety without suicidal ideation suggests category 4"
    assert suggestion("anxious, panic attack, willing to wait") == 4


def test_overdose_phrasing():
    f = parser.parse("took too many pills an hour ago")
    assert f.complaintKey == "self_harm" and "self_harm_act" in f.mh, "overdose phrasing"
    assert triage.suggestion(triage.evaluate(f)) == 2, "self-harm attempt suggests category 2"
    f = parser.parse("took too many tablets last night")
    assert f.complaintKey == "self_harm" and "self_harm_act" in f.mh and triage.suggestion(triage.evaluate(f)) == 2


def test_wont_wait_removes_willing_to_wait():
    f = parser.parse("says he is not willing to wait")
    assert "wont_wait" in f.mh and "willing_wait" not in f.mh


def test_sprain_and_walk_in():
    f = parser.parse("sprained ankle, pain 3 out of 10, walked in")
    assert f.complaintKey == "limb" and f.arrivalMode in (ArrivalMode.walked, ArrivalMode.car), "ankle and walk-in"
    assert triage.suggestion(triage.evaluate(f)) == 4, "sprain suggests category 4"
    f = parser.parse("twisted his ankle playing football, walked in, pain 3 out of 10")
    assert f.complaintKey == "limb" and triage.suggestion(triage.evaluate(f)) == 4


# Voice commands, counted in order.

def test_commands_in_order():
    cmds = parser.commands("blah blah. Confirm category two. Send the message. Add to the waiting room.")
    assert cmds == [confirm(2), SEND, FINISH], f"commands: confirm, send, finish (got {cmds})"
    assert parser.commands("category 3")[0] == confirm(3), "bare 'category 3'"
    assert parser.commands("chest pain. confirm category 2. send the message. add him to the waiting room") == [confirm(2), SEND, FINISH]
    assert parser.commands("... pain 5 out of 10. Confirm category 3.") == [confirm(3)]
    assert [c.text for c in parser.commands("obs from the monitor, then redirect her to the clinic")] == ["fromMonitor", "redirect"]


# Names and records.

def test_name_and_known_record():
    f = parser.parse("Name is Alan Pierce, chest pain")
    assert f.name == "Alan Pierce" and personas.find_record(f.name) is not None, "name and known record"
    assert personas.find_record("Nobody Here") is None
    assert personas.find_record("jess tran") is not None


# Arrival modes as spoken.

def test_arrival_modes():
    assert parser.parse("came by bus").arrivalMode is ArrivalMode.publicTransport, "came by bus"
    assert parser.parse("brought in by ambulance").arrivalMode is ArrivalMode.ambulance, "by ambulance"
    assert parser.parse("walked in this morning").arrivalMode is ArrivalMode.walked, "walked in"
    assert parser.parse("the police brought him").arrivalMode is ArrivalMode.police
    assert parser.parse("got an uber here").arrivalMode is ArrivalMode.taxi
    assert parser.parse("her son drove her").arrivalMode is ArrivalMode.car


def test_grace_sentence():
    f = parser.parse("Name is Grace Bennett, 68 year old woman, short of breath for a day, hurts to breathe. Came by car. Pulse 96, BP 138 over 84, sats 92 percent, resp rate 24, pain 5 out of 10.")
    assert f.name == "Grace Bennett" and personas.find_record(f.name) is not None
    assert (f.age, f.sex, f.complaintKey, f.duration) == (68, "F", "sob", "a day")
    assert f.arrivalMode is ArrivalMode.car and "pleuritic" in f.redFlags
    assert (f.vitals.pulse, f.vitals.systolic, f.vitals.spo2, f.vitals.resp, f.vitals.pain) == (96, 138, 92, 24, 5)
    assert triage.suggestion(triage.evaluate(f)) == 3


def test_duration_since_and_other_vitals():
    f = parser.parse("vomiting since last night, can't keep fluids down, temp 38.9, GCS 14, RR 22, age 70")
    assert f.duration == "since last night" and f.complaintKey == "vomiting" and "dehydrated" in f.redFlags
    assert f.vitals.temp == 38.9 and f.vitals.gcs == 14 and f.vitals.resp == 22 and f.age == 70
    hits = triage.evaluate(f)
    assert any(h.text == "Persistent vomiting with dehydration" for h in hits)
    assert any(h.text == "Drowsy, decreased responsiveness (GCS under 13)" for h in hits) is False


def test_out_of_range_vitals_are_dropped():
    f = parser.parse("pulse 300, sats 40, bp 400 over 20, temp 50, pain 12 out of 10")
    assert f.vitals.pulse is None and f.vitals.spo2 is None and f.vitals.systolic is None and f.vitals.temp is None
    assert f.vitals.pain is None


# The demo's personas: each script parses to its category, finds its record, and is a different person.

@pytest.mark.parametrize("p", personas.ALL, ids=[p.id for p in personas.ALL])
def test_persona_scripts(p):
    pf = parser.parse(p.script)
    assert pf.name == p.name and personas.find_record(pf.name) is not None, f"{p.id}: the name is heard and the record found"
    assert pf.age == p.age and pf.sex == p.sex, f"{p.id}: age {pf.age} and sex {pf.sex} as scripted"
    assert triage.suggestion(triage.evaluate(pf)) == p.category, f"{p.id}: the rules suggest category {p.category}"
    assert parser.commands(p.script + f" Confirm category {p.category}. Send the message. Add to the waiting room.") == [confirm(p.category), SEND, FINISH], f"{p.id}: the three commands"
    assert p.age >= 65 or p.priorVisits >= 2, f"{p.id}: the follow-up story holds (65+ or repeat visits)"


def test_personas_distinct_and_random():
    assert len({p.short for p in personas.ALL}) == len(personas.ALL) and len({p.id for p in personas.ALL}) == len(personas.ALL)
    assert personas.random(excluding="alan").id != "alan"


def test_safety_actions_and_stream():
    f = parser.parse("Name is Alan Pierce, 72 year old man, chest pain")
    assert "Notify the medical officer now" in triage.safety_actions(2, f)
    assert triage.stream(2, f) == "Resuscitation or acute area"
    mh = parser.parse("suicidal thoughts, won't wait")
    acts = triage.safety_actions(2, mh)
    assert acts[0] == "Keep in line of sight while waiting" and acts[-1] == "Offer an Aboriginal Liaison Officer if the patient identifies as Aboriginal"
    assert triage.stream(3, mh) == "Mental health team review"
    assert triage.stream(4, parser.parse("sprained ankle")) == "Fast track"
    assert triage.stream(5, parser.parse("sore throat")) == "Fast track, or redirect to an urgent care clinic"


def test_hits_sorted_and_sourced():
    hits = triage.evaluate(parser.parse("72 year old, chest pain, pain 9 out of 10, sats 88"))
    assert [h.ats for h in hits] == sorted(h.ats for h in hits)
    assert {h.source.value for h in hits} <= {"ACEM descriptor", "WA triage descriptor", "Demo threshold"}
    assert hits[0].to_dict()["source"] in ("ACEM descriptor", "Demo threshold")
