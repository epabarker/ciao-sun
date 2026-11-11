"""Candidate generation, scoring, and ranking of sunrise viewpoints.

No command calls this since `find` and `compare` were removed. It is kept, with
its tests, as prior art for the Stage 1 reference scorer, which replaces it.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ciao_sun.horizon import horizon_angle, meridian_convergence, ray_samples
from ciao_sun.raster import RasterGrid, sample
from ciao_sun.solar import SunTrack


@dataclass(frozen=True)
class SearchResult:
    x: np.ndarray  # BNG easting, m
    y: np.ndarray  # BNG northing, m
    distance_m: np.ndarray  # straight-line distance from home, m
    fraction_clear: np.ndarray  # fraction of the hour's time steps clear
    worst_horizon_angle: np.ndarray  # deg; the candidate's max obstruction angle across the track
    clear_mask: np.ndarray  # bool, (n_candidates, n_steps): clear at each sun-track time step
    times: pd.DatetimeIndex  # the sun-track time steps clear_mask's columns correspond to


def candidate_grid(
    home_x: float, home_y: float, radius: float, spacing: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Regular grid of candidate positions within radius of home, circle-masked."""
    if spacing <= 0:
        raise ValueError("spacing must be positive")
    if radius <= 0:
        raise ValueError("radius must be positive")
    offsets = np.arange(-radius, radius + spacing, spacing)
    grid_x, grid_y = np.meshgrid(home_x + offsets, home_y + offsets)
    gx, gy = grid_x.ravel(), grid_y.ravel()
    dist = np.hypot(gx - home_x, gy - home_y)
    keep = dist <= radius
    return gx[keep], gy[keep], dist[keep]


def score_candidates(
    dsm: RasterGrid,
    dtm: RasterGrid,
    home_x: float,
    home_y: float,
    radius: float,
    spacing: float,
    eye_height: float,
    sun_track: SunTrack,
    max_ray: float,
    curvature: bool = True,
    chunk_size: int = 4000,
) -> SearchResult:
    """Score every candidate position against every step of the sun track.

    A candidate "passes" a time step when the horizon angle along the sun's
    azimuth is below its apparent elevation. The sun track's azimuths are true
    azimuths; the meridian convergence at home converts them for the whole
    area of interest. Scoring is chunked over candidates with the ray casting
    fully vectorised across each chunk.
    """
    gx, gy, dist = candidate_grid(home_x, home_y, radius, spacing)

    # Observer stands on bare earth (DTM), never on the DSM surface -- otherwise
    # candidates get placed on rooftops and in tree canopies.
    ground = sample(dtm, gx, gy)
    valid = np.isfinite(ground)
    gx, gy, dist, ground = gx[valid], gy[valid], dist[valid], ground[valid]
    if len(gx) == 0:
        raise ValueError(
            "No candidate positions have valid DTM coverage in this area of "
            "interest. Check the DTM tiles cover home +/- radius."
        )
    gz = ground + eye_height

    ray_d = ray_samples(max_ray)
    convergence = meridian_convergence(home_x, home_y)
    n_steps = len(sun_track.azimuth)
    n_clear = np.zeros(len(gx), dtype=np.int32)
    worst_angle = np.full(len(gx), -90.0, dtype=np.float32)
    clear_mask = np.zeros((len(gx), n_steps), dtype=bool)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN (slice|axis) encountered")
        for start in range(0, len(gx), chunk_size):
            sl = slice(start, start + chunk_size)
            px, py, pz = gx[sl], gy[sl], gz[sl]
            tally = np.zeros(len(px), dtype=np.int32)
            chunk_worst = np.full(len(px), -90.0, dtype=np.float32)
            for step, (az, el) in enumerate(
                zip(sun_track.azimuth, sun_track.apparent_elevation, strict=True)
            ):
                ang = horizon_angle(
                    dsm, px, py, pz, az, ray_d, convergence_deg=convergence, curvature=curvature
                )
                step_clear = ang < el
                tally += step_clear
                clear_mask[sl, step] = step_clear
                chunk_worst = np.fmax(chunk_worst, np.nan_to_num(ang, nan=90.0))
            n_clear[sl] = tally
            worst_angle[sl] = chunk_worst

    fraction_clear = n_clear / n_steps
    return SearchResult(
        x=gx,
        y=gy,
        distance_m=dist,
        fraction_clear=fraction_clear,
        worst_horizon_angle=worst_angle,
        clear_mask=clear_mask,
        times=sun_track.times,
    )


def passing_mask(result: SearchResult, pass_fraction: float) -> np.ndarray:
    """Candidates clear for at least `pass_fraction` of the hour's time steps."""
    return result.fraction_clear >= pass_fraction - 1e-9


def longest_clear_run(clear_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each row, the length (in steps) and [start, end] step indices of the
    longest run of consecutive True values. Rows with no True value get length 0
    and start = end = -1.
    """
    n, m = clear_mask.shape
    run_len = np.zeros((n, m), dtype=np.int32)
    run_len[:, 0] = clear_mask[:, 0]
    for j in range(1, m):
        run_len[:, j] = np.where(clear_mask[:, j], run_len[:, j - 1] + 1, 0)

    max_len = run_len.max(axis=1)
    end_idx = run_len.argmax(axis=1)  # last step of the (first) longest run
    start_idx = end_idx - max_len + 1
    no_run = max_len == 0
    start_idx[no_run] = -1
    end_idx[no_run] = -1
    return max_len, start_idx, end_idx


def clear_window_minutes(result: SearchResult) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per candidate: (duration_minutes, start_step_idx, end_step_idx) of the
    longest unbroken clear window. duration_minutes is 0 and the indices are -1
    where no step is clear at all; a single isolated clear step also has
    duration 0 (there is no second timestamp to span), even though max_len is 1.

    Duration is measured between the first and last clear *sample* timestamp,
    so it is a lower bound resolved to the sun track's step size -- a real
    window between two clear samples spaced `step_minutes` apart could be
    longer or (rarely, near a marginal obstruction) shorter than reported.
    """
    max_len, start_idx, end_idx = longest_clear_run(result.clear_mask)
    duration_minutes = np.zeros(len(max_len), dtype="float64")
    has_run = max_len > 0
    times = result.times
    start_ts = times[start_idx[has_run]]
    end_ts = times[end_idx[has_run]]
    duration_minutes[has_run] = (end_ts - start_ts).total_seconds() / 60.0
    return duration_minutes, start_idx, end_idx


def passing_mask_duration(duration_minutes: np.ndarray, min_clear_minutes: float) -> np.ndarray:
    """Candidates with an unbroken clear window of at least min_clear_minutes."""
    return duration_minutes >= min_clear_minutes - 1e-9

