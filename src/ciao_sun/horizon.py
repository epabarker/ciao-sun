"""Vectorised horizon (obstruction-angle) ray casting.

Azimuths in and out of this module are *true* azimuths (degrees clockwise from
true north), the same convention as pvlib's sun azimuth, so a Horizon profile
can be compared with the sun directly. Rays, though, are stepped through the
EPSG:27700 grid, whose north differs from true north by the meridian
convergence (about -0.47 deg in Bristol, several degrees in west Scotland). The one
place that converts between the two is `grid_azimuth`; nothing else should
correct for it.

For an observer at (px, py, pz) and a grid azimuth theta, the obstruction angle
at ray distance d is:

    x_s = px + d * sin(theta)
    y_s = py + d * cos(theta)
    drop = d**2 / (2 * R_eff)                  # earth curvature + standard refraction
    angle = atan2(DSM(x_s, y_s) - pz - drop, d)

and the horizon angle for that azimuth is max(angle) over all sampled d.
"""

from __future__ import annotations

import numpy as np
from pyproj import Proj

from ciao_sun.crs import BNG_TO_WGS84
from ciao_sun.raster import RasterGrid, sample

_BNG = Proj("EPSG:27700")

# The Earth radius the rays' curvature drop uses (with refraction, R_EFF); not the
# lat/lon distances' DISTANCE_EARTH_RADIUS_M (`ciao_sun.reference.world`).
CURVATURE_EARTH_RADIUS_M = 6371000.0
STANDARD_REFRACTION_COEFF = 1.13
R_EFF = CURVATURE_EARTH_RADIUS_M * STANDARD_REFRACTION_COEFF

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


def meridian_convergence(x: float, y: float) -> float:
    """Meridian convergence (deg) of EPSG:27700 at easting/northing (x, y).

    The angle from true north to grid north, as pyproj reports it: negative west
    of BNG's 2 deg W central meridian, positive east of it. It varies by only a
    few hundredths of a degree across an area of interest a few km wide, so
    callers compute it once per area of interest, not per Candidate.

    The factors are evaluated at the point's WGS84 lon/lat, not its OSGB36
    lon/lat, because the sun's true north (pvlib) is WGS84 north. In Bristol
    the two differ by ~0.001 deg; the WGS84 value matches the grid bearing of
    a WGS84 meridian to ~0.0002 deg.
    """
    lon, lat = BNG_TO_WGS84.transform(x, y)
    return float(_BNG.get_factors(lon, lat).meridian_convergence)


def grid_azimuth(true_azimuth_deg: float, convergence_deg: float) -> float:
    """The EPSG:27700 grid azimuth (deg) of a true azimuth, given the local convergence."""
    return (true_azimuth_deg - convergence_deg) % 360.0


def horizon_angle(
    dsm: RasterGrid,
    px: np.ndarray,
    py: np.ndarray,
    pz: np.ndarray,
    true_azimuth_deg: float,
    ray_d: np.ndarray,
    *,
    convergence_deg: float,
    curvature: bool = True,
) -> np.ndarray:
    """Max obstruction angle (deg) along one true azimuth, for many observer points at once.

    px, py: observer easting/northing (m, EPSG:27700). pz: observer eye elevation
    (m AOD). true_azimuth_deg: a single azimuth, clockwise from true north,
    shared by every observer point. convergence_deg: the meridian convergence
    for these observers, from `meridian_convergence`; required so that no
    caller can cast a true azimuth along the grid by mistake. Pass 0.0 only for
    a synthetic grid on which true and grid north are defined to coincide.
    Returns one angle per observer point; NaN where the whole ray falls off the
    DSM grid (treated as a fail by callers, since nothing is confirmed clear).
    """
    return horizon_ridge(
        dsm, px, py, pz, true_azimuth_deg, ray_d,
        convergence_deg=convergence_deg, curvature=curvature,
    )[0]  # fmt: skip


def horizon_ridge(
    dsm: RasterGrid,
    px: np.ndarray,
    py: np.ndarray,
    pz: np.ndarray,
    true_azimuth_deg: float,
    ray_d: np.ndarray,
    *,
    convergence_deg: float,
    curvature: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`horizon_angle`, plus where the cell that sets each angle is.

    Returns (angle, ridge easting, ridge northing), one of each per observer
    point. The ridge is the first sample along the ray at the maximum angle;
    all three are NaN where the whole ray falls off the grid.
    """
    theta = np.radians(grid_azimuth(true_azimuth_deg, convergence_deg))
    xs = px[:, None] + ray_d[None, :] * np.sin(theta)
    ys = py[:, None] + ray_d[None, :] * np.cos(theta)
    zs = sample(dsm, xs.ravel(), ys.ravel()).reshape(xs.shape)
    drop = curvature_drop(ray_d, curvature)
    rise = zs - pz[:, None] - drop[None, :]
    angle = np.degrees(np.arctan2(rise, ray_d[None, :]))
    ridge = np.where(np.isnan(angle), -np.inf, angle).argmax(axis=1)
    rows = np.arange(len(px))
    best = angle[rows, ridge]
    no_data = np.isnan(best)
    return (
        best,
        np.where(no_data, np.nan, xs[rows, ridge]),
        np.where(no_data, np.nan, ys[rows, ridge]),
    )
