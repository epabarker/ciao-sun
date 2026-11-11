"""The Morning window: its bounds, its taper and its Leave-by rule."""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from ciao_sun.reference.contract import Answer, Query
from ciao_sun.reference.windows import WindowPlan, minute_of, now_minute, wake_minute
from ciao_sun.solar import SunTrack

MORNING_WINDOW_MIN = 180  # the window ends this long after Wake time
FULL_WEIGHT_MIN = 60  # weight 1 until this long after Wake time, then linear to 0 at the end


def morning_leave_by(
    in_view: npt.NDArray[np.bool_], walk_min: float, plan: WindowPlan, target_min: int
) -> int:
    """Arrive as the sun appears: the first sun interval's start minus the walk.

    The walk is rounded up to whole minutes. Never before Wake time or now.
    """
    first_sun = plan.start + int(np.argmax(in_view))
    return max(first_sun - math.ceil(walk_min), plan.earliest_leave)


def plan_morning(query: Query, track: SunTrack) -> WindowPlan | Answer:
    wake = wake_minute(query, track)
    now = now_minute(query, track)
    end = min(wake + MORNING_WINDOW_MIN, len(track.times))
    earliest_leave = wake if now is None else max(wake, now)
    if track.nominal_sunrise is None:
        return _no_daylight(query, track)
    unclipped_start = max(wake, minute_of(track, track.nominal_sunrise))
    start = max(unclipped_start, earliest_leave)
    if start >= end:
        return _no_daylight(query, track)

    since_wake = np.arange(start, end, dtype=np.int64) - wake
    taper_min = MORNING_WINDOW_MIN - FULL_WEIGHT_MIN
    return WindowPlan(
        start=start,
        end=end,
        unclipped_start=unclipped_start,
        axis_start=earliest_leave,
        axis_end=end,
        earliest_leave=earliest_leave,
        weight_numerators=np.minimum(taper_min, MORNING_WINDOW_MIN - since_wake),
        weight_denominator=taper_min,
        leave_by=morning_leave_by,
    )


def _no_daylight(query: Query, track: SunTrack) -> Answer:
    """The Morning window holds no daylight: the lamp-only Answer."""
    raise NotImplementedError("the lamp-only Answer is ticket #40")
