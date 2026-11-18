"""Triage-note templates for typing when dictation is off (the static build): ten invented patients, five aged 65+ and
five mental health, each written the way a different nurse would say it, plus the elbow case of
the case film as a nurse would say it at triage. Each carries what the parser and the triage rules
give for it, checked by tests/test_templates.py. Names are invented and are none of the demo's records, so the
"known record" lookup does not fire. Standard library only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Template:
    id: str
    title: str
    cohort: str  # "p65" | "mh" | "other"
    style: str  # a short label the UI can show
    text: str
    complaintKey: Optional[str]
    suggested: int

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "cohort": self.cohort, "style": self.style, "text": self.text,
                "expect": {"complaintKey": self.complaintKey, "suggested": self.suggested, "cohort": self.cohort}}


TEMPLATES: list[Template] = [
    # Aged 65+
    Template("p65-chest-pain", "Chest pain, 77, by ambulance", "p65", "shorthand",
             "Name is Desmond Achebe, 77yo male, central chest pain 1 hr, radiating to the jaw, sweaty, a bit short of "
             "breath. Hx angina, stents 2019. By ambulance. HR 112, BP 160/95, sats 93%, RR 22, temp 36.9, pain 7/10.",
             "chest_pain", 2),
    Template("p65-fall", "Fall at home, 84, on warfarin", "p65", "carer",
             "I'm her daughter. Her name is Elsie Hartigan, she is 84 years old. She had a fall at home this morning "
             "getting out of bed and has hurt her wrist, it's swollen. She's on warfarin for her heart. We came by car. "
             "She's alert and talking. Pulse 92, blood pressure 150 over 88, sats 96 percent, temperature 38.3, "
             "pain 5 out of 10.",
             "fall", 3),
    Template("p65-abdo", "Abdominal pain, 65, two days", "p65", "narrative",
             "Name is Walter Okafor, 65 year old man, abdominal pain for 2 days, lower right side, off his food, no "
             "vomiting, no fever, bowels normal. Drove himself in. Pulse 84, BP 140 over 84, sats 97 percent, "
             "temp 37.2, pain 4 out of 10.",
             "abdo", 4),
    Template("p65-wrist", "Wrist injury, 69, dizzy on standing", "p65", "list",
             "Name is Ingrid Solberg. 69 year old woman. Dizzy on standing, stumbled, hurt right wrist. Swollen, "
             "moving fingers, nothing out of place. Came by taxi. Pulse 76. BP 138 over 80. Sats 98 percent. Temp 36.6. "
             "Pain 3 out of 10.",
             "limb", 4),
    Template("p65-dizzy", "Dizzy spells, 68, a week", "p65", "spoken numbers",
             "Name is Pauline Metcalf, sixty eight year old woman, dizzy for a week, light headed when she stands "
             "up, no falls, eating and drinking normally. Walked in with her husband. Pulse seventy two, blood "
             "pressure one twenty eight over seventy six, sats ninety eight percent, temperature thirty six point "
             "seven, pain one out of ten.",
             "dizzy", 5),
    # Mental health
    Template("mh-overdose", "Overdose, 23, with police", "mh", "shorthand",
             "Name is Tegan Rowe, 23yo female, took a lot of tablets about 1 hr ago, paracetamol, intoxicated, "
             "agitated, says she wants to die and won't wait. With police. HR 98, BP 118/72, sats 99%, GCS 15.",
             "self_harm", 2),
    Template("mh-suicidal", "Suicidal thoughts, no plan, 34", "mh", "narrative",
             "Name is Marcus Delaney, 34 year old man, has had suicidal thoughts for a couple of weeks, no plan and "
             "has not acted on them, hearing voices at night, low mood since he was kicked out of his flat, no "
             "drugs or alcohol, willing to wait, came by bus with a friend. Pulse 88, BP 126 over 80, sats 98 "
             "percent.",
             "suicidal", 3),
    Template("mh-panic", "Panic attack, 29, settling", "mh", "list",
             "Name is Hannah Osei. 29 year old woman. Panic attack at work, anxious, tingling hands, settling now. "
             "Denies thoughts of harming herself. Happy to wait. Walked in. Pulse 104. BP 128 over 82. Sats 98 "
             "percent. Resp rate 20.",
             "anxiety", 4),
    Template("mh-low-mood", "Low mood, 26, flatmate's account", "mh", "carer",
             "I'm his flatmate. His name is Jonah Whitlock, he's 26 years old. He has had a low mood for a month, "
             "not sleeping, not eating much, says he feels hopeless but has no thoughts of hurting himself. He's "
             "happy to wait. I drove him here. Pulse 70, blood pressure 120 over 70.",
             "low_mood", 4),
    Template("mh-medication", "Out of medication, 41, repeat script", "mh", "spoken numbers",
             "Name is Sadie Brennan, forty one year old woman, ran out of her medication three days ago and wants a "
             "repeat script, says her mood is stable, calm, sleeping well, willing to wait, came by train. Pulse "
             "seventy eight, blood pressure one twenty over eighty, sats ninety nine percent.",
             "script", 5),
    # The elbow case from the case film (media/pathfinder_case_elbow.mp4), as a nurse would say it
    Template("case-elbow", "Elbow injury, international student (case file)", "other", "narrative",
             "Adult international student. Fell onto the elbow, isolated elbow injury, swollen and sore to move, no "
             "other pain or injury, walked in. Asked for paracetamol. No known allergies.",
             "fall", 4),
]


def find(id: str) -> Optional[Template]:
    return next((t for t in TEMPLATES if t.id == id), None)
