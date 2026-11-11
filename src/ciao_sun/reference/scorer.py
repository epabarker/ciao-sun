"""`(Query, tiles) -> Answer`: the reference for the scoring rules of spec #27.

The JS client is canonical (ADR 0001); this is the reference its golden
fixtures come from. The rules live beside it:

- `windows`, `morning`, `evening`: the window, its weights and its Leave-by rule
- `sunview`: sun in view, the 0-30 degree band, Sky openness
- `world`: tiles joined into one walk graph; the origin snap and the walk
- `scoring`: per-Candidate scores, and a scored Candidate as a Spot
- `ranking`: the deterministic order and the de-dupe
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd

from ciao_sun.reference.contract import Answer, Query, Sky, Spot, Status, Window, WindowName
from ciao_sun.reference.evening import plan_evening
from ciao_sun.reference.morning import plan_morning
from ciao_sun.reference.ranking import dedupe, rank_by_low_sun
from ciao_sun.reference.scoring import build_spot, score, walk_minutes
from ciao_sun.reference.windows import TIME_ZONE, WindowPlan, clock, minute_of
from ciao_sun.reference.world import join_tiles
from ciao_sun.solar import SunTrack, sun_track
from ciao_sun.tile_codec import Tile

DURATION_TARGET_MIN: dict[Sky, int] = {"clear": 10, "partly": 20, "overcast": 30}

# A planner returns the query's window, or the whole Answer when there is no
# window to rank in (lamp-only, no-evening-window).
Planner = Callable[[Query, SunTrack], WindowPlan | Answer]
PLANNERS: dict[WindowName, Planner] = {"morning": plan_morning, "evening": plan_evening}


def answer(query: Query, tiles: Sequence[Tile]) -> Answer:
    """The Answer to a Query over built tiles (read them with `load_tiles`)."""
    if query.window not in PLANNERS:
        raise NotImplementedError(f"the {query.window} window is not built yet (ticket #39)")
    track = sun_track(query.origin_lat, query.origin_lon, query.date, tz=TIME_ZONE)
    plan = PLANNERS[query.window](query, track)
    if isinstance(plan, Answer):
        return plan

    world = join_tiles(tiles)
    scored = score(world, query, track, plan)
    target_min = DURATION_TARGET_MIN[query.sky]

    sunny = np.flatnonzero(scored.reachable & (scored.sun_minutes > 0))
    if query.sky == "overcast" or sunny.size == 0:
        raise NotImplementedError("the fallback Answer is ticket #40")

    spots = []
    for j in dedupe(world, scored, rank_by_low_sun(world, scored, sunny)):
        leave = plan.leave_by(scored.in_view[j], walk_minutes(scored, j), plan, target_min)
        spots.append(build_spot(world, track, plan, scored, j, leave, target_min))
    return windowed_answer("ranked", tuple(spots), query, track, plan)


def windowed_answer(
    status: Status, spots: tuple[Spot, ...], query: Query, track: SunTrack, plan: WindowPlan
) -> Answer:
    """An Answer that has a window, with the fields every such Answer carries."""

    def event(when: pd.Timestamp | None) -> str | None:
        return None if when is None else clock(track, minute_of(track, when))

    return Answer(
        status=status,
        spots=spots,
        window=Window(
            start=clock(track, plan.start),
            end=clock(track, plan.end),
            axis_start=clock(track, plan.axis_start),
            axis_end=clock(track, plan.axis_end),
        ),
        nominal_sunrise=event(track.nominal_sunrise),
        nominal_sunset=event(track.nominal_sunset),
        solar_noon=event(track.solar_noon),
        duration_target_min=DURATION_TARGET_MIN[query.sky],
    )
