"""Horizon ray-casting correctness: HANDOFF.md #6, test groups 1-3."""

from __future__ import annotations

import numpy as np
import pytest

from sunspot.horizon import R_EFF, curvature_drop, horizon_angle, ray_samples

EYE_HEIGHT = 1.6


def test_flat_plane_horizon_matches_analytic_formula(flat_grid_factory):
    """Group 1: flat DSM. Horizon angle at every azimuth is the analytic max of
    atan2(-eye_height - drop, d) over the sampled ray, slightly negative, within
    0.01 degrees.
    """
    grid = flat_grid_factory(value=0.0, xmin=-600.0, ymax=600.0, width=1200, height=1200)
    pz = np.array([EYE_HEIGHT])
    px = np.array([0.0])
    py = np.array([0.0])
    ray_d = ray_samples(500.0)
    expected = np.degrees(np.arctan2(-EYE_HEIGHT - curvature_drop(ray_d), ray_d)).max()

    for az in [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0, 17.3]:
        result = horizon_angle(grid, px, py, pz, az, ray_d)[0]
        assert result < 0.0, f"azimuth {az}: expected slightly negative, got {result}"
        assert abs(result - expected) < 0.01, f"azimuth {az}: {result} vs analytic {expected}"


def test_single_wall_10m_at_100m_azimuth_90(flat_grid_factory):
    """Group 2: a 10 m rise at exactly 100 m along azimuth 90, flat elsewhere.

    Expected angle degrees(atan2(10 - eye_height - drop, 100)) ~= 4.80 degrees,
    within 0.02 degrees. Azimuth 270 (opposite direction) must be unaffected.
    """
    from rasterio.transform import rowcol

    grid = flat_grid_factory(value=0.0, xmin=-160.0, ymax=60.0, width=420, height=120)
    row, col = rowcol(grid.transform, [100.0], [0.0])
    grid.data[row[0], col[0]] = 10.0

    px, py, pz = np.array([0.0]), np.array([0.0]), np.array([EYE_HEIGHT])
    ray_d = ray_samples(150.0)
    assert 100.0 in ray_d

    drop_100 = 100.0**2 / (2.0 * R_EFF)
    expected = np.degrees(np.arctan2(10.0 - EYE_HEIGHT - drop_100, 100.0))
    assert expected == pytest.approx(4.80, abs=0.05)  # per HANDOFF.md worked example

    result_east = horizon_angle(grid, px, py, pz, 90.0, ray_d)[0]
    assert abs(result_east - expected) < 0.02

    result_west = horizon_angle(grid, px, py, pz, 270.0, ray_d)[0]
    flat_expected = np.degrees(np.arctan2(-EYE_HEIGHT - curvature_drop(ray_d), ray_d)).max()
    assert abs(result_west - flat_expected) < 0.01
    assert result_west < result_east - 1.0


def test_curvature_strictly_reduces_distant_obstruction_angle(flat_grid_factory):
    """Group 3: with curvature enabled, a distant obstacle's angle must be
    strictly less than with it disabled. Guards against a sign error.
    """
    from rasterio.transform import rowcol

    grid = flat_grid_factory(value=0.0, xmin=-10.0, ymax=2100.0, width=20, height=2200)
    row, col = rowcol(grid.transform, [0.0], [2000.0])
    grid.data[row[0], col[0]] = 50.0

    px, py, pz = np.array([0.0]), np.array([0.0]), np.array([EYE_HEIGHT])
    ray_d = ray_samples(2500.0)
    assert 2000.0 in ray_d

    angle_curved = horizon_angle(grid, px, py, pz, 0.0, ray_d, curvature=True)[0]
    angle_flat = horizon_angle(grid, px, py, pz, 0.0, ray_d, curvature=False)[0]
    assert angle_curved < angle_flat
