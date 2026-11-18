"""A transparent rule table that suggests an Australasian Triage Scale category. The nurse always decides.

Descriptors follow ACEM's G24 guideline (Nov 2023) and the
WA Country Health Service triage procedure (2025). Numeric cut-offs that are not in those documents are marked
"demo" and still need clinical validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .parser import IntakeForm


class Source(str, Enum):
    acem = "ACEM descriptor"
    wa = "WA triage descriptor"
    demo = "Demo threshold"


@dataclass(frozen=True)
class RuleHit:
    ats: int
    text: str
    source: Source

    @property
    def id(self) -> str:
        return f"{self.ats}-{self.text}"

    def to_dict(self) -> dict:
        return {"ats": self.ats, "text": self.text, "source": self.source.value}


_MH_KEYS = ["suicidal", "self_harm", "anxiety", "psychosis", "agitation", "low_mood", "crisis", "intox"]


def evaluate(f: IntakeForm) -> list[RuleHit]:
    hits: list[RuleHit] = []

    def add(ats: int, text: str, src: Source) -> None:
        if not any(h.text == text for h in hits):
            hits.append(RuleHit(ats, text, src))

    v = f.vitals
    age = f.age if f.age is not None else 40
    key = f.complaintKey or ""
    flags = f.redFlags
    mh = f.mh

    # Physiology (ACEM G24 indicative descriptors).
    if v.resp is not None and v.resp < 10:
        add(1, "Respiratory rate under 10 a minute", Source.acem)
    if v.systolic is not None and v.systolic < 80:
        add(1, "Blood pressure under 80 systolic", Source.acem)
    if v.gcs is not None and v.gcs < 9:
        add(1, "Unresponsive or responds to pain only (GCS under 9)", Source.acem)
    if v.pulse is not None and (v.pulse < 50 or v.pulse > 150):
        add(2, "Heart rate under 50 or over 150", Source.acem)
    if v.gcs is not None and 9 <= v.gcs < 13:
        add(2, "Drowsy, decreased responsiveness (GCS under 13)", Source.acem)
    if v.spo2 is not None and v.spo2 < 90:
        add(2, "Severe respiratory distress (SpO₂ under 90%)", Source.demo)
    if v.spo2 is not None and 90 <= v.spo2 < 94:
        add(3, "Moderate shortness of breath (SpO₂ 90–93%)", Source.demo)
    if v.temp is not None and v.temp >= 38.0:
        if "lethargic" in flags:
            add(2, "Fever with signs of lethargy", Source.acem)
        else:
            add(3, "Fever, physiologically stable", Source.demo)
    if v.systolic is not None and v.systolic >= 200:
        add(3, "Severe hypertension", Source.acem)

    # Pain (ACEM descriptors; the mapping from a 0–10 score is a demo choice).
    if v.pain is not None:
        p = v.pain
        if 8 <= p <= 10:
            add(2, "Very severe pain", Source.demo)
        elif 5 <= p <= 7:
            add(3, "Moderately severe pain requiring analgesia", Source.demo)
        elif 3 <= p <= 4:
            add(4, "Moderate pain, some risk features", Source.demo)
        else:
            add(5, "Minimal pain, no high-risk features", Source.demo)

    # Presenting problem (ACEM descriptors).
    if key == "chest_pain":
        if age >= 35 or "radiating" in flags or "sweaty" in flags or "cardiac_history" in flags:
            add(2, "Chest pain of likely cardiac nature", Source.acem)
        else:
            add(3, "Chest pain, likely non-cardiac and moderate severity", Source.acem)
    elif key == "stroke":
        add(2, "Acute stroke symptoms", Source.acem)
    elif key == "seizure":
        if "ongoing" in flags:
            add(1, "Ongoing or prolonged seizure", Source.acem)
        else:
            add(3, "Seizure, now alert", Source.acem)
    elif key == "head_injury":
        if "loc" in flags:
            add(3, "Head injury with short loss of consciousness, now alert", Source.acem)
        else:
            add(4, "Minor head injury, no loss of consciousness", Source.acem)
    elif key == "abdo":
        if age > 65:
            add(3, "Abdominal pain, patient over 65", Source.acem)
        else:
            add(4, "Non-specific abdominal pain", Source.acem)
    elif key == "sob":
        add(3, "Moderate shortness of breath", Source.acem)
    elif key == "vomiting":
        if "dehydrated" in flags:
            add(3, "Persistent vomiting with dehydration", Source.acem)
        else:
            add(4, "Vomiting or diarrhoea without dehydration", Source.acem)
    elif key == "limb":
        if "deformity" in flags:
            add(3, "Moderate limb injury, deformity", Source.acem)
        else:
            add(4, "Minor limb trauma, possible fracture", Source.acem)
    elif key == "laceration":
        add(4, "Uncomplicated laceration needing repair", Source.acem)
    elif key == "fall":
        if age >= 65:
            add(3, "Fall in an older person: high-risk history", Source.demo)
        else:
            add(4, "Minor fall", Source.demo)
    elif key == "confusion":
        add(3, "New confusion", Source.demo)
    elif key in ("sore_throat", "rash", "script"):
        add(5, "Minor symptoms of existing stable illness", Source.acem)
    if "syncope" in flags:
        add(3, "Collapse or fainting, now alert", Source.demo)

    # Mental health (WA triage descriptors, from the Emergency Triage Education Kit).
    if "weapon" in mh or "violent" in mh:
        add(1, "Definite danger to life: violent, or possession of a weapon", Source.wa)
    if "self_harm_act" in mh:
        add(2, "Attempt at self-harm or threat of self-harm", Source.wa)
    if "aggression" in mh:
        add(2, "Physically or verbally aggressive", Source.wa)
    if "wont_wait" in mh and ("suicidal" in mh or "self_harm_act" in mh):
        add(2, "Unable to wait safely", Source.wa)
    if "suicidal" in mh:
        add(3, "Suicidal ideation", Source.wa)
    if "psychosis" in mh:
        add(3, "Psychotic symptoms: hallucinations, delusions, paranoid ideas", Source.wa)
    if "distress" in mh or "agitation" in mh:
        add(3, "Very distressed or agitated", Source.wa)
    if "wont_wait" in mh:
        add(3, "Not likely to wait for treatment", Source.wa)
    if "crisis" in mh:
        add(3, "Situational crisis", Source.wa)
    if ("anxiety" in mh or "low_mood" in mh) and "suicidal" not in mh:
        add(4, "Anxiety or depression without suicidal ideation", Source.wa)
    if "medication" in mh:
        add(5, "Request for medication, no acute distress", Source.wa)

    return sorted(hits, key=lambda h: (h.ats, h.text))


def suggestion(hits: list[RuleHit]) -> Optional[int]:
    """The most urgent feature decides (ACEM G24, section 6.2)."""
    return min((h.ats for h in hits), default=None)


def is_mental_health(f: IntakeForm) -> bool:
    return bool(f.mh) or (f.complaintKey or "") in _MH_KEYS


def safety_actions(ats: int, f: IntakeForm) -> list[str]:
    """Actions the WA procedures already require after a category is allocated."""
    out: list[str] = []
    mh = is_mental_health(f)
    if mh:
        if "suicidal" in f.mh or "self_harm_act" in f.mh:
            out.append("Keep in line of sight while waiting")
        if ats in (1, 2):
            out.append("Alert the mental health team now; a staff member stays with the patient")
        elif ats == 3:
            out.append("Do not leave in the waiting room without a support person; alert the mental health team")
        elif ats == 4:
            out.append("Regular observation while waiting; discuss with the mental health team")
        else:
            out.append("Routine waiting-room checks")
        out.append("If under Mental Health Act forms or in police custody, consider escalation")
    if ats <= 2 and not mh:
        out.append("Notify the medical officer now")
    if (f.age or 0) >= 65 and f.complaintKey in ("fall", "confusion"):
        out.append("Falls and delirium screen; check for a carer or aged-care contact")
    out.append("Offer an Aboriginal Liaison Officer if the patient identifies as Aboriginal")
    return out


def stream(ats: int, f: IntakeForm) -> str:
    if is_mental_health(f):
        return "Mental health team review" if ats <= 3 else "Mental health liaison, then main ED"
    if ats in (1, 2):
        return "Resuscitation or acute area"
    if ats == 3:
        return "Main ED"
    if ats == 4:
        return "Fast track" if f.complaintKey in ("limb", "laceration") else "Main ED"
    return "Fast track, or redirect to an urgent care clinic"
