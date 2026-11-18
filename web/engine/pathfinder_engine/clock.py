"""The simulated clock: an integer minute since Monday 00:00 of the demo week, and its text.

``SimClock``.
"""
from __future__ import annotations

WEEK = 10_080
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def hour_of_week(t: int) -> int:
    return (((t % WEEK) + WEEK) % WEEK) // 60


def minute_of_day(t: int) -> int:
    return ((t % 1440) + 1440) % 1440


def day_of_week(t: int) -> int:
    """0 = Monday."""
    return (((t % WEEK) + WEEK) % WEEK) // 1440


def time(t: int) -> str:
    m = minute_of_day(t)
    h = m // 60
    mm = m % 60
    h12 = 12 if h % 12 == 0 else h % 12
    return f"{h12}:{mm:02d} {'am' if h < 12 else 'pm'}"


def text(t: int) -> str:
    return f"{DAYS[day_of_week(t)]} {time(t)}"


def duration(minutes: int) -> str:
    m = max(0, minutes)
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h" if m % 60 == 0 else f"{m // 60} h {m % 60} m"
