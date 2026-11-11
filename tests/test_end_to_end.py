"""End-to-end synthetic search: HANDOFF.md #6, test group 8.

A flat plain with a single ridge to the southeast: the sun sits fixed at
azimuth 135 (southeast), elevation 10 degrees. The ridge is a straight NE-SW
line (DSM raised wherever x - y >= 60), perpendicular to the sun's azimuth, so
anyone on or beyond it (x - y >= 60) looks straight into the ridge and is
blocked, while anyone clear of it on the home side is not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from affine import Affine
from rasterio.crs import CRS

from ciao_sun.raster import RasterGrid
from ciao_sun.search import passing_mask, score_candidates
from ciao_sun.solar import SunTrack

RIDGE_T = 60.0
RIDGE_HEIGHT = 2.0
SUN_AZIMUTH = 135.0
SUN_ELEVATION = 10.0


def _make_ridge_world() -> tuple[RasterGrid, RasterGrid]:
    xmin, ymax, size = -250.0, 250.0, 500
    transform = Affine(1.0, 0.0, xmin, 0.0, -1.0, ymax)
    xs = xmin + 0.5 + np.arange(size)
    ys = ymax - 0.5 - np.arange(size)
    xx, yy = np.meshgrid(xs, ys)
    dsm_data = np.where(xx - yy >= RIDGE_T, RIDGE_HEIGHT, 0.0).astype("float32")
    dtm_data = np.zeros((size, size), dtype="float32")
    crs = CRS.from_epsg(27700)
    dsm = RasterGrid(data=dsm_data, transform=transform, crs=crs)
    dtm = RasterGrid(data=dtm_data, transform=transform, crs=crs)
    return dsm, dtm


def test_positions_behind_the_ridge_are_all_blocked_and_near_side_passes():
    dsm, dtm = _make_ridge_world()
    track = SunTrack(
        times=pd.DatetimeIndex(["2026-12-21 08:00"], tz="UTC"),
        azimuth=np.array([SUN_AZIMUTH]),
        elevation=np.array([SUN_ELEVATION]),
        apparent_elevation=np.array([SUN_ELEVATION]),
        nominal_sunrise=None,
        nominal_sunset=None,
        solar_noon=pd.Timestamp("2026-12-21 12:08", tz="UTC"),
    )

    result = score_candidates(
        dsm,
        dtm,
        home_x=0.0,
        home_y=0.0,
        radius=100.0,
        spacing=10.0,
        eye_height=1.6,
        sun_track=track,
        max_ray=500.0,
        curvature=True,
    )
    mask = passing_mask(result, pass_fraction=1.0)
    assert mask.any(), "expected at least one candidate to pass on the near side"

    behind_ridge = (result.x - result.y) >= RIDGE_T
    assert not (mask & behind_ridge).any(), "no passing candidate should be behind the ridge"

    # home itself (42 m from the ridge line) must be well clear of a 2 m ridge
    # at a 10 degree sun.
    home_idx = np.argmin(np.hypot(result.x, result.y))
    assert result.x[home_idx] == 0.0 and result.y[home_idx] == 0.0
    assert mask[home_idx]
