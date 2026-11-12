"""Horizon profile precompute, asserted on tiles read back through the codec (#34).

Every world is small and synthetic. Expected angles are worked by hand from
    angle = atan((obstacle top - eye - d^2 / (2 * 1.13 * 6371000)) / d)
with the eye 1.6 m above the ground.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

import numpy as np
import pytest
from pyproj import Geod, Transformer
from rasterio.transform import rowcol

from ciao_sun.horizon import horizon_angle, meridian_convergence, ray_samples
from ciao_sun.horizon_precompute import (
    TileWorld,
    cast_tile,
    horizon_profile_codes,
    precompute_tiles,
)
from ciao_sun.raster import RasterGrid
from ciao_sun.tile_codec import (
    PROFILE_SAMPLES,
    Candidates,
    Tile,
    WalkGraph,
    read_tile,
    write_tile,
)
from tests.conftest import make_flat_grid

_WGS84_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
_BNG_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
_GEOD = Geod(ellps="WGS84")

BRISTOL_LAT, BRISTOL_LON = 51.4720, -2.6040
# The storage code's steps: 0.1 deg up to 10 deg, 0.5 deg above. A decoded
# angle is within half a step of the angle that was encoded.
FINE_TOLERANCE = 0.05
COARSE_TOLERANCE = 0.25


def _sample_index(true_azimuth: float) -> int:
    """The profile sample at a true azimuth: one per 0.25 deg, clockwise from true north."""
    return round(true_azimuth * 4)


def _bristol_candidate() -> tuple[float, float]:
    """A Bristol position on a 100 m BNG grid point, where convergence is about -0.47 deg."""
    x, y = _WGS84_TO_BNG.transform(BRISTOL_LON, BRISTOL_LAT)
    return float(round(x, -2)), float(round(y, -2))


def _empty_terrain(x: float, y: float) -> RasterGrid:
    """A Terrain 50 raster that holds no data anywhere a far-field ray lands."""
    return make_flat_grid(np.nan, xmin=x - 75.0, ymax=y + 75.0, width=4, height=4, pixel_size=50.0)


def _written_tile(
    directory: Path, grid_ref: str, x: np.ndarray, y: np.ndarray, codes: np.ndarray
) -> Tile:
    """Write Candidates and their profile codes as an f1 tile, then read it back."""
    lon, lat = _BNG_TO_WGS84.transform(x, y)
    n = len(x)
    zeros = np.zeros(n, dtype=np.uint32)
    tile = Tile(
        grid_ref=grid_ref,
        names=("Test Green",),
        candidates=Candidates(
            lat_e7=np.round(np.asarray(lat) * 1e7).astype(np.int32),
            lon_e7=np.round(np.asarray(lon) * 1e7).astype(np.int32),
            node_index=zeros,
            offset_cm=zeros,
            name_index=zeros,
            profile_codes=codes,
        ),
        walk_graph=WalkGraph(
            node_id=np.array([1], dtype=np.uint64),
            node_lat_e7=np.array([0], dtype=np.int32),
            node_lon_e7=np.array([0], dtype=np.int32),
            edge_from=np.zeros(0, dtype=np.uint32),
            edge_to=np.zeros(0, dtype=np.uint32),
            edge_length_cm=np.zeros(0, dtype=np.uint32),
        ),
    )
    return read_tile(write_tile(tile, directory))


def test_obstacle_on_a_true_bearing_decodes_at_that_bearing_for_a_bristol_candidate(tmp_path):
    """The true-north guard. A 3 m wide, 50 m tall strip lies 480-520 m out on
    true bearing 90, placed by walking a WGS84 geodesic. At 480 m, Bristol's
    0.47 deg of convergence is ~4 m sideways, so a profile indexed by grid
    azimuth would show the strip two samples away, at 89.5.
    """
    cx, cy = _bristol_candidate()
    surface = make_flat_grid(0.0, xmin=cx - 10.0, ymax=cy + 20.0, width=560, height=41)
    dtm = make_flat_grid(0.0, xmin=cx - 10.0, ymax=cy + 20.0, width=560, height=41)
    lon0, lat0 = _BNG_TO_WGS84.transform(cx, cy)
    for d in range(480, 521):
        lon, lat, _ = _GEOD.fwd(lon0, lat0, 90.0, float(d))
        sx, sy = _WGS84_TO_BNG.transform(lon, lat)
        (row,), (col,) = rowcol(surface.transform, [sx], [sy])
        surface.data[row - 1 : row + 2, col] = 50.0
    x, y = np.array([cx]), np.array([cy])

    codes = horizon_profile_codes(TileWorld(surface, dtm, _empty_terrain(cx, cy), x, y))
    profile = _written_tile(tmp_path, "ST5873", x, y, codes).horizon_profile_degrees(0)

    # atan((50 - 1.6 - 0.016) / 480) = 5.756 deg
    assert profile[_sample_index(90.0)] == pytest.approx(5.756, abs=FINE_TOLERANCE + 0.01)
    assert profile[_sample_index(89.5)] < 0.0
    assert profile[_sample_index(90.5)] < 0.0


def _ridge_world() -> TileWorld:
    """Two Candidates sharing one far-field lattice point, facing a distant ridge.

    Candidate A stands on the lattice point, on ground at 0 m. Candidate B is
    30 m north of it on a plateau at 50 m (the plateau is every cell 20 m or
    more north of A). Terrain 50 is flat at 0 m except for a 300 m ridge
    running north-south, whose crest starts 10 km east of both Candidates.
    """
    ax, ay = _bristol_candidate()
    surface = make_flat_grid(0.0, xmin=ax - 100.0, ymax=ay + 100.0, width=201, height=201)
    surface.data[:81, :] = 50.0  # rows 0-80 are the cells at ay + 20 and north
    dtm = RasterGrid(surface.data.copy(), surface.transform, surface.crs)
    terrain50 = make_flat_grid(
        0.0, xmin=ax - 5000.0, ymax=ay + 5000.0, width=400, height=201, pixel_size=50.0
    )
    (_,), (first_col,) = rowcol(terrain50.transform, [ax + 10_000.0], [ay])
    terrain50.data[:, first_col : first_col + 10] = 300.0
    return TileWorld(surface, dtm, terrain50, np.array([ax, ax]), np.array([ay, ay + 30.0]))


def test_distant_ridge_raises_the_merged_profile_with_each_candidates_own_eye_height(tmp_path):
    world = _ridge_world()

    codes = horizon_profile_codes(world)
    tile = _written_tile(tmp_path, "ST5873", world.x, world.y, codes)
    a, b = tile.horizon_profile_degrees(0), tile.horizon_profile_degrees(1)

    east = _sample_index(90.0)
    # A, eye at 1.6 m: atan((300 - 1.6 - 6.945) / 10000) = 1.670 deg
    assert a[east] == pytest.approx(1.670, abs=FINE_TOLERANCE + 0.01)
    # B, eye at 51.6 m, sees the same ridge lower: atan((300 - 51.6 - 6.945) / 10000) = 1.383 deg
    assert b[east] == pytest.approx(1.383, abs=FINE_TOLERANCE + 0.01)


def test_far_field_never_lowers_a_near_obstruction_and_lifts_an_open_horizon(tmp_path):
    world = _ridge_world()

    codes = horizon_profile_codes(world)
    a = _written_tile(tmp_path, "ST5873", world.x, world.y, codes).horizon_profile_degrees(0)

    # North of A the plateau edge is 20 m away: atan(48.4 / 20) = 67.5 deg, above
    # the top of the storage code, so it clamps to 63.5.
    assert a[_sample_index(0.0)] == 63.5
    # West of A there is flat ground to the far field's reach. The near surface
    # ends 100 m out, where flat ground sits at atan(-1.6 / 100) = -0.92 deg;
    # Terrain 50 carries the horizon on to atan((-1.6 - 0.625) / 3000) = -0.04 deg.
    assert a[_sample_index(270.0)] == pytest.approx(-0.04, abs=FINE_TOLERANCE + 0.01)


def _rooftop_world(cx: float, cy: float, seed: int) -> TileWorld:
    """One Candidate on flat ground among scattered blocks 2-60 m tall, with no far field."""
    surface = make_flat_grid(0.0, xmin=cx - 150.0, ymax=cy + 150.0, width=301, height=301)
    dtm = make_flat_grid(0.0, xmin=cx - 150.0, ymax=cy + 150.0, width=301, height=301)
    rng = np.random.default_rng(seed)
    for _ in range(60):
        row, col = rng.integers(0, 290, size=2)
        if abs(row - 150) < 15 and abs(col - 150) < 15:
            continue  # keep the Candidate's own ground open
        surface.data[row : row + 10, col : col + 10] = rng.uniform(2.0, 60.0)
    return TileWorld(surface, dtm, _empty_terrain(cx, cy), np.array([cx]), np.array([cy]))


def test_profile_is_1440_samples_each_within_the_storage_code_tolerance_of_a_direct_ray(tmp_path):
    cx, cy = _bristol_candidate()
    world = _rooftop_world(cx, cy, seed=34)

    codes = horizon_profile_codes(world)
    profile = _written_tile(tmp_path, "ST5873", world.x, world.y, codes).horizon_profile_degrees(0)

    assert profile.shape == (PROFILE_SAMPLES,) == (1440,)
    direct = np.array(
        [
            horizon_angle(
                world.surface,
                world.x,
                world.y,
                np.array([1.6]),
                true_azimuth,
                ray_samples(3000.0),
                convergence_deg=meridian_convergence(cx, cy),
            )[0]
            for true_azimuth in np.arange(1440) * 0.25
        ]
    )
    in_range = np.clip(direct, -2.0, 63.5)
    tolerance = np.where(in_range <= 10.0, FINE_TOLERANCE, COARSE_TOLERANCE)
    assert (np.abs(profile - in_range) <= tolerance + 1e-9).all()
    # The world exercises both halves of the code.
    assert (direct < 10.0).any() and (direct > 10.5).any()


_PARALLEL_TILES = {"ST5873": 1, "ST5973": 2, "ST5874": 3}


def _write_rooftop_tile(directory: Path, grid_ref: str) -> Path:
    """A whole tile job, as the build runs it: load the world, cast, write the tile."""
    cx, cy = _bristol_candidate()
    world = _rooftop_world(cx, cy, seed=_PARALLEL_TILES[grid_ref])
    _written_tile(directory, grid_ref, world.x, world.y, horizon_profile_codes(world))
    return directory / f"{grid_ref}.bin"


def test_tiles_computed_in_parallel_are_byte_identical_to_a_serial_run(tmp_path):
    serial_done: list[tuple[str, Path]] = []
    parallel_done: list[tuple[str, Path]] = []
    serial = precompute_tiles(
        list(_PARALLEL_TILES), partial(_write_rooftop_tile, tmp_path / "serial"), workers=1,
        on_done=lambda ref, path: serial_done.append((ref, path)),
    )  # fmt: skip
    parallel = precompute_tiles(
        list(_PARALLEL_TILES), partial(_write_rooftop_tile, tmp_path / "parallel"), workers=3,
        on_done=lambda ref, path: parallel_done.append((ref, path)),
    )  # fmt: skip

    assert list(serial) == list(parallel) == list(_PARALLEL_TILES)
    # Each tile is announced once as it finishes; in parallel, in whatever order they finish.
    assert serial_done == list(serial.items())
    assert sorted(parallel_done) == sorted(parallel.items())
    for grid_ref in _PARALLEL_TILES:
        assert parallel[grid_ref].read_bytes() == serial[grid_ref].read_bytes()
    profiles = [read_tile(path).candidates.profile_codes for path in parallel.values()]
    assert not np.array_equal(profiles[0], profiles[1]), "each tile holds its own world"


def _wall_world(**flags: bool) -> TileWorld:
    """One Candidate on flat ground with a 20 m wall 30 m east; `flags` mark the wall's cells."""
    x, y = _bristol_candidate()
    surface = make_flat_grid(0.0, xmin=x - 100.0, ymax=y + 100.0, width=201, height=201)
    dtm = RasterGrid(surface.data.copy(), surface.transform, surface.crs)
    surface.data[90:111, 128:133] = 20.0  # x + 28 .. x + 32
    marked = np.zeros(surface.data.shape, dtype="float32")
    marked[90:111, 128:133] = 1.0
    terrain50 = make_flat_grid(
        -50.0, xmin=x - 5000.0, ymax=y + 5000.0, width=201, height=201, pixel_size=50.0
    )
    rasters = {
        name: RasterGrid(marked, surface.transform, surface.crs) for name, on in flags.items() if on
    }
    return TileWorld(surface, dtm, terrain50, np.array([x]), np.array([y]), **rasters)


def test_a_cell_marked_for_review_that_sets_a_horizon_is_reported_apart_from_the_guard():
    horizons = cast_tile(_wall_world(review=True))
    assert horizons.set_by_review.tolist() == [True]
    assert horizons.set_by_water.tolist() == [False]


def test_a_guarded_water_cell_that_sets_a_horizon_is_not_a_review(tmp_path):
    horizons = cast_tile(_wall_world(water=True))
    assert horizons.set_by_water.tolist() == [True]
    assert horizons.set_by_review.tolist() == [False]
