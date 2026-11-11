"""Horizon profile precompute: near-field rays, far-field lattice, and their merge.

For every Candidate of a tile this produces the f1 Horizon profile: 1,440
storage codes, sample i at true azimuth i * 0.25 deg. The true-north conversion
(`grid_az = true_az - convergence`) happens here, at cast time, so nothing
downstream ever sees grid north.

Near field: rays from the Candidate's eye (1.6 m above the DTM) over the
crown-envelope surface out to 3 km, with Earth curvature and standard
refraction and the variable-density sampling of `horizon.ray_samples`.

Far field: OS Terrain 50 from 3 km out to 50 km (never beyond 100 km). It is
not cast per Candidate. Each Candidate takes the nearest point of a 100 m
lattice on the National Grid, the far horizon is cast once per lattice point,
and each Candidate's own eye height is then corrected for at the distance of
the ridge that sets it:

    far = lattice_far - degrees((eye - lattice_eye) / ridge_distance)

Measured on Bristol (prototype/horizon-cost), this is within 0.035 deg (p99) of
a per-Candidate far ray. Where Terrain 50 has no data along a whole ray (open
sea beyond the grid) there is no far obstruction.

The two are merged as `max(near, far)`, so a tile holds one profile per
Candidate.

A build casts one tile at a time; `precompute_tiles` spreads the tiles over
processes.
"""

from __future__ import annotations

import multiprocessing
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import TypeVar

import numpy as np
import numpy.typing as npt

from ciao_sun.horizon import (
    curvature_drop,
    grid_azimuth,
    horizon_angle,
    meridian_convergence,
    ray_samples,
)
from ciao_sun.raster import RasterGrid, sample, sample_bilinear
from ciao_sun.tile_codec import PROFILE_SAMPLES, degrees_to_codes

EYE_HEIGHT_M = 1.6
NEAR_REACH_M = 3000.0
FAR_REACH_M = 50_000.0
FAR_REACH_CAP_M = 100_000.0
FAR_LATTICE_M = 100.0
# True azimuth of each profile sample, degrees clockwise from true north.
PROFILE_AZIMUTHS_DEG = np.arange(PROFILE_SAMPLES) * (360.0 / PROFILE_SAMPLES)

_CHUNK = 2000

T = TypeVar("T")


@dataclass(frozen=True, eq=False)
class TileWorld:
    """Everything one tile's Horizon profiles are computed from, in EPSG:27700.

    `surface` is the crown-envelope obstruction surface (`surface.py`) and
    `dtm` the bare earth the Candidates stand on; both must reach 3 km beyond
    the Candidates. `terrain50` is OS Terrain 50 in metres. `x`, `y` are the
    Candidates' eastings and northings.
    """

    surface: RasterGrid
    dtm: RasterGrid
    terrain50: RasterGrid
    x: npt.NDArray[np.float64]
    y: npt.NDArray[np.float64]


def _eye_elevations(world: TileWorld) -> npt.NDArray[np.float64]:
    ground = sample(world.dtm, world.x, world.y).astype(np.float64)
    if not np.isfinite(ground).all():
        raise ValueError("every Candidate must stand on a DTM cell that has data")
    return ground + EYE_HEIGHT_M


def _near_field(
    world: TileWorld, eye: npt.NDArray[np.float64], convergence: float
) -> npt.NDArray[np.float64]:
    ray_d = ray_samples(NEAR_REACH_M)
    out = np.empty((len(world.x), PROFILE_SAMPLES), dtype=np.float64)
    for start in range(0, len(world.x), _CHUNK):
        rows = slice(start, start + _CHUNK)
        for i, azimuth in enumerate(PROFILE_AZIMUTHS_DEG):
            out[rows, i] = horizon_angle(
                world.surface,
                world.x[rows],
                world.y[rows],
                eye[rows],
                float(azimuth),
                ray_d,
                convergence_deg=convergence,
            )
    if np.isnan(out).any():
        raise ValueError(
            "a near-field ray found no surface data at all; the obstruction surface "
            "must cover every Candidate"
        )
    return out


def _far_distances(reach: float) -> npt.NDArray[np.float64]:
    """Far-field sample distances: one per Terrain 50 cell to 10 km, sparser beyond.

    Against twice this density the far horizon moves by 0.014 deg at p99
    (prototype/horizon-cost).
    """
    d = np.concatenate(
        [
            np.arange(NEAR_REACH_M, 10_000.0, 50.0),
            np.arange(10_000.0, 30_000.0, 100.0),
            np.arange(30_000.0, FAR_REACH_CAP_M, 250.0),
        ]
    )
    return d[d < reach]


def _far_field(
    world: TileWorld, eye: npt.NDArray[np.float64], convergence: float, reach: float
) -> npt.NDArray[np.float64]:
    """The far horizon per Candidate and sample; -inf where Terrain 50 shows nothing."""
    # The lattice is anchored to the National Grid, not to the tile, so a
    # Candidate gets the same lattice point whichever tile or run computes it.
    nearest = np.column_stack(
        [
            np.round(world.x / FAR_LATTICE_M) * FAR_LATTICE_M,
            np.round(world.y / FAR_LATTICE_M) * FAR_LATTICE_M,
        ]
    )
    points, point_of = np.unique(nearest, axis=0, return_inverse=True)
    point_of = point_of.ravel()
    # The lattice ray is cast from the mean eye of the Candidates it serves,
    # which keeps each Candidate's correction small.
    lattice_eye = np.bincount(point_of, weights=eye) / np.bincount(point_of)

    d = _far_distances(reach)
    drop = curvature_drop(d)
    every_point = np.arange(len(points))
    angle = np.empty((len(points), PROFILE_SAMPLES), dtype=np.float64)
    ridge_distance = np.empty_like(angle)
    for i, azimuth in enumerate(PROFILE_AZIMUTHS_DEG):
        theta = np.radians(grid_azimuth(float(azimuth), convergence))
        xs = points[:, 0, None] + d[None, :] * np.sin(theta)
        ys = points[:, 1, None] + d[None, :] * np.cos(theta)
        zs = sample_bilinear(world.terrain50, xs.ravel(), ys.ravel()).reshape(xs.shape)
        along_ray = np.degrees(np.arctan2(zs - lattice_eye[:, None] - drop[None, :], d[None, :]))
        along_ray = np.where(np.isnan(along_ray), -np.inf, along_ray)
        ridge = along_ray.argmax(axis=1)
        angle[:, i] = along_ray[every_point, ridge]
        ridge_distance[:, i] = d[ridge]

    eye_above_lattice = (eye - lattice_eye[point_of])[:, None]
    return angle[point_of] - np.degrees(eye_above_lattice / ridge_distance[point_of])


def horizon_profile_degrees(
    world: TileWorld, *, far_reach_m: float = FAR_REACH_M
) -> npt.NDArray[np.float64]:
    """Each Candidate's merged Horizon profile in degrees, shape (Candidates, 1440).

    This is the profile before the storage code rounds it. `far_reach_m` is how
    far the Terrain 50 far field looks: 50 km serves Bristol, and 100 km is the
    cap for Great Britain.
    """
    if not NEAR_REACH_M < far_reach_m <= FAR_REACH_CAP_M:
        raise ValueError(
            f"far_reach_m must be above {NEAR_REACH_M:.0f} m and at most "
            f"{FAR_REACH_CAP_M:.0f} m, got {far_reach_m}"
        )
    if len(world.x) == 0:
        return np.empty((0, PROFILE_SAMPLES), dtype=np.float64)
    eye = _eye_elevations(world)
    # One convergence per tile: it varies by ~0.01 deg across a 1 km square.
    convergence = meridian_convergence(float(world.x.mean()), float(world.y.mean()))
    near = _near_field(world, eye, convergence)
    far = _far_field(world, eye, convergence, far_reach_m)
    return np.maximum(near, far)


def horizon_profile_codes(
    world: TileWorld, *, far_reach_m: float = FAR_REACH_M
) -> npt.NDArray[np.uint8]:
    """Each Candidate's Horizon profile as f1 storage codes, ready for `tile_codec.Candidates`."""
    return degrees_to_codes(horizon_profile_degrees(world, far_reach_m=far_reach_m))


def precompute_tiles(
    grid_refs: Sequence[str], compute_tile: Callable[[str], T], *, workers: int
) -> dict[str, T]:
    """Run `compute_tile` once per tile, on `workers` processes, and collect the results.

    Tiles are independent, so the output does not depend on `workers`. Results
    come back keyed by grid ref in the order given. `compute_tile` and its
    result cross a process boundary, so it must be picklable (a module-level
    function or a `functools.partial` of one). It should load the tile's own
    rasters, cast, and write the tile itself, returning something small such
    as the tile's path; profile arrays are best not sent back to the parent.
    `workers=1` runs in this process.
    """
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if len(set(grid_refs)) != len(grid_refs):
        raise ValueError("each tile must be listed once")
    if workers == 1:
        return {grid_ref: compute_tile(grid_ref) for grid_ref in grid_refs}
    # spawn, not fork: GDAL and PROJ handles do not survive a fork.
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        return dict(zip(grid_refs, pool.map(compute_tile, grid_refs), strict=True))
