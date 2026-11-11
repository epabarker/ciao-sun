"""What the Morning window and the Evening window have in common.

Times inside the scorer are **minutes**: whole minutes since local midnight
of the query date, which are also indexes into the day's sun track. A window
holds the minutes from `start` up to, not including, `end`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from ciao_sun.reference.contract import Query
from ciao_sun.solar import SunTrack

TIME_ZONE = "Europe/London"

# (sun in view at each minute of the window, walk in minutes, the plan, Duration target)
# -> the minute to leave by. Only called for a spot with Sun minutes.
LeaveByRule = Callable[[npt.NDArray[np.bool_], float, "WindowPlan", int], int]


@dataclass(frozen=True, eq=False)
class WindowPlan:
    """One query's window, and the rules that differ between morning and evening."""

    start: int
    end: int
    # The window before `now` clips it. Sky openness is taken over this one's
    # sun path, so a Candidate's openness does not change as the morning goes on.
    unclipped_start: int
    axis_start: int
    axis_end: int
    earliest_leave: int  # leave-by is never before this
    # Low-sun minutes weigh minute `start + i` by weight_numerators[i] / weight_denominator.
    # Integers, so the ranking key is exact in any language.
    weight_numerators: npt.NDArray[np.int64]
    weight_denominator: int
    leave_by: LeaveByRule
    reports_last_sun: bool = False  # evening: each Spot carries its Last sun


def minute_of(track: SunTrack, when: pd.Timestamp) -> int:
    """The minute of the track's day at or after `when`."""
    seconds = float((when - track.times[0]).total_seconds())
    return math.ceil(seconds / 60.0)


def clock(track: SunTrack, minute: int) -> str:
    """The Answer's string for a minute of the track's day."""
    return str((track.times[0] + pd.Timedelta(minutes=minute)).isoformat())


def wake_minute(query: Query, track: SunTrack) -> int:
    return minute_of(track, pd.Timestamp(f"{query.date} {query.wake_time}", tz=track.times.tz))


def now_minute(query: Query, track: SunTrack) -> int | None:
    """`now` as a minute of the query date, or None when it is absent or on another day."""
    if query.now is None:
        return None
    now = pd.Timestamp(query.now)
    zone = track.times.tz
    local: pd.Timestamp = now.tz_localize(zone) if now.tzinfo is None else now.tz_convert(zone)
    if local.strftime("%Y-%m-%d") != query.date:
        return None
    return minute_of(track, local)
