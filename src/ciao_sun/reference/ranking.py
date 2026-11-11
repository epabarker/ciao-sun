"""The deterministic ranking and the greedy de-dupe, shared by every list an Answer shows."""

from __future__ import annotations

from collections.abc import Iterable

from ciao_sun.reference.scoring import Scored
from ciao_sun.reference.world import World, distance_m

DEDUPE_RADIUS_M = 200.0
SPOTS_SHOWN = 5


def rank_by_low_sun(world: World, scored: Scored, among: Iterable[int]) -> list[int]:
    """The `among` positions of `scored`, best first.

    Low-sun minutes to 0.01 min descending, then walk in whole metres
    ascending, then candidateId ascending (grid ref, then index as a number).
    """
    return sorted(
        (int(j) for j in among),
        key=lambda j: (
            -int(scored.low_sun_hundredths[j]),
            int(scored.walk_m[j]),
            world.candidate_order(int(scored.candidates[j])),
        ),
    )


def dedupe(
    world: World, scored: Scored, ranked: Iterable[int], keep: int = SPOTS_SHOWN
) -> list[int]:
    """Greedy de-dupe of positions of `scored` given in rank order.

    Keep a Candidate; drop any later one with the same Spot name, or within
    200 m of a kept one. Stop at `keep` kept.
    """
    kept: list[int] = []
    for j in ranked:
        if len(kept) == keep:
            break
        k = int(scored.candidates[j])
        others = (int(scored.candidates[i]) for i in kept)
        if all(
            world.name[k] != world.name[other]
            and distance_m(world.lat[k], world.lon[k], world.lat[other], world.lon[other])
            > DEDUPE_RADIUS_M
            for other in others
        ):
            kept.append(j)
    return kept
