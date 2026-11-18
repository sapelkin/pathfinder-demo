"""The calibration table in Pathfinder/README.md (8 simulated weeks): median wait 38 min, did not wait 4.4 %.

The table was produced by tools/build_public_seed.py, which runs tools/waitroom_sim.py (Python's own generator,
seed 17); the first test reproduces it from that tool. The second runs the ported app engine (SeededRNG, seed 62)
for the same eight weeks: the week-to-week spread of this near-capacity queue is several minutes (seeds 1, 2, 3, 7,
17 and 62 give medians of 38 to 44), so the engine is held to the seed's did-not-wait rate within 0.2 points and to
the median wait within that spread, not within one minute.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from pathfinder_engine import simulator
from pathfinder_engine.domain import Outcome
from pathfinder_engine.rng import SeededRNG
from pathfinder_engine.simulator import SimState

WEEKS = 8
TOOL = Path(__file__).resolve().parents[3] / "Pathfinder" / "tools" / "waitroom_sim.py"


def _median(xs: list) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(0.5 * len(xs)))]


@pytest.mark.slow
def test_calibration_table_from_the_seed_tool(seed):
    if not TOOL.exists():
        pytest.skip("Pathfinder/tools/waitroom_sim.py is not in this checkout")
    spec = importlib.util.spec_from_file_location("waitroom_sim", TOOL)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    import json
    from importlib import resources
    raw = json.loads(resources.files("pathfinder_engine").joinpath("data/pathfinder_seed.json").read_text())
    params = {k: raw["sim"][k] for k in ("priority_targets", "patience_median_min", "patience_sigma", "service_slack", "service_lag_hours")}
    r = tool.simulate(params, raw["aggregates"], raw["demo_ed"]["weekly_presentations"], raw["arrival_shape"], weeks=WEEKS, seed=17)
    assert abs(r["median_wait_min"] - 38) <= 1, r
    assert abs(r["dnw_rate"] * 100 - 4.4) <= 0.2, r
    assert r["median_wait_min"] == seed.sim.calibration.median_wait_min
    assert r["dnw_rate"] == seed.sim.calibration.dnw_rate


@pytest.mark.slow
def test_engine_eight_weeks_on_the_seed(seed, config):
    s = SimState(0, SeededRNG(seed.sim.seed))
    end = WEEKS * 10_080
    while s.now < end:
        simulator.step(s, config)
    arrived = [e for e in s.episodes if e.outcome is not Outcome.redirected]
    waits = [e.calledAt - e.arrival for e in arrived if e.calledAt is not None]
    left = [e for e in arrived if e.outcome is Outcome.didNotWait]
    median_wait = _median(waits)
    dnw = len(left) / len(arrived) * 100
    leave = _median([e.outcomeAt - e.arrival for e in left])
    assert abs(dnw - 4.4) <= 0.2, f"did-not-wait rate {dnw:.2f} %"
    assert 38 - 1 <= median_wait <= 38 + 6, f"median wait {median_wait} min (the engine's seed spread is 38–44)"
    assert abs(leave - 104) <= 10, f"median time before leaving {leave} min"
    assert _median([e.calledAt - e.arrival for e in arrived if e.ats == 2 and e.calledAt is not None]) <= 15
    assert len(arrived) > WEEKS * 1200
