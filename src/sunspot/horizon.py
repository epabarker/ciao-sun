"""Vectorised horizon (obstruction-angle) ray casting.

For an observer at (px, py, pz) and an azimuth theta (degrees clockwise from
grid north), the obstruction angle at ray distance d is:

    x_s = px + d * sin(theta)
    y_s = py + d * cos(theta)
    drop = d**2 / (2 * R_eff)                  # earth curvature + standard refraction
    angle = atan2(DSM(x_s, y_s) - pz - drop, d)

and the horizon angle for that azimuth is max(angle) over all sampled d.
"""

from __future__ import annotations

import warnings

import numpy as np

from sunspot.raster import RasterGrid, sample

EARTH_RADIUS_M = 6371000.0
STANDARD_REFRACTION_COEFF = 1.13
R_EFF = EARTH_RADIUS_M * STANDARD_REFRACTION_COEFF

# Variable-density ray sampling: dense near the observer where parallax matters
# most. Uniform 1 m sampling all the way to max_ray is ~14x the work for no
# accuracy gain (see HANDOFF.md #2).
_NEAR_STEP = 1.0
_NEAR_LIMIT = 200.0
_MID_STEP = 5.0
_MID_LIMIT = 1000.0
_FAR_STEP = 20.0


def ray_samples(max_ray: float) -> np.ndarray:
    """Sample distances from just beyond the observer out to max_ray."""
    if max_ray <= _NEAR_STEP:
        raise ValueError(f"max_ray must be greater than {_NEAR_STEP} m")
    if max_ray <= _NEAR_LIMIT:
        return np.arange(_NEAR_STEP, max_ray, _NEAR_STEP)
    near = np.arange(_NEAR_STEP, _NEAR_LIMIT, _NEAR_STEP)
    if max_ray <= _MID_LIMIT:
        mid = np.arange(_NEAR_LIMIT, max_ray, _MID_STEP)
        return np.concatenate([near, mid])
    mid = np.arange(_NEAR_LIMIT, _MID_LIMIT, _MID_STEP)
    far = np.arange(_MID_LIMIT, max_ray, _FAR_STEP)
    return np.concatenate([near, mid, far])


def curvature_drop(d: np.ndarray, curvature: bool = True) -> np.ndarray:
    """Earth-curvature + standard-refraction drop (m) at ray distance d."""
    if not curvature:
        return np.zeros_like(d)
    return d**2 / (2.0 * R_EFF)


def horizon_angle(
    dsm: RasterGrid,
    px: np.ndarray,
    py: np.ndarray,
    pz: np.ndarray,
    azimuth_deg: float,
    ray_d: np.ndarray,
    curvature: bool = True,
) -> np.ndarray:
    """Max obstruction angle (deg) along one azimuth, for many observer points at once.

    px, py: observer easting/northing (m, EPSG:27700). pz: observer eye elevation
    (m AOD). azimuth_deg: a single azimuth shared by every observer point.
    Returns one angle per observer point; NaN where the whole ray falls off the
    DSM grid (treated as a fail by callers, since nothing is confirmed clear).
    """
    theta = np.radians(azimuth_deg)
    xs = px[:, None] + ray_d[None, :] * np.sin(theta)
    ys = py[:, None] + ray_d[None, :] * np.cos(theta)
    zs = sample(dsm, xs.ravel(), ys.ravel()).reshape(xs.shape)
    drop = curvature_drop(ray_d, curvature)
    rise = zs - pz[:, None] - drop[None, :]
    angle = np.degrees(np.arctan2(rise, ray_d[None, :]))
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN (slice|axis) encountered")
        return np.nanmax(angle, axis=1)
