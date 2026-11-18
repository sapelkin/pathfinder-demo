# Where the public edition's figures come from

Pathfinder's public edition reads no hackathon Data. Every figure in its seed is one of two kinds:

- **published**: a number from a public report, with its period and source;
- **assumed**: a modelling assumption we state here, anchored to a published range where one exists.

The assumed values were chosen by the authors from the published anchors in this table and general knowledge of how emergency departments run. None was taken from the hackathon's dataset or any other non-public source; the script reads no data files, and every value is written in it.

The demo ED and its patients are fictional. The waiting-room model is calibrated by simulation to the published wait and did-not-wait targets (`web/engine/tools/waitroom_sim.py`); the calibration it reached is at the end.

| Figure | Value | Status | Period | Source | Note |
|---|---|---|---|---|---|
| WA public ED presentations | `1027016` | published | 2024-25 | rogs2026 | 24 public EDs reporting nationally |
| WA presentations completed within 4 hours | `0.539` | published | 2024-25 | rogs2026 |  |
| WA presentations by triage category 1 to 5 | `[0.01, 0.162, 0.379, 0.393, 0.056]` | published | 2022-23 | aihw_ed_2223 |  |
| WA share admitted from the ED | `0.24` | published | 2024-25 | aihw_ed_2425 | the lowest of the states; Australia 30% |
| Australia median waiting time to treatment | `18` | published | 2024-25 | aihw_ed_2425 | minutes; 90th percentile 1 h 58 min |
| Australia seen on time | `0.67` | published | 2024-25 | aihw_ed_2425 |  |
| Australia did not wait | `0.046` | published | 2023-24 | rogs2026 | up from 3.6% the year before |
| Australia left at own risk | `0.039` | published | 2023-24 | rogs2026 | up from 1.2%; AIHW 2024-25 reports 4.1% left at own risk or did not wait |
| WA did not wait or left at own risk | `0.05` | published | 2020-21 | oag_ed_2024 | a 39% rise since 2016-17 |
| Australia time in the ED, median | `{"all": 3.8, "admitted": 6.22, "not_admitted": 3.17}` | published | 2024-25 | aihw_ed_2425 | hours; 90th percentiles 11 h 16, 18 h 57 and 7 h 44 |
| Australia arrivals by ambulance or air | `0.27` | published | 2024-25 | aihw_glance_2425 |  |
| Australia presentations between 8 am and 8 pm | `0.7` | published | 2024-25 | aihw_glance_2425 | busiest days Sunday, Monday, Tuesday |
| Australia share of presentations by people aged 65 and over | `0.24` | published | 2024-25 | aihw_ed_2425 | 52% of them admitted, against 30% of all presentations |
| WA mental health-related ED presentations | `36799` | published | 2024-25 | aihw_mh_ed_2425 | 122 per 10,000 people; 75% triaged urgent or higher; median wait 45 min; 41% seen on time; median stay 5 h 47 |
| WA mental health presentations by principal diagnosis | `{"substance_use": 0.34, "psychotic": 0.14, "anxiety_stress": 0.23}` | published | 2024-25 | aihw_mh_ed_2425 |  |
| WA frequent users | `{"people": 0.05, "attendances": 0.2}` | published | 2017-18 | oag_ed_2024 | 5% of people account for 20% of attendances (Sustainable Health Review) |
| Return to an ED within 7 days after did not wait | `0.148` | published | 2021-22 | dinh2025 | NSW; 23% of them to a different hospital |
| Older adults back in an ED within 28 days | `{"low": 0.079, "high": 0.18}` | published | 2014-2023 | older_28d | the range across Australian studies |
| Demo ED presentations a year | `70000` | assumed |  | rogs2026 | a mid-sized metropolitan ED, about one fifteenth of WA's presentations |
| Day-of-week factors, Monday to Sunday | `[1.07, 1.02, 0.98, 0.97, 0.96, 0.97, 1.03]` | assumed |  | aihw_glance_2425 | Sunday, Monday and Tuesday busiest, as published; the spread is assumed |
| Hour-of-day profile, midnight to 11 pm | `[0.45, 0.35, 0.28, 0.24, 0.22, 0.25, 0.35, 0.6, 0.95, 1.3, 1.55, 1.6, 1.5, 1.45, 1.4, 1.35, 1.35, 1.4, 1.45, 1.35, 1.2, 1.0, 0.8, 0.6]` | assumed |  | aihw_glance_2425 | quietest at 4 am, a late-morning peak and an evening shoulder; tuned so that 70% of arrivals fall between 8 am and 8 pm |
| Mental health share of the demo ED's presentations | `0.0358` | assumed |  | aihw_mh_ed_2425 | the WA share, 3.6% |
| Aged 65+ share of the demo ED's presentations | `0.22` | assumed |  | aihw_ed_2425 | between the national 24% and WA's younger age structure |
| Mental health triage distribution | `[0.01, 0.2, 0.54, 0.22, 0.03]` | assumed |  | aihw_mh_ed_2425 | 75% urgent or higher, as published for WA |
| Aged 65+ triage distribution | `[0.02, 0.27, 0.46, 0.22, 0.03]` | assumed |  | aihw_ed_2425 | older people are triaged more urgently; the split is assumed |
| Did not wait by triage category | `[0.0, 0.01, 0.04, 0.06, 0.08]` | assumed |  | rogs2026, dinh2025 | allocated so the whole-ED rate is 4.6%, the national 2023-24 figure, with the gradient by urgency seen in the NSW linkage study |
| Left at own risk by cohort | `{"other": 0.006, "mh": 0.03, "p65": 0.004}` | assumed |  | mh_incomplete_2025 | mental health presentations leave at own risk several times more often |
| Redirected at triage by category | `[0.0, 0.0, 0.004, 0.015, 0.035]` | assumed |  |  | small, and only for the less urgent |
| Minutes in the department before leaving without being seen | `{"p25": 65, "p50": 115, "p75": 185, "p90": 270}` | assumed |  |  | a median of about two hours |
| Median wait to treatment, whole ED, minutes | `35` | assumed |  | aihw_ed_2425, aihw_mh_ed_2425, rogs2026 | the national median is 18 minutes; WA runs about twice as long where it is published (mental health 45 against 21 nationally; the lowest four-hour performance of the states), so the target is about twice the national median |
| Median wait by triage category, minutes | `[0, 15, 38, 44, 46]` | assumed |  | aihw_ed_2425 | the same doubling applied by category, with the more urgent category always seen sooner, which the app's expected-time logic assumes (nationally a fast-track stream sees categories 4 and 5 a little sooner than 3; the demo ED has no fast track) |
| 90th percentile wait by triage category, minutes | `[2, 70, 180, 200, 210]` | assumed |  |  | the national 90th percentile is 118 minutes overall |
| Seen on time by triage category | `[1.0, 0.62, 0.5, 0.72, 0.92]` | assumed |  |  | national 67% overall; category 1 always seen on time |
| Admitted by cohort and triage category | `{"other": [0.75, 0.42, 0.25, 0.1, 0.04], "mh": [0.7, 0.45, 0.33, 0.18, 0.08], "p65": [0.85, 0.65, 0.5, 0.3, 0.12]}` | assumed |  | aihw_ed_2425 | chosen so the ED admits 24% overall, WA's published share, and about half of people aged 65+ |
| Hours in care after being seen, by outcome (median, log-sd) | `{"B": [5.6, 0.6], "D": [2.6, 0.7], "R3": [2.0, 0.7]}` | assumed |  | aihw_ed_2425 | the published medians of time in the ED, 6 h 13 admitted and 3 h 10 not admitted, less a typical wait |
| Flags by cohort: self-harm, drugs or alcohol, police, ambulance | `{"other": [0.004, 0.03, 0.006, 0.2], "mh": [0.12, 0.34, 0.06, 0.36], "p65": [0.002, 0.01, 0.002, 0.46]}` | assumed |  | aihw_mh_ed_2425, aihw_glance_2425 | substance use is 34% of WA mental health presentations, as published; ambulance 27% overall nationally, higher with age |
| Arrival mode by cohort: private, public transport, ambulance, police, taxi | `{"other": [0.72, 0.04, 0.2, 0.006, 0.02], "mh": [0.48, 0.05, 0.36, 0.06, 0.03], "p65": [0.48, 0.02, 0.46, 0.002, 0.03]}` | assumed |  | aihw_glance_2425 | the ambulance shares above; the rest is private transport |
| Age bands by cohort | `{"other": {"18-24": 0.2, "25-44": 0.46, "45-64": 0.34}, "mh": {"18-24": 0.22, "25-44": 0.46, "45-64": 0.24, "65-74": 0.05, "75-84": 0.02, "85+": 0.01}, "p65": {"65-74": 0.45, "75-84": 0.37, "85+": 0.18}}` | assumed |  |  | adults only; older-old bands follow the population |
| Earlier ED visits in the past year, by cohort: 0, 1, 2-3, 4+ | `{"other": [0.62, 0.21, 0.12, 0.05], "mh": [0.42, 0.22, 0.2, 0.16], "p65": [0.52, 0.24, 0.17, 0.07]}` | assumed |  | oag_ed_2024 | 5% of people make 20% of attendances, as published for WA; the bands are assumed |
| Days since the last visit, by cohort (quartiles) | `{"other": [30, 95, 200], "mh": [14, 45, 130], "p65": [25, 80, 180]}` | assumed |  |  | shorter gaps for mental health |
| People with two or more visits a year, and their share of visits | `{"other": [0.22, 0.48], "mh": [0.45, 0.78], "p65": [0.3, 0.58]}` | assumed |  |  | from the prior-visit bands above |
| Back in an ED within 28 days, base rates by cohort and outcome (D went home, R left or redirected) | `{"other D": 0.1, "other R": 0.24, "mh D": 0.2, "mh R": 0.32, "p65 D": 0.15, "p65 R": 0.28}` | assumed |  | older_28d, dinh2025, mh_incomplete_2025 | older adults 8 to 18% in Australian studies; 14.8% are back within 7 days after not waiting (NSW); mental health higher and higher again after leaving at own risk |
| Share of 28-day returns that happen within 7 days | `{"D": 0.45, "R": 0.6}` | assumed |  | dinh2025 | returns after leaving come sooner |
| Return-risk multiplier by earlier visits: 0, 1, 2-3, 4+ | `[0.7, 1.0, 1.4, 2.1]` | assumed |  |  | frequent users return most; capped at 60% |
| Call-order targets by category, minutes | `[1, 3, 30, 40, 46]` | assumed |  |  | the model calls whoever has waited the largest share of their target; a gentler gradient than the official 0/10/30/60/120 so that categories 4 and 5 are not left for hours, but the more urgent is always seen sooner |

## Sources

- `rogs2026`: Productivity Commission, Report on Government Services 2026, Part E section 12 Public hospitals. https://www.pc.gov.au/ongoing/report-on-government-services/health/public-hospitals/
- `aihw_ed_2425`: AIHW, Emergency department care 2024-25 (web report: presentations, waiting times, care provided, time spent). https://www.aihw.gov.au/hospitals/topics/emergency-departments
- `aihw_glance_2425`: AIHW, Australia's hospitals at a glance 2024-25. https://www.aihw.gov.au/hospitals/overview/hospitals-at-a-glance
- `aihw_ed_2223`: AIHW, Emergency department care 2022-23, appendix tables A1 and A4. https://www.aihw.gov.au/getmedia/77b55e9d-a340-4d47-b1fc-001efba9bf17/emergency-department-care-2022-23-appendix.pdf
- `aihw_mh_ed_2425`: AIHW, Mental health services: state and territory emergency department data 2024-25. https://www.aihw.gov.au/mental-health/topic-areas/hospital-based-services/emergency-departments/state-and-territory-data
- `oag_ed_2024`: WA Auditor General, Quality and Utilisation of Emergency Department Data, Report 4 2024-25. https://audit.wa.gov.au/reports-and-publications/reports/quality-and-utilisation-of-emergency-department-data/
- `dinh2025`: Dinh et al., Characteristics and outcomes of ED patients who did not wait: a state-wide data linkage analysis from NSW (Emergency Medicine Australasia, 2025; episodes 2021-2022). https://onlinelibrary.wiley.com/doi/abs/10.1111/1742-6723.70095
- `older_28d`: Australian studies of 28-day ED re-presentation in older adults: 7.9% of visits (aged 60+, 2020-23) and 18.0% of visits in an inner-city ED. https://pubmed.ncbi.nlm.nih.gov/40910692/ and https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2222161/
- `mh_incomplete_2025`: Who has incomplete ED care among mental health patients in Australia? (Australasian Emergency Care, 2025): leaving at own risk carries a multi-fold risk of 7- and 28-day re-presentation. https://pubmed.ncbi.nlm.nih.gov/40541514/
- `wa_live`: WA Health, Emergency department live activity (public page). https://www.health.wa.gov.au/reports-and-publications/emergency-department-activity/data?report=ed_activity_now

## Calibration reached

Median wait 38 min against a target of 35; did not wait 4.4% against 4.5%; median time before leaving 104 min against 115. Built 2026-09-30T00:19:41.
