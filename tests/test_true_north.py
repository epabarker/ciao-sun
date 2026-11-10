"""Sun azimuths are true north; ray casting must honour that (issue #15).

pvlib gives the sun's azimuth clockwise from true north, but EPSG:27700 rays
step clockwise from grid north. West of 2 deg W the two differ by the meridian
convergence (about -0.47 deg in Bristol). These tests place a narrow obstacle
on a known *true* bearing from a Candidate, independently of the code under
test: a WGS84 geodesic is walked out on that bearing with pyproj.Geod and only
then projected to BNG. The sun at that true azimuth must be blocked by it.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pyproj import Geod, Transformer
from rasterio.transform import rowcol
from typer.testing import CliRunner

from sunspot.cli import app
from sunspot.horizon import horizon_angle, meridian_convergence, ray_samples
from sunspot.raster import RasterGrid
from sunspot.search import score_candidates
from sunspot.solar import SunTrack
from tests.conftest import make_flat_grid

_WGS84_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
_BNG_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
_GEOD = Geod(ellps="WGS84")

BRISTOL_LAT, BRISTOL_LON = 51.4720, -2.6040
EYE_HEIGHT = 1.6

# The obstacle: a 3 m wide, 40 m long, 50 m tall strip centred 500 m out on a
# true bearing of 90 deg. At 500 m, 0.47 deg is ~4.1 m sideways, so a ray cast
# on the wrong north misses the strip entirely.
TRUE_BEARING = 90.0
STRIP_NEAR, STRIP_FAR = 480, 520
STRIP_HEIGHT = 50.0
SUN_ELEVATION = 2.0


def _bristol_world() -> tuple[RasterGrid, RasterGrid, float, float]:
    """Flat DSM/DTM around a Bristol Candidate, with a strip on a true bearing."""
    hx, hy = _WGS84_TO_BNG.transform(BRISTOL_LON, BRISTOL_LAT)
    hx, hy = float(round(hx)), float(round(hy))  # land on a pixel centre
    dsm = make_flat_grid(value=0.0, xmin=hx - 10.0, ymax=hy + 20.0, width=560, height=41)
    dtm = make_flat_grid(value=0.0, xmin=hx - 10.0, ymax=hy + 20.0, width=560, height=41)

    lon0, lat0 = _BNG_TO_WGS84.transform(hx, hy)
    for d in range(STRIP_NEAR, STRIP_FAR + 1):
        lon, lat, _ = _GEOD.fwd(lon0, lat0, TRUE_BEARING, float(d))
        x, y = _WGS84_TO_BNG.transform(lon, lat)
        (row,), (col,) = rowcol(dsm.transform, [x], [y])
        dsm.data[row - 1 : row + 2, col] = STRIP_HEIGHT
    return dsm, dtm, hx, hy


def _sun_at(true_azimuth: float, elevation: float) -> SunTrack:
    t = pd.Timestamp("2026-12-21 08:15", tz="Europe/London")
    return SunTrack(
        times=pd.DatetimeIndex([t]),
        azimuth=np.array([true_azimuth]),
        apparent_elevation=np.array([elevation]),
        sunrise=t,
    )


def test_sun_at_obstacles_true_bearing_is_blocked_for_a_bristol_candidate():
    dsm, dtm, hx, hy = _bristol_world()
    result = score_candidates(
        dsm,
        dtm,
        home_x=hx,
        home_y=hy,
        radius=1.0,
        spacing=1.0,
        eye_height=EYE_HEIGHT,
        sun_track=_sun_at(TRUE_BEARING, SUN_ELEVATION),
        max_ray=600.0,
    )
    home = np.argmin(np.hypot(result.x - hx, result.y - hy))
    assert result.distance_m[home] == 0.0
    assert result.fraction_clear[home] == 0.0, "sun behind the strip must be blocked"
    assert result.worst_horizon_angle[home] > 5.0


def _cast_at_bristol(convergence_deg: float) -> float:
    dsm, _, hx, hy = _bristol_world()
    return float(
        horizon_angle(
            dsm,
            np.array([hx]),
            np.array([hy]),
            np.array([EYE_HEIGHT]),
            TRUE_BEARING,
            ray_samples(600.0),
            convergence_deg=convergence_deg,
        )[0]
    )


def test_bristol_convergence_hits_the_strip_but_skipping_or_flipping_it_misses():
    _, _, hx, hy = _bristol_world()
    convergence = meridian_convergence(hx, hy)
    assert convergence == pytest.approx(-0.4725, abs=0.001)

    assert _cast_at_bristol(convergence) > 5.0
    # 0.47 deg at 500 m puts the ray ~4 m north of a 3 m wide strip.
    assert _cast_at_bristol(0.0) < 0.0, "skipping the conversion must miss the strip"
    assert _cast_at_bristol(-convergence) < 0.0, "the wrong sign must miss it too"


@pytest.mark.parametrize(
    "lat,lon",
    [
        (51.4720, -2.6040),  # Bristol, just west of 2 deg W
        (58.2000, -6.4000),  # Isle of Lewis, far west
        (52.6300, 1.3000),  # Norwich, east of 2 deg W
    ],
)
def test_meridian_convergence_turns_a_true_bearing_into_its_grid_bearing(lat, lon):
    """Independent check: walk 100 m along a geodesic on true bearing 0 and
    measure its bearing on the BNG grid. Grid bearing = true - convergence.
    """
    x0, y0 = _WGS84_TO_BNG.transform(lon, lat)
    lon1, lat1, _ = _GEOD.fwd(lon, lat, 0.0, 100.0)
    x1, y1 = _WGS84_TO_BNG.transform(lon1, lat1)
    grid_bearing = math.degrees(math.atan2(x1 - x0, y1 - y0))
    assert -meridian_convergence(x0, y0) == pytest.approx(grid_bearing, abs=0.001)


def _write_tile(grid: RasterGrid, path: Path) -> None:
    import rasterio

    path.parent.mkdir(parents=True, exist_ok=True)
    rows, cols = grid.shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="float32",
        crs=grid.crs,
        transform=grid.transform,
    ) as dst:
        dst.write(grid.data, 1)


def test_profile_only_reports_a_true_north_horizon_profile(tmp_path):
    dsm, dtm, hx, hy = _bristol_world()
    _write_tile(dsm, tmp_path / "dsm" / "dsm.tif")
    _write_tile(dtm, tmp_path / "dtm" / "dtm.tif")
    config = tmp_path / "sunspot.toml"
    config.write_text(
        "home_lat = 0.0\nhome_lon = 0.0\n"
        f'dsm_dir = "{tmp_path / "dsm"}"\n'
        f'dtm_dir = "{tmp_path / "dtm"}"\n'
        f'cache_dir = "{tmp_path / "cache"}"\n'
    )
    lon, lat = _BNG_TO_WGS84.transform(hx, hy)

    result = CliRunner().invoke(
        app,
        [
            "profile-only",
            f"{lat:.9f},{lon:.9f}",
            "--config",
            str(config),
            "--max-ray",
            "600",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 0, result.output

    with open(tmp_path / "out" / "horizon_profile.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == ["true_azimuth_deg", "horizon_angle_deg"]
    profile = {float(r["true_azimuth_deg"]): float(r["horizon_angle_deg"]) for r in rows}
    assert profile[90.0] > 5.0, "the strip sits on true bearing 90"
    assert profile[89.0] < 0.0 and profile[91.0] < 0.0
