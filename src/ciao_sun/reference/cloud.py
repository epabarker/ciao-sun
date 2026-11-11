"""The cloud category: which sky a forecast gives a query's window (spec #27, "Cloud category").

The forecast is Open-Meteo's hourly `cloud_cover` with `models=ukmo_seamless`,
requested with `timeformat=unixtime`, so every hour is a UTC instant and no
clock change can misplace one. `C` is the time-weighted mean, over the span,
of `cloud_cover` interpolated linearly between the hours (each value is an
instant, not an hour's average). The span is the Morning window, or the last
3 h of the Evening window (all of it if shorter), taken from the same window
plans the scorer uses.

The JS forecast adapter (`app/src/forecast/`) is the one that fetches; this is
its reference. Both are held to `fixtures/cloud/cases.json`.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from ciao_sun.reference.contract import Answer, Query, Sky
from ciao_sun.reference.evening import plan_evening
from ciao_sun.reference.morning import plan_morning
from ciao_sun.reference.windows import TIME_ZONE
from ciao_sun.solar import sun_track

CLEAR_BELOW_PCT = 25.0  # C below this is clear
OVERCAST_FROM_PCT = 80.0  # C at or above this is overcast; between the two, partly cloudy
EVENING_CLOUD_SPAN_MIN = 180  # the evening span is this much of the window's end
FORECAST_CELLS_PER_DEG = 20  # the request coordinate is rounded to 1/20 = 0.05 degrees


def cloud_span(query: Query) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """The instants `C` is averaged between, or None when the query has no window."""
    track = sun_track(query.origin_lat, query.origin_lon, query.date, tz=TIME_ZONE)
    plan = (plan_morning if query.window == "morning" else plan_evening)(query, track)
    if isinstance(plan, Answer):
        return None
    start = plan.start
    if query.window == "evening":
        start = max(start, plan.end - EVENING_CLOUD_SPAN_MIN)
    day = track.times[0]
    return day + pd.Timedelta(minutes=start), day + pd.Timedelta(minutes=plan.end)


def cloud_category(c: float) -> Sky:
    """Clear below 25 %, overcast from 80 %, partly cloudy between."""
    if c < CLEAR_BELOW_PCT:
        return "clear"
    if c < OVERCAST_FROM_PCT:
        return "partly"
    return "overcast"


def mean_cloud_cover(
    response: dict[str, Any], start: pd.Timestamp, end: pd.Timestamp
) -> float | None:
    """`C` over [start, end] from an Open-Meteo response, or None if it does not cover the span.

    Covering means an hour at or before `start`, an hour at or after `end`,
    and a number for every hour from one to the other. A null hour (past
    the model's horizon) or a malformed response covers nothing.
    """
    hourly = response.get("hourly")
    if not isinstance(hourly, dict):
        return None
    times, values = hourly.get("time"), hourly.get("cloud_cover")
    if not isinstance(times, list) or not isinstance(values, list) or len(times) != len(values):
        return None
    s, e = start.timestamp(), end.timestamp()
    first = next(
        (i for i in range(len(times) - 1, -1, -1) if _number(times[i]) and times[i] <= s), None
    )
    last = next((j for j in range(len(times)) if _number(times[j]) and times[j] >= e), None)
    if first is None or last is None or not s < e:
        return None
    hours = range(first, last + 1)
    if not all(_number(times[k]) and _number(values[k]) for k in hours):
        return None
    if any(times[k + 1] <= times[k] for k in range(first, last)):
        return None

    area = 0.0
    for k in range(first, last):
        t0, t1, v0, v1 = times[k], times[k + 1], values[k], values[k + 1]
        a, b = max(t0, s), min(t1, e)
        if b <= a:
            continue
        va = v0 + (v1 - v0) * (a - t0) / (t1 - t0)
        vb = v0 + (v1 - v0) * (b - t0) / (t1 - t0)
        area += (b - a) * (va + vb) / 2
    return float(area / (e - s))


def forecast_coordinate(lat: float, lon: float) -> tuple[str, str]:
    """The coordinate sent with the forecast request: rounded to 0.05 degrees, to 2 decimals.

    Halves round up (towards +inf), as JS `Math.round` does.
    """

    def snap(x: float) -> str:
        return f"{math.floor(x * FORECAST_CELLS_PER_DEG + 0.5) / FORECAST_CELLS_PER_DEG:.2f}"

    return snap(lat), snap(lon)


def _number(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
