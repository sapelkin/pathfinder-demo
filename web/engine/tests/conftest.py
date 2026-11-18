from __future__ import annotations

import pytest

from pathfinder_engine import network
from pathfinder_engine.domain import ArrivalMode, ClinicalFlag, Cohort, Episode
from pathfinder_engine.seed import SeedFile
from pathfinder_engine.simulator import SimConfig

SAT_1430 = 5 * 1440 + 14 * 60 + 30
SAT_1500 = 5 * 1440 + 15 * 60


@pytest.fixture(scope="session")
def seed() -> SeedFile:
    return SeedFile.load()


@pytest.fixture(scope="session")
def config(seed: SeedFile) -> SimConfig:
    return SimConfig(seed)


def episode(name: str, age: int, cohort: Cohort, complaint_key: str, ats: int, mode: ArrivalMode, x: float, y: float,
            flags: set[ClinicalFlag] | None = None, prior: int = 0, complaint: str | None = None) -> Episode:
    lat, lon = network.coordinate(x, y)
    return Episode(id=0, name=name, age=age, sex="M", cohort=cohort, complaint=complaint or complaint_key.replace("_", " "),
                   complaintKey=complaint_key, ats=ats, arrival=0, arrivalMode=mode, priorVisits=prior, daysSinceLast=None,
                   priorDNW=False, flags=flags or set(), homeLat=lat, homeLon=lon, homeSuburb=network.suburb(x, y))


@pytest.fixture
def alan() -> Episode:
    e = episode("Alan P.", 72, Cohort.p65, "chest_pain", 2, ArrivalMode.car, 5.3, -0.5, prior=2, complaint="Chest pain")
    e.daysSinceLast = 40
    e.homeSuburb = "Riverbend"
    return e
