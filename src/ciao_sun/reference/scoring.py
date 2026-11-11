"""Scoring every Candidate that could be shown, and turning one into a Spot."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ciao_sun.reference.contract import MAX_WALK_CAP_MIN, Interval, Query, Spot
from ciao_sun.reference.sunview import (
    OPENNESS_CUTOFF,
    last_sun,
    low_sun,
    runs,
    sky_openness,
    sun_in_view,
)
from ciao_sun.reference.windows import WindowPlan, clock
from ciao_sun.reference.world import WALK_SPEED_M_PER_MIN, World, walk_metres
from ciao_sun.solar import SunTrack


@dataclass(frozen=True, eq=False)
class Scored:
    """The Candidates within the 20 min walk cap whose Sky openness passes the cut-off.

    Element `j` of every array is the same Candidate, `world` index `candidates[j]`.
    Candidates beyond the query's max walk are included (`reachable` is False),
    because a fallback may name the nearest sun beyond the limit.
    """

    candidates: npt.NDArray[np.int64]
    walk_m: npt.NDArray[np.int64]
    reachable: npt.NDArray[np.bool_]  # within the query's max walk
    sky_openness: npt.NDArray[np.float64]
    in_view: npt.NDArray[np.bool_]  # (Candidates, window minutes)
    low: npt.NDArray[np.bool_]  # (window minutes,): the sun is at 0-30 degrees
    sun_minutes: npt.NDArray[np.int64]
    low_sun_hundredths: npt.NDArray[np.int64]  # Low-sun minutes x 100, rounded half up


def score(world: World, query: Query, track: SunTrack, plan: WindowPlan) -> Scored:
    cap_m = MAX_WALK_CAP_MIN * WALK_SPEED_M_PER_MIN
    walks = walk_metres(world, query.origin_lat, query.origin_lon, cap_m)
    near = np.flatnonzero(walks >= 0)
    openness = sky_openness(world.profile_codes[near], track, plan.unclipped_start, plan.end)
    shown = openness >= OPENNESS_CUTOFF
    candidates, openness = near[shown], openness[shown]

    in_view = sun_in_view(world.profile_codes[candidates], track, plan.start, plan.end)
    low = low_sun(track, plan.start, plan.end)
    weighted = (in_view & low).astype(np.int64) @ plan.weight_numerators
    denominator = plan.weight_denominator
    return Scored(
        candidates=candidates,
        walk_m=walks[candidates],
        reachable=walks[candidates] <= query.max_walk_min * WALK_SPEED_M_PER_MIN,
        sky_openness=openness,
        in_view=in_view,
        low=low,
        sun_minutes=in_view.sum(axis=1),
        low_sun_hundredths=(200 * weighted + denominator) // (2 * denominator),
    )


def walk_minutes(scored: Scored, j: int) -> float:
    """Candidate `j`'s walk in minutes: its whole metres at the walking speed."""
    return int(scored.walk_m[j]) / WALK_SPEED_M_PER_MIN


def build_spot(
    world: World,
    track: SunTrack,
    plan: WindowPlan,
    scored: Scored,
    j: int,
    leave: int,
    target_min: int,
) -> Spot:
    """Candidate `j` of `scored` as a Spot that is left for at minute `leave`.

    The Duration target is met when the walk plus the Sun minutes from arrival
    to the window's end reach it. Arrival is `leave` plus the walk rounded up
    to whole minutes.
    """
    k = int(scored.candidates[j])
    in_view = scored.in_view[j]
    walk_min = walk_minutes(scored, j)
    arrival = leave + math.ceil(walk_min)
    sun_from_arrival = int(in_view[max(arrival - plan.start, 0) :].sum())

    def intervals(mask: npt.NDArray[np.bool_]) -> tuple[Interval, ...]:
        return tuple(
            Interval(clock(track, plan.start + a), clock(track, plan.start + b))
            for a, b in runs(mask)
        )

    return Spot(
        candidate_id=world.candidate_id(k),
        name=world.name[k],
        lat=float(world.lat[k]),
        lon=float(world.lon[k]),
        walk_metres=int(scored.walk_m[j]),
        walk_min=walk_min,
        leave_by=clock(track, leave),
        sun_intervals=intervals(in_view),
        low_sun_intervals=intervals(in_view & scored.low),
        sun_minutes=int(scored.sun_minutes[j]),
        low_sun_minutes=int(scored.low_sun_hundredths[j]) / 100.0,
        sky_openness=math.floor(float(scored.sky_openness[j]) * 1000.0 + 0.5) / 1000.0,
        target_met=walk_min + sun_from_arrival >= target_min,
        last_sun=_last_sun_clock(world, track, k) if plan.reports_last_sun else None,
    )


def _last_sun_clock(world: World, track: SunTrack, k: int) -> str | None:
    minute = last_sun(world.profile_codes[k], track)
    return None if minute is None else clock(track, minute)
