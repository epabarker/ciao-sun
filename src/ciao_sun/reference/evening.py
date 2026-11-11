"""The Evening window: its bounds, its axis and its Leave-by rule. Its minutes are unweighted."""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt
import pandas as pd

from ciao_sun.reference.contract import Answer, Query
from ciao_sun.reference.morning import morning_leave_by
from ciao_sun.reference.windows import WindowPlan, clock, minute_of, now_minute, wake_minute
from ciao_sun.solar import SunTrack

WAKE_TO_EVENING_MIN = 360  # the window starts no sooner than this long after Wake time
EVENING_AXIS_MIN = 180  # the axis covers this long before Nominal sunset


def evening_leave_by(
    in_view: npt.NDArray[np.bool_], walk_min: float, plan: WindowPlan, target_min: int
) -> int:
    """The latest departure that meets the Duration target before Last sun.

    The target is met when the walk plus the Sun minutes from arrival reach
    it, so the Sun minutes still needed are the target less the walk, rounded
    up to a whole minute, and at least 1: a walk that meets the target alone
    must still arrive for the last Sun minute, or no departure would be the
    latest. Arrival is the minute that leaves exactly that many Sun minutes
    in the window, and the walk before it is rounded up to whole minutes.

    If that departure is before Wake time or now, or the window holds too
    few Sun minutes, no departure meets the target: the morning rule applies.
    """
    needed = max(math.ceil(target_min - walk_min), 1)
    sun = np.flatnonzero(in_view)
    if sun.size >= needed:
        leave = plan.start + int(sun[-needed]) - math.ceil(walk_min)
        if leave >= plan.earliest_leave:
            return leave
    return morning_leave_by(in_view, walk_min, plan, target_min)


def plan_evening(query: Query, track: SunTrack) -> WindowPlan | Answer:
    wake = wake_minute(query, track)
    now = now_minute(query, track)
    earliest_leave = wake if now is None else max(wake, now)
    if track.nominal_sunset is None:
        return _no_evening_window(track)
    end = minute_of(track, track.nominal_sunset)
    unclipped_start = max(minute_of(track, track.solar_noon), wake + WAKE_TO_EVENING_MIN)
    start = max(unclipped_start, earliest_leave)
    if start >= end:
        return _no_evening_window(track)

    return WindowPlan(
        start=start,
        end=end,
        unclipped_start=unclipped_start,
        axis_start=max(end - EVENING_AXIS_MIN, 0),
        axis_end=end,
        earliest_leave=earliest_leave,
        weight_numerators=np.ones(end - start, dtype=np.int64),
        weight_denominator=1,
        leave_by=evening_leave_by,
        reports_last_sun=True,
    )


def _no_evening_window(track: SunTrack) -> Answer:
    """The window would not start before Nominal sunset: the no-evening-window Answer.

    It has no window, spots or Duration target, only the day's sun events.
    """

    def event(when: pd.Timestamp | None) -> str | None:
        return None if when is None else clock(track, minute_of(track, when))

    return Answer(
        status="no-evening-window",
        nominal_sunrise=event(track.nominal_sunrise),
        nominal_sunset=event(track.nominal_sunset),
        solar_noon=event(track.solar_noon),
    )
