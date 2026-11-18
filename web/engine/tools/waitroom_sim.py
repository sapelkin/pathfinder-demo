"""The demo waiting room in Python: the same minute-step algorithm the engine runs (pathfinder_engine/simulator.py),
used to calibrate a seed's patience, capacity slack and lag to its targets. Used by build_public_seed.py
to calibrate the public-edition seed."""
from __future__ import annotations

import math
import random

ATS_TARGET_MIN = [0, 10, 30, 60, 120]

# ----------------------------------------------------------------------------------------------------------------
# Waiting-room simulation. pathfinder_engine/simulator.py runs the same algorithm; keep them in step.
# Minute steps. Arrivals are Poisson from the weekly template. Capacity follows demand with a lag and some slack.
# ATS 1 is seen at once; everyone else is called by the largest share of their priority target already waited.
# Each waiting patient has a patience time; if nobody calls them first they leave (did not wait).
# ----------------------------------------------------------------------------------------------------------------

def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def pick(rng: random.Random, probs) -> int:
    u, acc = rng.random(), 0.0
    for i, p in enumerate(probs):
        acc += p
        if u <= acc:
            return i
    return len(probs) - 1


def simulate(params: dict, agg: dict, weekly: float, shape: list[float], weeks: int = 6, seed: int = 7,
             track_eta: bool = False) -> dict:
    rng = random.Random(seed)
    targets = params["priority_targets"]
    waiting: list[list] = []          # [ats, arrived_minute, patience_minute]
    waits = {a: [] for a in range(1, 6)}
    left = {a: 0 for a in range(1, 6)}
    arrived = {a: 0 for a in range(1, 6)}
    leave_minutes: list[float] = []
    queue_len: list[int] = []
    sat_queue: list[int] = []
    for t in range(weeks * 10080):
        h = (t // 60) % 168
        lam = weekly * shape[h] / 60.0
        for _ in range(poisson(rng, lam)):
            a = pick(rng, agg["triage_mix"]) + 1
            if rng.random() < agg["referred_at_triage_by_ats"][a - 1]:
                continue
            arrived[a] += 1
            med = params["patience_median_min"][a - 1]
            pat = math.exp(math.log(med) + params["patience_sigma"] * rng.gauss(0, 1))
            waiting.append([a, t, pat])
        # ATS 1 goes straight in
        keep = []
        for p in waiting:
            if p[0] == 1:
                waits[1].append(0.0)
            else:
                keep.append(p)
        waiting = keep
        mu = params["service_slack"] * weekly * shape[(h - params["service_lag_hours"]) % 168] / 60.0
        for _ in range(poisson(rng, mu)):
            if not waiting:
                break
            best = max(range(len(waiting)), key=lambda i: ((t - waiting[i][1]) / targets[waiting[i][0] - 1], -waiting[i][0]))
            a, t0, _ = waiting.pop(best)
            waits[a].append(t - t0)
        keep = []
        for p in waiting:
            if t - p[1] >= p[2]:
                left[p[0]] += 1
                leave_minutes.append(t - p[1])
            else:
                keep.append(p)
        waiting = keep
        if t % 15 == 0 and t >= 10080:
            queue_len.append(len(waiting))
            if h in (134, 135):            # Saturday 2 pm to 4 pm, the demo's time of day
                sat_queue.append(len(waiting))

    def q(xs, p):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None

    all_waits = [w for a in waits for w in waits[a]]
    on_time = sum(1 for a in waits for w in waits[a] if w <= max(ATS_TARGET_MIN[a - 1], 2))
    total = sum(arrived.values())
    return {
        "median_wait_min": q(all_waits, 0.5),
        "median_wait_by_ats": [q(waits[a], 0.5) for a in range(1, 6)],
        "seen_on_time": round(on_time / max(1, len(all_waits)), 3),
        "dnw_rate": round(sum(left.values()) / max(1, total), 4),
        "dnw_by_ats": [round(left[a] / max(1, arrived[a]), 4) for a in range(1, 6)],
        "dnw_median_leave_min": q(leave_minutes, 0.5),
        "queue_median": q(queue_len, 0.5),
        "queue_p90": q(queue_len, 0.9),
        "queue_saturday_2_4pm_median": q(sat_queue, 0.5),
    }


def calibrate(agg: dict, weekly: float, shape: list[float], *, priority_targets=(1, 3, 30, 45, 50),
              sigmas=(0.35, 0.5, 0.65), slacks=(0.90, 0.93, 0.96, 0.99, 1.02), lags=(0, 1, 2, 3), iters: int = 4) -> tuple[dict, dict]:
    """Grid over capacity slack, lag and patience spread; inside each, fit patience per category to the DNW rates.
    Score: median wait and median time before leaving against the targets in `agg`. The defaults are the grid the
    Data edition was calibrated with; the public edition widens it."""
    target_wait = agg["wait_all"]["median_min"]
    target_dnw = [x["rate"] or 0.0 for x in agg["dnw_by_ats"]]
    target_leave = agg["dnw_minutes_before_leaving"]["p50"]

    def fit_patience(p: dict, seed: int) -> dict:
        for _ in range(iters):
            r = simulate(p, agg, weekly, shape, weeks=3, seed=seed)
            new = list(p["patience_median_min"])
            for i in range(2, 5):   # category 2 almost never leaves (0.35%); too few cases to fit, so it stays fixed
                got, want = r["dnw_by_ats"][i], target_dnw[i]
                if want > 0 and got > 0:
                    new[i] = max(20.0, min(5000.0, new[i] * (got / want) ** 0.7))
                elif want > 0:
                    new[i] *= 0.6
            p = dict(p, patience_median_min=[round(x, 1) for x in new])
        return p

    base = {"priority_targets": list(priority_targets), "patience_median_min": [10000, 2000, 300, 300, 300]}
    best = None
    for sigma in sigmas:
        for slack in slacks:
            for lag in lags:
                p = fit_patience(dict(base, patience_sigma=sigma, service_slack=slack, service_lag_hours=lag), seed=13)
                r = simulate(p, agg, weekly, shape, weeks=3, seed=11)
                score = (abs((r["median_wait_min"] or 0) - target_wait) / target_wait
                         + abs((r["dnw_median_leave_min"] or 0) - target_leave) / target_leave
                         + 3 * abs(r["dnw_rate"] - agg["dnw_rate"]) / agg["dnw_rate"])
                if best is None or score < best[0]:
                    best = (score, p)
    params = best[1]
    report = simulate(params, agg, weekly, shape, weeks=8, seed=17)
    report["score"] = round(best[0], 3)
    report["targets"] = {"median_wait_min": target_wait, "dnw_rate": agg["dnw_rate"], "dnw_by_ats": target_dnw,
                         "dnw_median_leave_min": target_leave}
    return params, report
