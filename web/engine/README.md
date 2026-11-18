# pathfinder_engine

Pathfinder's models and the simulated department they run on, in Python. Standard library only, so the same package
runs under CPython and, in the browser, under Pyodide. The seed (`data/pathfinder_seed.json`) and WA Health's
live-activity snapshot (`data/ed_activity_now.json`) ship inside the package and load through `importlib.resources`.

```sh
pip install -e .          # Python 3.11+
pytest -m "not slow"      # 87 tests, about 12 s; drop -m to add the two 8-week calibration runs
```

## What is where

| Module | What it does |
|---|---|
| `simulator.py`, `clock.py`, `rng.py` | The demo waiting room in one-minute steps, on a seeded generator so every run is identical |
| `eta.py` | The wait model: 100 simulated futures of the room, the 10th, 50th and 90th percentile per person |
| `parser.py`, `templates.py` | The triage note as structured fields; the eleven typed templates |
| `triage.py` | The rule table that suggests an ATS category, with the published descriptor it matched |
| `ranker.py` | The follow-through list: did-not-wait policy tiers, then return risk |
| `hexgrid.py`, `network.py`, `rightdoor.py` | The demo metro, its services, and the ring search from home with travel time, hours and fit |
| `feed.py`, `metro.py` | WA Health's published live-activity numbers, and Metro mode: any of ten metropolitan EDs, rebuilt with Little's law |
| `model.py`, `demo.py`, `units.py`, `personas.py` | The whole document, the guided demo, the unit catalogue, the demo's own patients |
| `routes.py`, `dispatch.py` | Every API route as a plain function, and the in-browser host that calls them |

## The numbers

`tools/build_public_seed.py` builds the seed from published figures and stated assumptions, calibrates the waiting
room by simulation (`tools/waitroom_sim.py`, about 25 s), and writes the table of every figure to
[`docs/PUBLIC_FIGURES.md`](../../docs/PUBLIC_FIGURES.md). `tools/fetch_ed_activity.py` refreshes the live-activity
snapshot from WA Health's public page.

## The API without a server (`dispatch.py`)

```python
from pathfinder_engine.dispatch import Dispatcher

d = Dispatcher(now="2026-11-05T03:00:00.000Z")          # the demo afternoon, Saturday 2:30 pm, seed 62
r = d.handle("GET", "/state")                           # {"status": 200, "body": State}
r = d.handle("POST", "/tick", {}, {"clientNow": "2026-11-05T03:00:00.000Z"})
r = d.handle("GET", "/rightdoor", {"id": 1054, "purpose": "nextTime"})
text = d.export_document()                              # JSON of the whole document → localStorage / download
d.import_document(text)                                 # ValueError when it is not a Pathfinder document
```

`handle(method, path, query=None, body=None, now=None)` returns `{"status": int, "body": <json-serialisable>}`;
errors are `{"error": "..."}` with an HTTP status (422 for a missing or out-of-range field, 400 for a semantic error,
404 for an unknown episode or route, 405 for a wrong method). The wall clock is the browser's: `body.clientNow` (or
`now`) is remembered and used for the tick, the demo script, banners and capture times.

The website loads the package as a wheel inside a Web Worker (`web/app/src/worker/`); `web/app/scripts/pyodide-assets.mjs`
builds the wheel at build time. Measured under Pyodide: `Dispatcher()` about 0.2 s, a tick 0.04 s, an ETA estimate
0.05 s.
