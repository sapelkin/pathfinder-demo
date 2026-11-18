"""Build Pathfinder's seed from published figures and stated assumptions: the public edition.

Run from web/engine:
    python3 tools/build_public_seed.py

No hackathon Data is read. Every figure is either PUBLISHED (a number from a public report, with its source and
period) or ASSUMED (a stated modelling assumption, anchored to a published range where one exists). The script writes
the seed the engine reads (pathfinder_engine/data/pathfinder_seed.json) and docs/PUBLIC_FIGURES.md, the
table of every figure with its status and source, so a reader can check each one.

The demo ED and its patients are fictional. The waiting-room model is calibrated by simulation (tools/waitroom_sim.py)
to the published wait and did-not-wait targets.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

from waitroom_sim import ATS_TARGET_MIN, calibrate

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent
OUT = ENGINE / "pathfinder_engine" / "data" / "pathfinder_seed.json"
DOC = ENGINE.parent.parent / "docs" / "PUBLIC_FIGURES.md"

# ---------------------------------------------------------------------------------------------------- sources

SOURCES = {
    "rogs2026": ("Productivity Commission, Report on Government Services 2026, Part E section 12 Public hospitals",
                 "https://www.pc.gov.au/ongoing/report-on-government-services/health/public-hospitals/"),
    "aihw_ed_2425": ("AIHW, Emergency department care 2024-25 (web report: presentations, waiting times, care provided, time spent)",
                     "https://www.aihw.gov.au/hospitals/topics/emergency-departments"),
    "aihw_glance_2425": ("AIHW, Australia's hospitals at a glance 2024-25",
                         "https://www.aihw.gov.au/hospitals/overview/hospitals-at-a-glance"),
    "aihw_ed_2223": ("AIHW, Emergency department care 2022-23, appendix tables A1 and A4",
                     "https://www.aihw.gov.au/getmedia/77b55e9d-a340-4d47-b1fc-001efba9bf17/emergency-department-care-2022-23-appendix.pdf"),
    "aihw_mh_ed_2425": ("AIHW, Mental health services: state and territory emergency department data 2024-25",
                        "https://www.aihw.gov.au/mental-health/topic-areas/hospital-based-services/emergency-departments/state-and-territory-data"),
    "oag_ed_2024": ("WA Auditor General, Quality and Utilisation of Emergency Department Data, Report 4 2024-25",
                    "https://audit.wa.gov.au/reports-and-publications/reports/quality-and-utilisation-of-emergency-department-data/"),
    "dinh2025": ("Dinh et al., Characteristics and outcomes of ED patients who did not wait: a state-wide data linkage analysis "
                 "from NSW (Emergency Medicine Australasia, 2025; episodes 2021-2022)",
                 "https://onlinelibrary.wiley.com/doi/abs/10.1111/1742-6723.70095"),
    "older_28d": ("Australian studies of 28-day ED re-presentation in older adults: 7.9% of visits (aged 60+, 2020-23) and "
                  "18.0% of visits in an inner-city ED",
                  "https://pubmed.ncbi.nlm.nih.gov/40910692/ and https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2222161/"),
    "mh_incomplete_2025": ("Who has incomplete ED care among mental health patients in Australia? (Australasian Emergency Care, 2025): "
                           "leaving at own risk carries a multi-fold risk of 7- and 28-day re-presentation",
                           "https://pubmed.ncbi.nlm.nih.gov/40541514/"),
    "wa_live": ("WA Health, Emergency department live activity (public page)",
                "https://www.health.wa.gov.au/reports-and-publications/emergency-department-activity/data?report=ed_activity_now"),
}

# A figure: value, PUBLISHED or ASSUMED, period, source key, note. The table in PUBLIC_FIGURES.md is built from these.
FIGURES: list[dict] = []


def published(key: str, value, period: str, source: str, note: str = ""):
    FIGURES.append(dict(key=key, value=value, status="published", period=period, source=source, note=note))
    return value


def assumed(key: str, value, note: str, anchor: str = ""):
    FIGURES.append(dict(key=key, value=value, status="assumed", period="", source=anchor, note=note))
    return value


# ---------------------------------------------------------------------------------------------------- published

WA_PRESENTATIONS = published("WA public ED presentations", 1_027_016, "2024-25", "rogs2026", "24 public EDs reporting nationally")
WA_WITHIN_4H = published("WA presentations completed within 4 hours", 0.539, "2024-25", "rogs2026")
WA_TRIAGE = published("WA presentations by triage category 1 to 5", [0.010, 0.162, 0.379, 0.393, 0.056], "2022-23", "aihw_ed_2223")
WA_ADMITTED = published("WA share admitted from the ED", 0.24, "2024-25", "aihw_ed_2425", "the lowest of the states; Australia 30%")
NAT_MEDIAN_WAIT = published("Australia median waiting time to treatment", 18, "2024-25", "aihw_ed_2425", "minutes; 90th percentile 1 h 58 min")
NAT_SEEN_ON_TIME = published("Australia seen on time", 0.67, "2024-25", "aihw_ed_2425")
NAT_DNW = published("Australia did not wait", 0.046, "2023-24", "rogs2026", "up from 3.6% the year before")
NAT_LAOR = published("Australia left at own risk", 0.039, "2023-24", "rogs2026", "up from 1.2%; AIHW 2024-25 reports 4.1% left at own risk or did not wait")
WA_DNW_LAOR_2021 = published("WA did not wait or left at own risk", 0.05, "2020-21", "oag_ed_2024", "a 39% rise since 2016-17")
NAT_LOS = published("Australia time in the ED, median", {"all": 3.80, "admitted": 6.22, "not_admitted": 3.17}, "2024-25", "aihw_ed_2425",
                    "hours; 90th percentiles 11 h 16, 18 h 57 and 7 h 44")
NAT_AMBULANCE = published("Australia arrivals by ambulance or air", 0.27, "2024-25", "aihw_glance_2425")
NAT_DAYTIME = published("Australia presentations between 8 am and 8 pm", 0.70, "2024-25", "aihw_glance_2425", "busiest days Sunday, Monday, Tuesday")
NAT_P65_SHARE = published("Australia share of presentations by people aged 65 and over", 0.24, "2024-25", "aihw_ed_2425",
                          "52% of them admitted, against 30% of all presentations")
WA_MH = published("WA mental health-related ED presentations", 36_799, "2024-25", "aihw_mh_ed_2425",
                  "122 per 10,000 people; 75% triaged urgent or higher; median wait 45 min; 41% seen on time; median stay 5 h 47")
WA_MH_DX = published("WA mental health presentations by principal diagnosis", {"substance_use": 0.34, "psychotic": 0.14, "anxiety_stress": 0.23},
                     "2024-25", "aihw_mh_ed_2425")
WA_FREQUENT = published("WA frequent users", {"people": 0.05, "attendances": 0.20}, "2017-18", "oag_ed_2024",
                        "5% of people account for 20% of attendances (Sustainable Health Review)")
DNW_RETURN_7D = published("Return to an ED within 7 days after did not wait", 0.148, "2021-22", "dinh2025", "NSW; 23% of them to a different hospital")
OLDER_RETURN_28D = published("Older adults back in an ED within 28 days", {"low": 0.079, "high": 0.18}, "2014-2023", "older_28d",
                             "the range across Australian studies")

# ---------------------------------------------------------------------------------------------------- assumptions

DEMO_ANNUAL = assumed("Demo ED presentations a year", 70_000,
                      "a mid-sized metropolitan ED, about one fifteenth of WA's presentations", "rogs2026")
DAY_FACTOR = assumed("Day-of-week factors, Monday to Sunday", [1.07, 1.02, 0.98, 0.97, 0.96, 0.97, 1.03],
                     "Sunday, Monday and Tuesday busiest, as published; the spread is assumed", "aihw_glance_2425")
HOUR_PROFILE = assumed("Hour-of-day profile, midnight to 11 pm",
                       [0.45, 0.35, 0.28, 0.24, 0.22, 0.25, 0.35, 0.60, 0.95, 1.30, 1.55, 1.60,
                        1.50, 1.45, 1.40, 1.35, 1.35, 1.40, 1.45, 1.35, 1.20, 1.00, 0.80, 0.60],
                       "quietest at 4 am, a late-morning peak and an evening shoulder; tuned so that 70% of arrivals fall "
                       "between 8 am and 8 pm", "aihw_glance_2425")
MH_SHARE = assumed("Mental health share of the demo ED's presentations", round(WA_MH / WA_PRESENTATIONS, 4),
                   "the WA share, 3.6%", "aihw_mh_ed_2425")
P65_SHARE = assumed("Aged 65+ share of the demo ED's presentations", 0.22, "between the national 24% and WA's younger age structure", "aihw_ed_2425")
MH_TRIAGE = assumed("Mental health triage distribution", [0.01, 0.20, 0.54, 0.22, 0.03], "75% urgent or higher, as published for WA", "aihw_mh_ed_2425")
P65_TRIAGE = assumed("Aged 65+ triage distribution", [0.02, 0.27, 0.46, 0.22, 0.03], "older people are triaged more urgently; the split is assumed", "aihw_ed_2425")
DNW_BY_ATS = assumed("Did not wait by triage category", [0.0, 0.010, 0.040, 0.060, 0.080],
                     "allocated so the whole-ED rate is 4.6%, the national 2023-24 figure, with the gradient by urgency seen in the NSW linkage study",
                     "rogs2026, dinh2025")
LAOR_BY_COHORT = assumed("Left at own risk by cohort", {"other": 0.006, "mh": 0.030, "p65": 0.004},
                         "mental health presentations leave at own risk several times more often", "mh_incomplete_2025")
REFERRED_BY_ATS = assumed("Redirected at triage by category", [0.0, 0.0, 0.004, 0.015, 0.035], "small, and only for the less urgent")
LEAVE_MINUTES = assumed("Minutes in the department before leaving without being seen", {"p25": 65, "p50": 115, "p75": 185, "p90": 270},
                        "a median of about two hours")
WAIT_MEDIAN_ALL = assumed("Median wait to treatment, whole ED, minutes", 35,
                          "the national median is 18 minutes; WA runs about twice as long where it is published (mental health 45 against "
                          "21 nationally; the lowest four-hour performance of the states), so the target is about twice the national median",
                          "aihw_ed_2425, aihw_mh_ed_2425, rogs2026")
WAIT_MEDIAN_BY_ATS = assumed("Median wait by triage category, minutes", [0, 15, 38, 44, 46],
                             "the same doubling applied by category, with the more urgent category always seen sooner, which the app's "
                             "expected-time logic assumes (nationally a fast-track stream sees categories 4 and 5 a little sooner than 3; "
                             "the demo ED has no fast track)", "aihw_ed_2425")
WAIT_P90_BY_ATS = assumed("90th percentile wait by triage category, minutes", [2, 70, 180, 200, 210], "the national 90th percentile is 118 minutes overall")
SEEN_ON_TIME_BY_ATS = assumed("Seen on time by triage category", [1.0, 0.62, 0.50, 0.72, 0.92], "national 67% overall; category 1 always seen on time")
ADMIT_BY_COHORT_ATS = assumed("Admitted by cohort and triage category",
                              {"other": [0.75, 0.42, 0.25, 0.10, 0.04], "mh": [0.70, 0.45, 0.33, 0.18, 0.08], "p65": [0.85, 0.65, 0.50, 0.30, 0.12]},
                              "chosen so the ED admits 24% overall, WA's published share, and about half of people aged 65+", "aihw_ed_2425")
CARE_HOURS = assumed("Hours in care after being seen, by outcome (median, log-sd)",
                     {"B": (5.6, 0.60), "D": (2.6, 0.70), "R3": (2.0, 0.70)},
                     "the published medians of time in the ED, 6 h 13 admitted and 3 h 10 not admitted, less a typical wait", "aihw_ed_2425")
FLAGS = assumed("Flags by cohort: self-harm, drugs or alcohol, police, ambulance",
                {"other": (0.004, 0.030, 0.006, 0.20), "mh": (0.12, 0.34, 0.06, 0.36), "p65": (0.002, 0.010, 0.002, 0.46)},
                "substance use is 34% of WA mental health presentations, as published; ambulance 27% overall nationally, higher with age",
                "aihw_mh_ed_2425, aihw_glance_2425")
ARRIVAL = assumed("Arrival mode by cohort: private, public transport, ambulance, police, taxi",
                  {"other": (0.72, 0.04, 0.20, 0.006, 0.02), "mh": (0.48, 0.05, 0.36, 0.06, 0.03), "p65": (0.48, 0.02, 0.46, 0.002, 0.03)},
                  "the ambulance shares above; the rest is private transport", "aihw_glance_2425")
AGE_BANDS = assumed("Age bands by cohort",
                    {"other": {"18-24": 0.20, "25-44": 0.46, "45-64": 0.34},
                     "mh": {"18-24": 0.22, "25-44": 0.46, "45-64": 0.24, "65-74": 0.05, "75-84": 0.02, "85+": 0.01},
                     "p65": {"65-74": 0.45, "75-84": 0.37, "85+": 0.18}},
                    "adults only; older-old bands follow the population")
PRIOR_VISITS = assumed("Earlier ED visits in the past year, by cohort: 0, 1, 2-3, 4+",
                       {"other": (0.62, 0.21, 0.12, 0.05), "mh": (0.42, 0.22, 0.20, 0.16), "p65": (0.52, 0.24, 0.17, 0.07)},
                       "5% of people make 20% of attendances, as published for WA; the bands are assumed", "oag_ed_2024")
DAYS_SINCE = assumed("Days since the last visit, by cohort (quartiles)",
                     {"other": (30, 95, 200), "mh": (14, 45, 130), "p65": (25, 80, 180)}, "shorter gaps for mental health")
RECURRENCE = assumed("People with two or more visits a year, and their share of visits",
                     {"other": (0.22, 0.48), "mh": (0.45, 0.78), "p65": (0.30, 0.58)}, "from the prior-visit bands above")
RETURN_BASE = assumed("Back in an ED within 28 days, base rates by cohort and outcome (D went home, R left or redirected)",
                      {("other", "D"): 0.10, ("other", "R"): 0.24, ("mh", "D"): 0.20, ("mh", "R"): 0.32, ("p65", "D"): 0.15, ("p65", "R"): 0.28},
                      "older adults 8 to 18% in Australian studies; 14.8% are back within 7 days after not waiting (NSW); mental health "
                      "higher and higher again after leaving at own risk", "older_28d, dinh2025, mh_incomplete_2025")
RETURN_7D_SHARE = assumed("Share of 28-day returns that happen within 7 days", {"D": 0.45, "R": 0.60}, "returns after leaving come sooner", "dinh2025")
PRIOR_MULT = assumed("Return-risk multiplier by earlier visits: 0, 1, 2-3, 4+", (0.70, 1.00, 1.40, 2.10), "frequent users return most; capped at 60%")
PRIORITY_TARGETS = assumed("Call-order targets by category, minutes", [1, 3, 30, 40, 46],
                           "the model calls whoever has waited the largest share of their target; a gentler gradient than the official "
                           "0/10/30/60/120 so that categories 4 and 5 are not left for hours, but the more urgent is always seen sooner")
PATIENCE_SAMPLE_N = 40_000   # notional weights for averaging the prior-visit bands; never published as counts


# ---------------------------------------------------------------------------------------------------- derivations

def arrival_shape() -> list[float]:
    prof = HOUR_PROFILE
    shape = [DAY_FACTOR[d] * prof[h] for d in range(7) for h in range(24)]
    s = sum(shape)
    shape = [x / s for x in shape]
    day = sum(shape[d * 24 + h] for d in range(7) for h in range(8, 20))
    assert 0.68 <= day <= 0.73, f"daytime share {day:.3f} is off the published 70%"
    return shape


def cohort_by_ats() -> list[dict]:
    rows = []
    for i in range(5):
        mh = MH_SHARE * MH_TRIAGE[i] / WA_TRIAGE[i]
        p65 = P65_SHARE * P65_TRIAGE[i] / WA_TRIAGE[i]
        rows.append({"ats": i + 1, "n": int(DEMO_ANNUAL * WA_TRIAGE[i]), "mh": round(mh, 4), "p65": round(p65, 4)})
    return rows


def returns_tables() -> tuple[list[dict], list[dict]]:
    bands = ["0", "1", "2-3", "4+"]
    rows, by_cohort = [], []
    for co in ("other", "mh", "p65"):
        for o in ("D", "R"):
            base = RETURN_BASE[(co, o)]
            n_co = int(PATIENCE_SAMPLE_N * {"other": 0.74, "mh": 0.036, "p65": 0.22}[co] * (0.85 if o == "D" else 0.12))
            r28_all, r7_all, n_all = 0.0, 0.0, 0
            for b, share, mult in zip(bands, PRIOR_VISITS[co], PRIOR_MULT):
                r28 = min(0.60, base * mult)
                r7 = round(r28 * RETURN_7D_SHARE[o], 3)
                n = max(30, int(n_co * share))
                rows.append({"cohort": co, "outcome": o, "prior": b, "n": None, "ret7": r7, "ret28": round(r28, 3)})
                r28_all += r28 * n
                r7_all += r7 * n
                n_all += n
            by_cohort.append({"cohort": co, "outcome": o, "n": None, "ret7": round(r7_all / n_all, 3), "ret28": round(r28_all / n_all, 3)})
    return rows, by_cohort


def build_aggregates() -> dict:
    annual = DEMO_ANNUAL
    dnw_rate = round(sum(m * r for m, r in zip(WA_TRIAGE, DNW_BY_ATS)), 4)
    agg: dict = {
        "metro_presentations": WA_PRESENTATIONS,
        "triage_mix": WA_TRIAGE,
        "cohort_by_ats": cohort_by_ats(),
        "referred_at_triage_by_ats": REFERRED_BY_ATS,
        "dnw_by_ats": [{"ats": i + 1, "n": int(annual * WA_TRIAGE[i]), "dnw": int(annual * WA_TRIAGE[i] * DNW_BY_ATS[i]), "rate": DNW_BY_ATS[i]}
                       for i in range(5)],
        "dnw_rate": dnw_rate,
        "dnw_minutes_before_leaving": {**LEAVE_MINUTES, "n": int(annual * dnw_rate)},
        "wait_by_ats": [{"ats": i + 1, "n": int(annual * WA_TRIAGE[i]), "median_min": WAIT_MEDIAN_BY_ATS[i], "p90_min": WAIT_P90_BY_ATS[i],
                         "seen_on_time": SEEN_ON_TIME_BY_ATS[i]} for i in range(5)],
        "wait_all": {"n": annual, "median_min": WAIT_MEDIAN_ALL, "seen_on_time": round(sum(m * s for m, s in zip(WA_TRIAGE, SEEN_ON_TIME_BY_ATS)), 4)},
        "admit_by_cohort_ats": ADMIT_BY_COHORT_ATS,
        "left_at_own_risk_by_cohort": LAOR_BY_COHORT,
        "care_hours": {o: {"n": int(annual * {"B": 0.24, "D": 0.66, "R3": 0.10}[o]), "median": m, "log_sd": s} for o, (m, s) in CARE_HOURS.items()},
        "flags_by_cohort": {co: {"n": int(annual * sh), "self_harm": f[0], "drugs_alcohol": f[1], "police": f[2], "ambulance": f[3]}
                            for co, sh, f in (("other", 0.74, FLAGS["other"]), ("mh", 0.036, FLAGS["mh"]), ("p65", 0.22, FLAGS["p65"]))},
        "arrival_mode_by_cohort": {co: {"n": int(annual * sh), "private": a[0], "public": a[1], "ambulance": a[2], "police": a[3], "taxi": a[4]}
                                   for co, sh, a in (("other", 0.74, ARRIVAL["other"]), ("mh", 0.036, ARRIVAL["mh"]), ("p65", 0.22, ARRIVAL["p65"]))},
        "age_bands_by_cohort": {co: {b: int(annual * sh * v) for b, v in bands.items()}
                                for co, sh, bands in (("other", 0.74, AGE_BANDS["other"]), ("mh", 0.036, AGE_BANDS["mh"]), ("p65", 0.22, AGE_BANDS["p65"]))},
        "prior_visits_by_cohort": {co: {b: int(annual * sh * v) for b, v in zip(("0", "1", "2-3", "4+"), PRIOR_VISITS[co])}
                                   for co, sh in (("other", 0.74), ("mh", 0.036), ("p65", 0.22))},
        "days_since_last_visit_by_cohort": {co: {"p25": q[0], "p50": q[1], "p75": q[2], "n": int(annual * sh * 0.4)}
                                            for co, sh, q in (("other", 0.74, DAYS_SINCE["other"]), ("mh", 0.036, DAYS_SINCE["mh"]), ("p65", 0.22, DAYS_SINCE["p65"]))},
        "recurrence_by_cohort": {co: {"persons": int(annual * sh * 0.7), "persons_2plus": r[0], "visits_by_2plus": r[1]}
                                 for co, sh, r in (("other", 0.74, RECURRENCE["other"]), ("mh", 0.036, RECURRENCE["mh"]), ("p65", 0.22, RECURRENCE["p65"]))},
    }
    agg["returns"], agg["returns_by_cohort"] = returns_tables()
    return agg


def statewide_kpis(agg: dict) -> dict:
    """The baselines the Impact screen shows: WA figures where published, the demo ED's assumptions otherwise."""
    dnw_rate = agg["dnw_rate"]
    ats123 = sum(WA_TRIAGE[i] * DNW_BY_ATS[i] for i in range(3)) / dnw_rate
    return {
        "presentations": WA_PRESENTATIONS,
        "seen_on_time": agg["wait_all"]["seen_on_time"],
        "median_wait_min": agg["wait_all"]["median_min"],
        "mh_seen_on_time": 0.41, "mh_median_wait_min": 45,          # published for WA, 2024-25
        "p65_seen_on_time": 0.60, "p65_median_wait_min": 30,        # assumed
        "dnw_n": int(WA_PRESENTATIONS * dnw_rate), "dnw_rate": dnw_rate,
        "left_or_redirected_rate": round(dnw_rate + 0.008 + sum(m * r for m, r in zip(WA_TRIAGE, REFERRED_BY_ATS)), 4),
        "dnw_ats123_share": round(ats123, 4),
        "dnw_median_leave_min": LEAVE_MINUTES["p50"],
        "returns": agg["returns_by_cohort"],
    }


def write_doc(seed: dict) -> None:
    lines = ["# Where the public edition's figures come from", "",
             "Pathfinder's public edition reads no hackathon Data. Every figure in its seed is one of two kinds:", "",
             "- **published**: a number from a public report, with its period and source;",
             "- **assumed**: a modelling assumption we state here, anchored to a published range where one exists.", "",
             "The assumed values were chosen by the authors from the published anchors in this table and general knowledge of "
             "how emergency departments run. None was taken from the hackathon's dataset or any other non-public source; "
             "the script reads no data files, and every value is written in it.", "",
             "The demo ED and its patients are fictional. The waiting-room model is calibrated by simulation to the published "
             "wait and did-not-wait targets (`web/engine/tools/waitroom_sim.py`); the calibration it reached is at the end.", "",
             "| Figure | Value | Status | Period | Source | Note |", "|---|---|---|---|---|---|"]
    for f in FIGURES:
        v = f["value"]
        if isinstance(v, (dict, list, tuple)):
            v = json.dumps(v if not isinstance(v, dict) or all(isinstance(k, str) for k in v) else {" ".join(k): x for k, x in v.items()})
        lines.append(f"| {f['key']} | `{v}` | {f['status']} | {f['period']} | {f['source']} | {f['note']} |")
    lines += ["", "## Sources", ""]
    for k, (name, url) in SOURCES.items():
        lines.append(f"- `{k}`: {name}. {url}")
    cal = seed["sim"]["calibration"]
    lines += ["", "## Calibration reached", "",
              f"Median wait {cal['median_wait_min']} min against a target of {cal['targets']['median_wait_min']}; did not wait "
              f"{cal['dnw_rate'] * 100:.1f}% against {cal['targets']['dnw_rate'] * 100:.1f}%; median time before leaving "
              f"{cal['dnw_median_leave_min']} min against {cal['targets']['dnw_median_leave_min']}. Built {seed['built_at']}.", ""]
    DOC.write_text("\n".join(lines))


def main() -> None:
    agg = build_aggregates()
    shape = arrival_shape()
    weekly = DEMO_ANNUAL / 52.143
    # A wider grid than the Data edition's, and gentler call-order targets so the less urgent are not left for hours.
    params, report = calibrate(agg, weekly, shape, priority_targets=PRIORITY_TARGETS, sigmas=(0.35, 0.5, 0.65, 0.8),
                               slacks=(0.96, 1.00, 1.04, 1.08, 1.12, 1.16), lags=(0, 1, 2), iters=6)
    seed = {
        "version": 2,
        "built_at": dt.datetime.now().isoformat(timespec="seconds"),
        "note": ("Public edition: published WA and national figures plus stated assumptions (see PUBLIC_FIGURES.md). "
                 "No hackathon Data. The demo ED and its patients are fictional."),
        "demo_ed": {"name": "Pathfinder Demo ED", "annual_presentations": DEMO_ANNUAL, "weekly_presentations": round(weekly, 1),
                    "basis": "A mid-sized metropolitan ED, assumed 70,000 presentations a year; WA's 24 public EDs saw 1.03 million in 2024-25"},
        "arrival_shape": [round(x, 7) for x in shape],
        "aggregates": agg,
        "kpi_statewide": statewide_kpis(agg),
        "sim": {**params, "seed": 62, "calibration": report,
                "method": ("Minute steps; Poisson arrivals from the weekly template; capacity follows demand with a lag; "
                           "ATS 1 seen at once, others called by the largest share of their priority target already waited; "
                           "lognormal patience per category, calibrated to the did-not-wait rate by category.")},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(seed, indent=1))
    write_doc(seed)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB) and {DOC.name}")
    print("demo ED:", seed["demo_ed"])
    print("params:", params)
    print("calibration:", json.dumps({k: v for k, v in report.items() if k != 'targets'}), "\ntargets:", report["targets"])


if __name__ == "__main__":
    main()
