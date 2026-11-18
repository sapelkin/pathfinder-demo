"""Refreshes pathfinder_engine/data/ed_activity_now.json from WA Health's public "Emergency department live activity"
page (public data, not hackathon Data). Finds the table by its headers, so a change of page chrome does not break it;
writes the same JSON shape the engine reads, with taken_text, taken_at (Perth time) and minute_of_week (SimClock's
minutes since Monday 00:00). Standard library only; leaves the current snapshot untouched when the page cannot be
read or parsed.

    python3 tools/fetch_ed_activity.py [--url URL] [--out PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

URL = "https://www.health.wa.gov.au/reports-and-publications/emergency-department-activity/data?report=ed_activity_now"
OUT = Path(__file__).resolve().parents[1] / "pathfinder_engine" / "data" / "ed_activity_now.json"
PERTH = timezone(timedelta(hours=8))

# The short names the engine and the explainer use, by a distinctive part of the published name.
SHORT = [("Armadale", "Armadale"), ("Fiona Stanley", "Fiona Stanley"), ("Joondalup", "Joondalup"),
         ("King Edward", "King Edward"), ("Peel", "Peel"), ("Children", "Perth Children's"), ("Rockingham", "Rockingham"),
         ("Royal Perth", "Royal Perth"), ("Gairdner", "Sir Charles Gairdner"), ("Midland", "Midland"), ("Osborne", "Osborne Park")]


class Tables(HTMLParser):
    """Every table on the page as rows of cell texts, plus the page's visible text for the "as at" line."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.texts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.tables:
            if self.row:
                self.tables[-1].append(self.row)
            self.row = None

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)
        self.texts.append(data)


def _header_index(headers: list[str], *needles: str) -> int | None:
    for i, h in enumerate(headers):
        low = h.lower()
        if all(n in low for n in needles):
            return i
    return None


def _int(text: str) -> int:
    m = re.search(r"\d+", text.replace(",", ""))
    return int(m.group()) if m else 0


def parse(html: str) -> dict:
    p = Tables()
    p.feed(html)
    chosen = None
    for table in p.tables:
        if not table:
            continue
        headers = table[0]
        if _header_index(headers, "wait") is not None and _header_index(headers, "waiting") is not None:
            chosen = table
            break
    if chosen is None:
        raise ValueError("no table with 'waiting' and 'wait' columns found")
    headers = chosen[0]
    i_name = _header_index(headers, "hospital") if _header_index(headers, "hospital") is not None else 0
    i_wait = _header_index(headers, "average", "wait")
    if i_wait is None:
        i_wait = _header_index(headers, "time")
    # The count of people waiting: a "waiting" column that is not the average-time one.
    i_waiting = next((i for i, h in enumerate(headers) if "waiting" in h.lower() and i != i_wait and "time" not in h.lower()), None)
    i_in = _header_index(headers, "in the")
    if i_in is None:
        i_in = next((i for i in (_header_index(headers, "being"), _header_index(headers, "total")) if i is not None), None)
    if i_wait is None or i_waiting is None or i_in is None:
        raise ValueError(f"unexpected headers: {headers}")
    hospitals = []
    for row in chosen[1:]:
        if len(row) <= max(i_name, i_wait, i_waiting, i_in):
            continue
        name = row[i_name]
        if not name or name.lower().startswith("total"):
            continue
        short = next((s for needle, s in SHORT if needle.lower() in name.lower()), name.split(" ")[0])
        hospitals.append({"name": name, "short": short, "t4_avg_wait_min": _int(row[i_wait]), "waiting": _int(row[i_waiting]),
                          "in_ed": _int(row[i_in])})
    if not hospitals:
        raise ValueError("the table has no hospital rows")
    text = " ".join(" ".join(p.texts).split())
    m = re.search(r"((?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s+\d{1,2}\s+\w+\s+\d{4}\s+\d{1,2}:\d{2}\s*[AP]M)", text, re.I)
    if m:
        taken_text = m.group(1)
        taken_at = datetime.strptime(re.sub(r"\s+", " ", taken_text.replace(",", "")), "%A %d %B %Y %I:%M %p").replace(tzinfo=PERTH)
    else:
        taken_at = datetime.now(PERTH).replace(second=0, microsecond=0)
        taken_text = taken_at.strftime("%A, %-d %B %Y %-I:%M %p")
    minute_of_week = taken_at.weekday() * 1440 + taken_at.hour * 60 + taken_at.minute
    return {
        "source": "WA Health, Emergency department live activity (public web page)", "url": URL, "taken_text": taken_text,
        "taken_at": taken_at.isoformat(), "minute_of_week": minute_of_week,
        "note": ("Public data, not hackathon Data. The page says the figures serve as a guide only; the average waiting "
                 "time is for triage category 4, the most common category."),
        "hospitals": hospitals,
    }


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("--url", default=URL)
    a.add_argument("--out", default=str(OUT))
    a.add_argument("--dry-run", action="store_true", help="print the JSON instead of writing it")
    o = a.parse_args()
    try:
        req = urllib.request.Request(o.url, headers={"User-Agent": "Mozilla/5.0 (Pathfinder snapshot fetcher)"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError) as err:
        print(f"could not read the page ({err}); the current snapshot is unchanged", file=sys.stderr)
        return 2
    try:
        snap = parse(html)
    except ValueError as err:
        print(f"could not parse the page ({err}); the current snapshot is unchanged", file=sys.stderr)
        return 3
    text = json.dumps(snap, indent=2, ensure_ascii=False) + "\n"
    if o.dry_run:
        print(text)
    else:
        Path(o.out).write_text(text, encoding="utf-8")
        print(f"wrote {o.out}: {len(snap['hospitals'])} hospitals as at {snap['taken_text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
