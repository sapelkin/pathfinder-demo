"""pathfinder_seed.json, built by tools/build_public_seed.py from published figures and stated assumptions.

Property names mirror the JSON so decoding needs no key
mapping; suppressed values arrive as ``None``. The seed ships inside the package (``data/pathfinder_seed.json``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any, Optional


@dataclass(frozen=True)
class DemoED:
    name: str
    annual_presentations: int
    weekly_presentations: float
    basis: str


@dataclass(frozen=True)
class Quantiles:
    p25: Optional[float]
    p50: Optional[float]
    p75: Optional[float]
    p90: Optional[float]
    n: Optional[int]


@dataclass(frozen=True)
class CohortByATS:
    ats: int
    n: Optional[int]
    mh: Optional[float]
    p65: Optional[float]


@dataclass(frozen=True)
class DNWByATS:
    ats: int
    n: Optional[int]
    dnw: Optional[int]
    rate: Optional[float]


@dataclass(frozen=True)
class WaitByATS:
    ats: int
    n: Optional[int]
    median_min: float
    p90_min: float
    seen_on_time: float


@dataclass(frozen=True)
class WaitAll:
    n: Optional[int]
    median_min: float
    seen_on_time: float


@dataclass(frozen=True)
class CareHours:
    n: Optional[int]
    median: float
    log_sd: float


@dataclass(frozen=True)
class CohortFlags:
    n: Optional[int]
    self_harm: Optional[float]
    drugs_alcohol: Optional[float]
    police: Optional[float]
    ambulance: Optional[float]


@dataclass(frozen=True)
class ArrivalModes:
    """Mode of arrival shares by cohort (data dictionary codes 1, 2, 3, 5 and 10), metro EDs."""

    n: Optional[int]
    private: Optional[float]
    public: Optional[float]
    ambulance: Optional[float]
    police: Optional[float]
    taxi: Optional[float]


@dataclass(frozen=True)
class ReturnRow:
    cohort: str
    outcome: str
    prior: Optional[str]
    n: Optional[int]
    ret7: Optional[float]
    ret28: Optional[float]


@dataclass(frozen=True)
class Recurrence:
    persons: Optional[int]
    persons_2plus: Optional[float]
    visits_by_2plus: Optional[float]


@dataclass(frozen=True)
class Aggregates:
    metro_presentations: int
    triage_mix: list[float]
    cohort_by_ats: list[CohortByATS]
    referred_at_triage_by_ats: list[float]
    dnw_by_ats: list[DNWByATS]
    dnw_rate: Optional[float]
    dnw_minutes_before_leaving: Quantiles
    wait_by_ats: list[WaitByATS]
    wait_all: WaitAll
    admit_by_cohort_ats: dict[str, list[Optional[float]]]
    left_at_own_risk_by_cohort: dict[str, Optional[float]]
    care_hours: dict[str, CareHours]
    flags_by_cohort: dict[str, CohortFlags]
    arrival_mode_by_cohort: Optional[dict[str, ArrivalModes]]
    age_bands_by_cohort: dict[str, dict[str, Optional[int]]]
    prior_visits_by_cohort: dict[str, dict[str, Optional[int]]]
    days_since_last_visit_by_cohort: dict[str, Quantiles]
    returns: list[ReturnRow]
    returns_by_cohort: list[ReturnRow]
    recurrence_by_cohort: dict[str, Recurrence]


@dataclass(frozen=True)
class StatewideKPI:
    presentations: int
    seen_on_time: float
    median_wait_min: float
    mh_seen_on_time: float
    mh_median_wait_min: float
    p65_seen_on_time: float
    p65_median_wait_min: float
    dnw_n: Optional[int]
    dnw_rate: Optional[float]
    left_or_redirected_rate: Optional[float]
    dnw_ats123_share: Optional[float]
    dnw_median_leave_min: float
    returns: list[ReturnRow]
    raw: dict[str, Any]

    def return_rate(self, cohort: str, outcome: str) -> Optional[ReturnRow]:
        return next((r for r in self.returns if r.cohort == cohort and r.outcome == outcome), None)


@dataclass(frozen=True)
class Calibration:
    median_wait_min: Optional[float]
    median_wait_by_ats: list[Optional[float]]
    seen_on_time: float
    dnw_rate: float
    dnw_by_ats: list[float]
    dnw_median_leave_min: Optional[float]
    queue_saturday_2_4pm_median: Optional[float]


@dataclass(frozen=True)
class SimParams:
    priority_targets: list[float]
    patience_median_min: list[float]
    patience_sigma: float
    service_slack: float
    service_lag_hours: int
    seed: int
    calibration: Calibration
    method: str


@dataclass(frozen=True)
class SeedFile:
    version: int
    built_at: str
    note: str
    demo_ed: DemoED
    arrival_shape: list[float]
    aggregates: Aggregates
    kpi_statewide: StatewideKPI
    sim: SimParams

    @staticmethod
    def load() -> "SeedFile":
        text = resources.files("pathfinder_engine").joinpath("data/pathfinder_seed.json").read_text(encoding="utf-8")
        return SeedFile.from_json(text)

    @staticmethod
    def from_json(text: str) -> "SeedFile":
        return _decode(json.loads(text))


def _returns(rows: list[dict[str, Any]]) -> list[ReturnRow]:
    return [ReturnRow(cohort=r["cohort"], outcome=r["outcome"], prior=r.get("prior"), n=r.get("n"),
                      ret7=r.get("ret7"), ret28=r.get("ret28")) for r in rows]


def _quantiles(d: dict[str, Any]) -> Quantiles:
    return Quantiles(p25=d.get("p25"), p50=d.get("p50"), p75=d.get("p75"), p90=d.get("p90"), n=d.get("n"))


def _decode(d: dict[str, Any]) -> SeedFile:
    a = d["aggregates"]
    k = d["kpi_statewide"]
    s = d["sim"]
    cal = s["calibration"]
    aggregates = Aggregates(
        metro_presentations=a["metro_presentations"],
        triage_mix=list(a["triage_mix"]),
        cohort_by_ats=[CohortByATS(ats=x["ats"], n=x.get("n"), mh=x.get("mh"), p65=x.get("p65")) for x in a["cohort_by_ats"]],
        referred_at_triage_by_ats=list(a["referred_at_triage_by_ats"]),
        dnw_by_ats=[DNWByATS(ats=x["ats"], n=x.get("n"), dnw=x.get("dnw"), rate=x.get("rate")) for x in a["dnw_by_ats"]],
        dnw_rate=a.get("dnw_rate"),
        dnw_minutes_before_leaving=_quantiles(a["dnw_minutes_before_leaving"]),
        wait_by_ats=[WaitByATS(ats=x["ats"], n=x.get("n"), median_min=x["median_min"], p90_min=x["p90_min"],
                               seen_on_time=x["seen_on_time"]) for x in a["wait_by_ats"]],
        wait_all=WaitAll(n=a["wait_all"].get("n"), median_min=a["wait_all"]["median_min"],
                         seen_on_time=a["wait_all"]["seen_on_time"]),
        admit_by_cohort_ats={c: list(v) for c, v in a["admit_by_cohort_ats"].items()},
        left_at_own_risk_by_cohort=dict(a["left_at_own_risk_by_cohort"]),
        care_hours={c: CareHours(n=v.get("n"), median=v["median"], log_sd=v["log_sd"]) for c, v in a["care_hours"].items()},
        flags_by_cohort={c: CohortFlags(n=v.get("n"), self_harm=v.get("self_harm"), drugs_alcohol=v.get("drugs_alcohol"),
                                        police=v.get("police"), ambulance=v.get("ambulance"))
                         for c, v in a["flags_by_cohort"].items()},
        arrival_mode_by_cohort=({c: ArrivalModes(n=v.get("n"), private=v.get("private"), public=v.get("public"),
                                                 ambulance=v.get("ambulance"), police=v.get("police"), taxi=v.get("taxi"))
                                 for c, v in a["arrival_mode_by_cohort"].items()}
                                if a.get("arrival_mode_by_cohort") is not None else None),
        age_bands_by_cohort={c: dict(v) for c, v in a["age_bands_by_cohort"].items()},
        prior_visits_by_cohort={c: dict(v) for c, v in a["prior_visits_by_cohort"].items()},
        days_since_last_visit_by_cohort={c: _quantiles(v) for c, v in a["days_since_last_visit_by_cohort"].items()},
        returns=_returns(a["returns"]),
        returns_by_cohort=_returns(a["returns_by_cohort"]),
        recurrence_by_cohort={c: Recurrence(persons=v.get("persons"), persons_2plus=v.get("persons_2plus"),
                                            visits_by_2plus=v.get("visits_by_2plus"))
                              for c, v in a["recurrence_by_cohort"].items()},
    )
    kpi = StatewideKPI(
        presentations=k["presentations"], seen_on_time=k["seen_on_time"], median_wait_min=k["median_wait_min"],
        mh_seen_on_time=k["mh_seen_on_time"], mh_median_wait_min=k["mh_median_wait_min"],
        p65_seen_on_time=k["p65_seen_on_time"], p65_median_wait_min=k["p65_median_wait_min"], dnw_n=k.get("dnw_n"),
        dnw_rate=k.get("dnw_rate"), left_or_redirected_rate=k.get("left_or_redirected_rate"),
        dnw_ats123_share=k.get("dnw_ats123_share"), dnw_median_leave_min=k["dnw_median_leave_min"],
        returns=_returns(k["returns"]), raw=dict(k),
    )
    sim = SimParams(
        priority_targets=[float(x) for x in s["priority_targets"]],
        patience_median_min=[float(x) for x in s["patience_median_min"]],
        patience_sigma=float(s["patience_sigma"]), service_slack=float(s["service_slack"]),
        service_lag_hours=int(s["service_lag_hours"]), seed=int(s["seed"]),
        calibration=Calibration(median_wait_min=cal.get("median_wait_min"),
                                median_wait_by_ats=list(cal["median_wait_by_ats"]), seen_on_time=cal["seen_on_time"],
                                dnw_rate=cal["dnw_rate"], dnw_by_ats=list(cal["dnw_by_ats"]),
                                dnw_median_leave_min=cal.get("dnw_median_leave_min"),
                                queue_saturday_2_4pm_median=cal.get("queue_saturday_2_4pm_median")),
        method=s["method"],
    )
    return SeedFile(version=d["version"], built_at=d["built_at"], note=d["note"],
                    demo_ed=DemoED(name=d["demo_ed"]["name"], annual_presentations=d["demo_ed"]["annual_presentations"],
                                   weekly_presentations=float(d["demo_ed"]["weekly_presentations"]),
                                   basis=d["demo_ed"]["basis"]),
                    arrival_shape=[float(x) for x in d["arrival_shape"]], aggregates=aggregates, kpi_statewide=kpi, sim=sim)
