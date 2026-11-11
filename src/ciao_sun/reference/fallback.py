"""The fallback: what an Answer lists when the sky is overcast or no reachable spot has sun.

It works on any window's plan, Morning or Evening: it needs only the window's
start and, for the spot beyond the limit, the window's own Leave-by rule.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import replace

import numpy as np

from ciao_sun.reference.contract import Spot
from ciao_sun.reference.ranking import dedupe
from ciao_sun.reference.scoring import Scored, build_spot, walk_minutes
from ciao_sun.reference.windows import WindowPlan
from ciao_sun.reference.world import World
from ciao_sun.solar import SunTrack


def rank_by_walk(world: World, scored: Scored, among: Iterable[int]) -> list[int]:
    """The `among` positions of `scored`, nearest first.

    Walk in whole metres ascending, then candidateId ascending (grid ref, then
    index as a number).
    """
    return sorted(
        (int(j) for j in among),
        key=lambda j: (int(scored.walk_m[j]), world.candidate_order(int(scored.candidates[j]))),
    )


def stay_minutes(target_min: int, walk_min: float) -> int:
    """The fallback "stay N min": the Duration target less the walk, never below 0.

    Rounded up to a whole minute, as the Sun minutes an evening Leave-by still
    needs are, so that walk + stay always reaches the target.
    """
    return max(math.ceil(target_min - walk_min), 0)


def fallback_spots(
    world: World, track: SunTrack, plan: WindowPlan, scored: Scored, target_min: int
) -> tuple[Spot, ...]:
    """The nearest reachable spots that pass openness, de-duped, whatever their sun.

    Each is left for at the start of the window and says how long to stay:
    the walk counts towards the Duration target, so the stay is `stay_minutes`.
    Its sun fields are still the geometry's, as on a ranked spot.
    """
    nearest = rank_by_walk(world, scored, np.flatnonzero(scored.reachable))
    return tuple(
        replace(
            build_spot(world, track, plan, scored, j, plan.start, target_min),
            stay_min=stay_minutes(target_min, walk_minutes(scored, j)),
        )
        for j in dedupe(world, scored, nearest)
    )


def nearest_sun_beyond_limit(
    world: World, track: SunTrack, plan: WindowPlan, scored: Scored, target_min: int
) -> Spot | None:
    """The nearest spot with Sun minutes beyond max walk, within the 20 min cap.

    Nearest by `rank_by_walk`. It is a spot with sun, so it is left for by the
    window's own Leave-by rule and has no "stay N min". None when there is none.
    """
    beyond = np.flatnonzero(~scored.reachable & (scored.sun_minutes > 0))
    if beyond.size == 0:
        return None
    j = rank_by_walk(world, scored, beyond)[0]
    leave = plan.leave_by(scored.in_view[j], walk_minutes(scored, j), plan, target_min)
    return build_spot(world, track, plan, scored, j, leave, target_min)
