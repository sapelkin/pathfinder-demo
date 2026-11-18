"""What the nurse has said so far, as structured fields, and the voice commands in it.

The form is rebuilt from the whole transcript on every update, so corrections later in the sentence win. The text
is lowercased first, so the patterns match case-sensitively on lowercase text.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple, Optional

from .domain import ArrivalMode, Vitals


@dataclass
class IntakeForm:
    name: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    arrivalMode: Optional[ArrivalMode] = None
    complaintKey: Optional[str] = None
    complaint: Optional[str] = None
    duration: Optional[str] = None
    redFlags: set[str] = field(default_factory=set)
    mh: set[str] = field(default_factory=set)
    vitals: Vitals = field(default_factory=Vitals)

    @property
    def is_empty(self) -> bool:
        return self.complaintKey is None and self.age is None and self.vitals.is_empty and not self.mh

    def to_dict(self) -> dict:
        return {
            "name": self.name, "age": self.age, "sex": self.sex,
            "arrivalMode": self.arrivalMode.value if self.arrivalMode else None,
            "complaintKey": self.complaintKey, "complaint": self.complaint, "duration": self.duration,
            "redFlags": sorted(self.redFlags), "mh": sorted(self.mh), "vitals": self.vitals.to_dict(),
            "redFlagLabels": [label_for_flag(k) for k in sorted(self.redFlags)],
            "mhLabels": [label_for_flag(k) for k in sorted(self.mh)],
        }


class CommandKind(str, Enum):
    confirm = "confirm"
    send = "send"
    finish = "finish"
    fromMonitor = "fromMonitor"
    redirect = "redirect"


class VoiceCommand(NamedTuple):
    kind: CommandKind
    value: Optional[int] = None

    @property
    def text(self) -> str:
        """The wire form: "confirm:N" | "send" | "finish" | "fromMonitor" | "redirect"."""
        return f"confirm:{self.value}" if self.kind is CommandKind.confirm else self.kind.value


def confirm(n: int) -> VoiceCommand:
    return VoiceCommand(CommandKind.confirm, n)


SEND = VoiceCommand(CommandKind.send)
FINISH = VoiceCommand(CommandKind.finish)
FROM_MONITOR = VoiceCommand(CommandKind.fromMonitor)
REDIRECT = VoiceCommand(CommandKind.redirect)


class Vocab(NamedTuple):
    key: str
    label: str
    patterns: list[str]


# MARK: Vocabulary

COMPLAINTS: list[Vocab] = [
    Vocab("self_harm", "Self-harm", [r"self harm", r"cut (him|her|my|them)sel", r"overdos", r"took (a lot of |too many )?(pills|tablets)"]),
    Vocab("suicidal", "Suicidal thoughts", [r"suicid", r"wants? to die", r"end (it all|my life|his life|her life|their life)", r"kill (him|her|my|them)sel"]),
    Vocab("psychosis", "Hearing voices, paranoia", [r"hearing voices", r"paranoi", r"hallucinat"]),
    Vocab("agitation", "Agitation", [r"agitated", r"aggressive", r"violent"]),
    Vocab("anxiety", "Anxiety, panic", [r"anxiety", r"anxious", r"panic"]),
    Vocab("low_mood", "Low mood", [r"depress", r"low mood"]),
    Vocab("crisis", "Situational crisis", [r"crisis", r"kicked out", r"homeless"]),
    Vocab("intox", "Intoxication", [r"intoxicated", r"\bdrunk\b", r"\bice\b", r"\bmeth"]),
    Vocab("stroke", "Stroke symptoms", [r"stroke", r"face droop", r"facial droop", r"slurred", r"arm weakness"]),
    Vocab("seizure", "Seizure", [r"seizure", r"\bfitting\b", r"had a fit", r"convuls"]),
    Vocab("chest_pain", "Chest pain", [r"chest pain", r"chest tight", r"pain in (his|her|my|the|their) chest", r"chest discomfort"]),
    Vocab("sob", "Shortness of breath", [r"short of breath", r"shortness of breath", r"breathless", r"can'?t breathe", r"difficulty breathing"]),
    Vocab("head_injury", "Head injury", [r"head injury", r"hit (his|her|my|their) head", r"knocked out"]),
    Vocab("fall", "Fall", [r"\bfell\b", r"\bfall\b", r"had a fall", r"tripped"]),
    Vocab("confusion", "New confusion", [r"confus", r"delirium", r"not making sense"]),
    Vocab("abdo", "Abdominal pain", [r"abdominal", r"stomach pain", r"tummy", r"belly"]),
    Vocab("vomiting", "Vomiting, diarrhoea", [r"vomit", r"diarrh", r"gastro"]),
    Vocab("limb", "Limb injury", [r"ankle", r"wrist", r"sprain", r"twisted", r"fracture", r"broken (arm|leg|wrist|ankle)"]),
    Vocab("laceration", "Laceration", [r"lacerat", r"\bgash", r"cut (his|her|my|their) (hand|finger|arm|leg|head)", r"\bwound"]),
    Vocab("back", "Back pain", [r"back pain", r"sore back"]),
    Vocab("fever", "Fever", [r"fever", r"febrile", r"hot and cold"]),
    Vocab("headache", "Headache", [r"headache", r"migraine"]),
    Vocab("sore_throat", "Sore throat", [r"sore throat", r"tonsil"]),
    Vocab("rash", "Rash", [r"\brash\b", r"hives"]),
    Vocab("dizzy", "Dizziness", [r"dizz", r"vertigo", r"light headed"]),
    Vocab("eye", "Eye problem", [r"\beye\b"]),
    Vocab("allergy", "Allergic reaction", [r"allerg", r"anaphyla", r"swollen (lips|tongue)"]),
    Vocab("script", "Prescription or certificate", [r"prescription", r"\bscript\b", r"certificate"]),
]

RED_FLAGS: list[Vocab] = [
    Vocab("radiating", "Radiating pain", [r"radiat", r"down (his|her|my|the|their) (left )?arm", r"to (the|his|her|my) jaw"]),
    Vocab("sweaty", "Sweaty, clammy", [r"sweat", r"clammy"]),
    Vocab("pleuritic", "Worse on breathing", [r"worse (on|when|with) (breathing|deep breaths)", r"hurts to breathe", r"worse when breathing in"]),
    Vocab("syncope", "Fainted or collapsed", [r"faint", r"passed out", r"collaps"]),
    Vocab("loc", "Loss of consciousness", [r"knocked out", r"loss of consciousness", r"lost consciousness", r"blacked out"]),
    Vocab("lethargic", "Lethargic", [r"letharg", r"drowsy"]),
    Vocab("dehydrated", "Dehydrated", [r"dehydrat", r"can'?t keep (anything|fluids) down"]),
    Vocab("deformity", "Deformity", [r"deform", r"bone sticking out"]),
    Vocab("cardiac_history", "Cardiac history", [r"heart attack before", r"previous heart attack", r"\bstents?\b", r"angina", r"heart history"]),
    Vocab("blood_thinners", "On blood thinners", [r"blood thinner", r"warfarin", r"apixaban", r"rivaroxaban"]),
    Vocab("ongoing", "Still seizing", [r"still (seizing|fitting)", r"ongoing seizure"]),
]

MENTAL_HEALTH: list[Vocab] = [
    Vocab("suicidal", "Suicidal ideation", [r"suicid", r"wants? to die", r"end (it all|my life|his life|her life|their life)"]),
    Vocab("self_harm_act", "Self-harm or attempt", [r"self harm", r"cut (him|her|my|them)sel", r"overdos", r"took (a lot of |too many )?(pills|tablets)"]),
    Vocab("psychosis", "Psychotic symptoms", [r"hearing voices", r"paranoi", r"hallucinat", r"delusion"]),
    Vocab("agitation", "Agitated", [r"agitat", r"restless"]),
    Vocab("aggression", "Aggressive", [r"aggress", r"threaten"]),
    Vocab("violent", "Violent", [r"violent"]),
    Vocab("weapon", "Weapon", [r"weapon", r"\bknife\b"]),
    Vocab("distress", "Very distressed", [r"distress", r"crying", r"tearful"]),
    Vocab("crisis", "Situational crisis", [r"crisis", r"kicked out", r"homeless"]),
    Vocab("anxiety", "Anxiety", [r"anxi", r"panic"]),
    Vocab("low_mood", "Low mood", [r"depress", r"low mood", r"hopeless"]),
    Vocab("wont_wait", "Not likely to wait", [r"won'?t wait", r"will not wait", r"not going to wait", r"wants to leave", r"unwilling to wait", r"not willing to wait"]),
    Vocab("willing_wait", "Willing to wait", [r"willing to wait", r"happy to wait"]),
    Vocab("medication", "Needs usual medication", [r"ran out of (his|her|their|my) (medication|meds)", r"repeat script"]),
]


def label_for_flag(key: str) -> str:
    for v in RED_FLAGS + MENTAL_HEALTH:
        if v.key == key:
            return v.label
    return key


# MARK: Helpers

_cache: dict[str, re.Pattern[str]] = {}


def _re(pattern: str) -> re.Pattern[str]:
    p = _cache.get(pattern)
    if p is None:
        p = _cache[pattern] = re.compile(pattern)
    return p


def matches(t: str, pattern: str) -> bool:
    return _re(pattern).search(t) is not None


def any_match(patterns: list[str], t: str) -> bool:
    return any(matches(t, p) for p in patterns)


def first(t: str, pattern: str) -> Optional[list[str]]:
    """Capture groups of the last match (the latest thing said wins); group 0 is the whole match."""
    last = None
    for m in _re(pattern).finditer(t):
        last = m
    if last is None:
        return None
    return [last.group(g) or "" for g in range(0, (last.re.groups or 0) + 1)]


def _to_int(s: Optional[str]) -> Optional[int]:
    if s is None or not s.isdigit():
        return None
    return int(s)


def _group(groups: Optional[list[str]], i: int) -> Optional[str]:
    if groups is None or i >= len(groups):
        return None
    return groups[i]


def int_in(t: str, patterns: list[str], group: int = 1) -> Optional[int]:
    for p in patterns:
        g = first(t, p)
        if g is None:
            continue
        v = _to_int(_group(g, group))
        if v is not None:
            return v
    return None


def _in(lo: float, hi: float, x: Optional[float]) -> bool:
    return x is not None and lo <= x <= hi


UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def _is_punct(ch: str) -> bool:
    return unicodedata.category(ch).startswith("P")


def _word(tok: str) -> str:
    """Strip punctuation from both ends."""
    a, b = 0, len(tok)
    while a < b and _is_punct(tok[a]):
        a += 1
    while b > a and _is_punct(tok[b - 1]):
        b -= 1
    return tok[a:b]


def _is_number_word(w: str) -> bool:
    return w in UNITS or w in TENS or w == "hundred"


def words_to_numbers(s: str) -> str:
    """"seventy two" → "72", "a hundred and four" → "104", "thirty eight point five" → "38.5"."""
    tokens = s.split(" ")
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        w = _word(tokens[i])
        starts_number = _is_number_word(w) or (w == "a" and i + 1 < n and _word(tokens[i + 1]) == "hundred")
        if not starts_number or w == "hundred":
            out.append(tokens[i])
            i += 1
            continue
        total = 0
        current = 0
        last_token = tokens[i]
        j = i
        while j < n:
            x = _word(tokens[j])
            # Clinical shorthand: "one fifty" is 150, "one forty five" is 145.
            if j == i and x in UNITS and 1 <= UNITS[x] <= 2 and j + 1 < n and _word(tokens[j + 1]) in TENS:
                current = UNITS[x] * 100
                last_token = tokens[j]
                j += 1
                continue
            if x in UNITS:
                current += UNITS[x]
            elif x in TENS:
                current += TENS[x]
            elif x == "hundred":
                current = max(1, current) * 100
            elif x == "a" and j == i:
                current = 0
            elif x == "and" and current >= 100 and j + 1 < n and _is_number_word(_word(tokens[j + 1])):
                pass
            else:
                break
            last_token = tokens[j]
            j += 1
        total += current
        text = str(total)
        if j + 1 < n and _word(tokens[j]) == "point":
            d = UNITS.get(_word(tokens[j + 1]))
            if d is not None and d < 10:
                text += f".{d}"
                last_token = tokens[j + 1]
                j += 2
        trailing = ""
        for ch in reversed(last_token):
            if _is_punct(ch):
                trailing = ch + trailing
            else:
                break
        out.append(text + trailing)
        i = j
    return " ".join(out)


_REPLACEMENTS = [("per cent", "percent"), ("%", " percent"), ("’", "'"), ("-", " "), ("sp o2", "spo2"), ("s p o 2", "spo2")]
_DECIMAL = re.compile(r"(\d) \. (\d)")
_SPACES = re.compile(r"\s+")


def normalise(raw: str) -> str:
    s = raw.lower()
    for a, b in _REPLACEMENTS:
        s = s.replace(a, b)
    s = words_to_numbers(s)
    s = _DECIMAL.sub(r"\1.\2", s)
    return _SPACES.sub(" ", s)


# MARK: Parsing

_AGE_PATTERNS = [r"(\d{1,3}) ?(year|yr)s? ?old", r"aged (\d{1,3})", r"\bage (\d{1,3})", r"(\d{1,3}) ?y ?o\b"]


# "No known allergies" is not an allergic reaction: the negated phrase is dropped before the vocabulary is matched.
_NEGATED_ALLERGIES = re.compile(r"\b(no|nil|not|denies|denied|without|zero)( known| any| drug| food)? allerg[a-z]*")


def parse(raw: str) -> IntakeForm:
    t = _NEGATED_ALLERGIES.sub(" ", normalise(raw))
    f = IntakeForm()
    for c in COMPLAINTS:
        if any_match(c.patterns, t):
            f.complaintKey = c.key
            f.complaint = c.label
            break
    f.redFlags = {v.key for v in RED_FLAGS if any_match(v.patterns, t)}
    f.mh = {v.key for v in MENTAL_HEALTH if any_match(v.patterns, t)}
    if "wont_wait" in f.mh:
        f.mh.discard("willing_wait")

    a = int_in(t, _AGE_PATTERNS)
    if a is not None and 1 <= a <= 110:
        f.age = a
    if first(t, r"\b(woman|female|lady|girl|she)\b") is not None:
        f.sex = "F"
    if first(t, r"\b(man|male|gentleman|guy|boy|he)\b") is not None and f.sex is None:
        f.sex = "M"
    if matches(t, r"ambulance|paramedic"):
        f.arrivalMode = ArrivalMode.ambulance
    elif matches(t, r"\bpolice\b"):
        f.arrivalMode = ArrivalMode.police
    elif matches(t, r"\btaxi\b|\buber\b|ride ?share"):
        f.arrivalMode = ArrivalMode.taxi
    elif matches(t, r"\bbus\b|\btrain\b|public transport"):
        f.arrivalMode = ArrivalMode.publicTransport
    elif matches(t, r"walked in|walk in|walked here|on foot"):
        f.arrivalMode = ArrivalMode.walked
    elif matches(t, r"\bcar\b|drove|driven|got a lift|dropped off"):
        f.arrivalMode = ArrivalMode.car
    d = _group(first(t, r"for (the (last|past) )?((\d+|a|an|few|couple of) (minute|hour|day|week|month)s?)"), 3)
    if d is not None:
        f.duration = d
    else:
        d = _group(first(t, r"since (yesterday|this morning|last night|this afternoon|lunch)"), 0)
        if d is not None:
            f.duration = d
    n = _group(first(t, r"(name is|named|called) ([a-z]+ [a-z]+)"), 2)
    if n is not None:
        f.name = " ".join(p[:1].upper() + p[1:] for p in n.split(" ") if p)

    v = Vitals()
    pulse = int_in(t, [r"(pulse|heart rate|\bhr\b)( is| of| at)? (\d{2,3})"], group=3)
    v.pulse = pulse if _in(20, 250, pulse) else None
    g = first(t, r"(blood pressure|\bbp\b)( is| of| at)? (\d{2,3}) ?(/|over) ?(\d{2,3})")
    if g is not None:
        v.systolic = _to_int(_group(g, 3))
        v.diastolic = _to_int(_group(g, 5))
    else:
        g = first(t, r"(blood pressure|\bbp\b)( is| of| at)? (\d):(\d{2}) over (\d{2,3})")
        if g is not None:
            v.systolic = (_to_int(_group(g, 3)) or 0) * 100 + (_to_int(_group(g, 4)) or 0)
            v.diastolic = _to_int(_group(g, 5))
    if v.systolic is not None and not 50 <= v.systolic <= 260:
        v.systolic = None
    spo2 = int_in(t, [r"(sats|saturations?|spo2|sp o2|oxygen|\bo2\b)( is| of| at)? (\d{2,3})"], group=3)
    v.spo2 = spo2 if _in(50, 100, spo2) else None
    resp = int_in(t, [r"(resp(iratory)? rate|resps|\brr\b|breathing rate)( is| of| at)? (\d{1,2})"], group=4)
    v.resp = resp if _in(4, 60, resp) else None
    g = first(t, r"(temp(erature)?)( is| of| at)? (\d{2}(\.\d)?)")
    if g is not None:
        try:
            x = float(_group(g, 4) or "")
        except ValueError:
            x = None
        if x is not None and 30 <= x <= 43:
            v.temp = x
    gcs = int_in(t, [r"\bgcs( is| of)? (\d{1,2})"], group=2)
    v.gcs = gcs if _in(3, 15, gcs) else None
    pain = int_in(t, [r"pain( score)?( is| of| at)? (\d{1,2}) ?(out of 10|/10)"], group=3)
    if pain is None:
        pain = int_in(t, [r"(\d{1,2}) ?(out of 10|/10) pain"], group=1)
    if pain is None:
        pain = int_in(t, [r"pain( score)?( is| of| at)? (\d{1,2})\b"], group=3)
    v.pain = pain if _in(0, 10, pain) else None
    f.vitals = v
    return f


_CONFIRM = re.compile(r"\b(confirm|triage)( as)?( category| cat)? ([1-5])\b|\bcategory ([1-5])\b")
_SEND = re.compile(r"\bsend (the |a |them the |him the |her the )?(message|text|sms|wait time)\b|\btext (him|her|them|the patient)\b")
_FINISH = re.compile(r"\badd (him |her |them )?to the (waiting room|queue)\b|\bfinish (the )?intake\b|\bsave (the )?(patient|intake)\b")
_MONITOR = re.compile(r"\b(obs|vitals|observations) from (the )?monitor\b")
_REDIRECT = re.compile(r"\bredirect (him |her |them )?to\b")


def commands(raw: str) -> list[VoiceCommand]:
    """Every command in the transcript, in the order spoken. The caller runs only the ones it has not run yet."""
    t = normalise(raw)
    found: list[tuple[int, VoiceCommand]] = []
    for m in _CONFIRM.finditer(t):
        for g in (4, 5):
            if m.group(g) is not None:
                found.append((m.start(), confirm(int(m.group(g)))))
                break
    for m in _SEND.finditer(t):
        found.append((m.start(), SEND))
    for m in _FINISH.finditer(t):
        found.append((m.start(), FINISH))
    for m in _MONITOR.finditer(t):
        found.append((m.start(), FROM_MONITOR))
    for m in _REDIRECT.finditer(t):
        found.append((m.start(), REDIRECT))
    found.sort(key=lambda x: x[0])
    return [c for _, c in found]
