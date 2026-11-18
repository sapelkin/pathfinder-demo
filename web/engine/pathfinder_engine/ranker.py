"""Puts every discharged (D) and left or redirected (R) episode on the follow-through list with a tier.

Tiers follow the WACHS "Did Not Wait" policy (v3.01,
2024): any mental health concern is at least moderate risk; self-harm, suicidal ideation or a Mental Health Act
referral is high risk. Risk figures are 28-day return rates from published studies and stated assumptions, for
another ED visit for people with the same cohort, outcome and number of earlier visits.
"""
from __future__ import annotations

import math
from functools import cmp_to_key
from typing import NamedTuple, Optional

from .domain import Cohort, Episode, FollowTier, FollowUp, Outcome
from .seed import ReturnRow


class Risk(NamedTuple):
    r7: Optional[float]
    r28: Optional[float]
    n: Optional[int]
    basis: str


def band(prior: int) -> str:
    if prior == 0:
        return "0"
    if prior == 1:
        return "1"
    if 2 <= prior <= 3:
        return "2-3"
    return "4+"


class FollowUpRanker:
    def __init__(self, returns: list[ReturnRow], returns_by_cohort: list[ReturnRow]):
        self.returns = returns
        self.returns_by_cohort = returns_by_cohort

    def risk(self, cohort: Cohort, outcome: Outcome, prior: int) -> Risk:
        o = "D" if outcome is Outcome.discharged else "R"
        b = band(prior)
        who = (("people" if cohort is Cohort.other else cohort.label.lower() + " patients") + " who "
               + ("went home" if outcome is Outcome.discharged else "left or were redirected"))
        if prior == 0:
            visits = "no earlier visit this year"
        elif b == "4+":
            visits = "4 or more earlier visits"
        else:
            visits = f"{b} earlier visit{'' if b == '1' else 's'}"
        r = next((x for x in self.returns if x.cohort == cohort.value and x.outcome == o and x.prior == b), None)
        if r is not None and r.ret28 is not None:
            return Risk(r.ret7, r.ret28, r.n, f"Return-risk table: {who}, {visits}")
        r = next((x for x in self.returns_by_cohort if x.cohort == cohort.value and x.outcome == o), None)
        if r is not None:
            return Risk(r.ret7, r.ret28, r.n, f"Return-risk table: {who}")
        return Risk(None, None, None, "No comparable group")

    def assign(self, e: Episode) -> Optional[FollowUp]:
        outcome = e.outcome
        if outcome is None or not outcome.needs_follow_up:
            return None
        r = self.risk(e.cohort, outcome, e.priorVisits)
        reasons: list[str] = []
        if outcome in (Outcome.didNotWait, Outcome.leftAtOwnRisk):
            verb = "Left before being seen" if outcome is Outcome.didNotWait else "Left before care was finished"
            high = any(f.is_high_risk for f in e.flags)
            if high:
                tier = FollowTier.callNow
                what = ", ".join(sorted(f.label for f in e.flags if f.is_high_risk)).lower()
                reasons.append(f"{verb} with {what}: high risk under the did-not-wait policy")
            elif e.ats <= 2:
                tier = FollowTier.callNow
                reasons.append(f"{verb} at triage category {e.ats}")
            elif e.cohort is Cohort.mh or e.ats == 3 or e.cohort is Cohort.p65 or e.priorVisits >= 4 or e.priorDNW:
                tier = FollowTier.callToday
                if e.cohort is Cohort.mh:
                    reasons.append(f"{verb}: any mental health presentation is at least moderate risk")
                elif e.cohort is Cohort.p65:
                    reasons.append(f"{verb}, aged {e.age}")
                elif e.ats == 3:
                    reasons.append(f"{verb} at triage category 3")
                else:
                    reasons.append(verb)
                if e.priorDNW:
                    reasons.append("Has left before on an earlier visit")
                if e.priorVisits >= 4:
                    reasons.append(f"{e.priorVisits} earlier ED visits this year")
            else:
                tier = FollowTier.within24h
                reasons.append(f"{verb} at triage category {e.ats}, low risk")
        elif outcome is Outcome.redirected:
            tier = FollowTier.within24h
            reasons.append(f"Redirected at triage to {e.redirectService or 'another service'}: check they got there")
        elif outcome is Outcome.discharged:
            if e.cohort is Cohort.mh and (e.priorVisits >= 2 or any(f.is_high_risk for f in e.flags)):
                tier = FollowTier.within24h
                reasons.append(f"Mental health presentation with {e.priorVisits} earlier visits this year")
            elif (r.r28 or 0) >= 0.35 or e.priorVisits >= 4:
                tier = FollowTier.within24h
                reasons.append(f"{e.priorVisits} earlier ED visits this year: high chance of coming back")
            elif e.cohort is Cohort.p65 and e.priorVisits >= 2:
                tier = FollowTier.within24h
                reasons.append(f"Aged {e.age} with {e.priorVisits} earlier visits: confirm a named next step")
            else:
                tier = FollowTier.autoMessage
                reasons.append("Routine discharge")
        else:
            return None
        if (r.r28 is not None and r.r28 >= 0.30 and tier is FollowTier.within24h
                and not any("chance" in x for x in reasons)):
            reasons.append(f"About {int(_round_half_away(r.r28 * 100))} in 100 people like this are back within 28 days")
        return FollowUp(tier=tier, reasons=reasons, risk7=r.r7, risk28=r.r28, riskN=r.n, riskBasis=r.basis)


def _round_half_away(x: float) -> float:
    return math.floor(x + 0.5) if x >= 0 else -math.floor(-x + 0.5)


def _compare(a: Episode, b: Episode) -> int:
    """Order inside a tier: higher 28-day risk first, then whoever has been waiting longest for contact."""
    ta = a.followUp.tier if a.followUp else FollowTier.autoMessage
    tb = b.followUp.tier if b.followUp else FollowTier.autoMessage
    if ta != tb:
        return -1 if ta < tb else 1
    ra = (a.followUp.risk28 if a.followUp and a.followUp.risk28 is not None else 0)
    rb = (b.followUp.risk28 if b.followUp and b.followUp.risk28 is not None else 0)
    if abs(ra - rb) > 0.0001:
        return -1 if ra > rb else 1
    oa = a.outcomeAt or 0
    ob = b.outcomeAt or 0
    if oa == ob:
        return 0
    return -1 if oa < ob else 1


sort_key = cmp_to_key(_compare)


def sort(episodes: list[Episode]) -> list[Episode]:
    return sorted(episodes, key=sort_key)
