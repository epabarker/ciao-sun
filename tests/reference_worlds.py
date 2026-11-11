"""Synthetic worlds for the reference scorer tests, written through the tile codec.

A world is one straight street running due east-west through the origin at
Bristol (51.45 N, 2.60 W), with Candidates standing on it. Every Candidate has
a Horizon profile drawn by hand: a flat plain, a ridge on true bearings, or a
ring of walls. The tests read the world back only through
`ciao_sun.reference.load_tiles`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from ciao_sun.reference import Query, load_tiles
from ciao_sun.tile_codec import (
    PROFILE_SAMPLES,
    Candidates,
    Tile,
    WalkGraph,
    degrees_to_codes,
    write_tile,
)

ORIGIN_LAT, ORIGIN_LON = 51.45, -2.60
_M_PER_DEG_LAT = 111_195.08
_M_PER_DEG_LON = _M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))

# A wall high enough to enclose a Candidate: cos^2(60 deg) is exactly 0.25.
WALL_DEG = 60.0


def horizon(
    base_deg: float = 0.0, ridges: tuple[tuple[float, float, float], ...] = ()
) -> npt.NDArray[np.float64]:
    """A Horizon profile: `base_deg` all round, with ridges.

    Each ridge is `(from_bearing, to_bearing, height_deg)` in true degrees,
    covering every 0.25 degree sample from one bearing to the other inclusive.
    """
    profile = np.full(PROFILE_SAMPLES, base_deg)
    for start, end, height in ridges:
        profile[round(start * 4) : round(end * 4) + 1] = height
    return profile


@dataclass(frozen=True)
class Stand:
    """One Candidate: `east_m` along the street from the origin (west is negative)."""

    east_m: float
    name: str
    profile: npt.NDArray[np.float64] = field(default_factory=horizon)
    offset_cm: int = 0


def lon_at(east_m: float) -> float:
    return ORIGIN_LON + east_m / _M_PER_DEG_LON


def lat_at(north_m: float) -> float:
    return ORIGIN_LAT + north_m / _M_PER_DEG_LAT


def _e7(degrees: list[float]) -> npt.NDArray[np.int32]:
    return np.array([round(d * 1e7) for d in degrees], dtype=np.int32)


def street_tile(
    stands: list[Stand],
    grid_ref: str = "ST5873",
    extra_nodes_east_m: tuple[float, ...] = (0.0,),
) -> Tile:
    """A tile holding the stands and the street: one node per stand, plus extras.

    A node's id is fixed by its position, so two tiles that both hold the node
    at the same place agree on its id.
    """
    easts = sorted({s.east_m for s in stands} | set(extra_nodes_east_m))
    names = sorted({s.name for s in stands})
    return Tile(
        grid_ref=grid_ref,
        names=tuple(names),
        candidates=Candidates(
            lat_e7=_e7([ORIGIN_LAT] * len(stands)),
            lon_e7=_e7([lon_at(s.east_m) for s in stands]),
            node_index=np.array([easts.index(s.east_m) for s in stands], dtype=np.uint32),
            offset_cm=np.array([s.offset_cm for s in stands], dtype=np.uint32),
            name_index=np.array([names.index(s.name) for s in stands], dtype=np.uint32),
            profile_codes=np.array(
                [degrees_to_codes(s.profile) for s in stands], dtype=np.uint8
            ).reshape(len(stands), PROFILE_SAMPLES),
        ),
        walk_graph=WalkGraph(
            node_id=np.array([1_000_000 + round(e) for e in easts], dtype=np.uint64),
            node_lat_e7=_e7([ORIGIN_LAT] * len(easts)),
            node_lon_e7=_e7([lon_at(e) for e in easts]),
            edge_from=np.arange(0, len(easts) - 1, dtype=np.uint32),
            edge_to=np.arange(1, len(easts), dtype=np.uint32),
            edge_length_cm=np.array(
                [round((b - a) * 100) for a, b in zip(easts, easts[1:], strict=False)],
                dtype=np.uint32,
            ),
        ),
    )


def build(directory: Path, *tiles: Tile) -> list[Tile]:
    """Write the tiles through the codec and read the build directory back."""
    for tile in tiles:
        write_tile(tile, directory)
    return load_tiles(directory)


def street(directory: Path, stands: list[Stand]) -> list[Tile]:
    return build(directory, street_tile(stands))


def morning(**changes: Any) -> Query:
    """A clear midwinter Morning query from the origin; override any field."""
    fields: dict[str, Any] = {
        "window": "morning",
        "date": "2026-12-21",
        "wake_time": "07:00",
        "origin_lat": ORIGIN_LAT,
        "origin_lon": ORIGIN_LON,
        "max_walk_min": 15,
        "sky": "clear",
    }
    return Query(**{**fields, **changes})
