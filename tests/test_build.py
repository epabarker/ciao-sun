"""`ciao-sun build`: build inputs -> build directory (#36).

The real build runs on the tiny synthetic world of `tests/build_world.py`, and
its output is read back only through the tile codec and the manifest.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from ciao_sun.build import BuildError, build, check_profiles
from ciao_sun.build_checks import BuildCheckError
from ciao_sun.cli import app
from ciao_sun.fetch import read_lockfile
from ciao_sun.reference.fixtures import bristol_query_set
from ciao_sun.tile_codec import PROFILE_SAMPLES, Tile, codes_to_degrees, read_tile, write_tile
from tests import basemap_world as protomaps
from tests import build_world as world
from tests.osm_extract import bng_of

TODAY = date(2026, 11, 11)


class Built:
    def __init__(self, directory: Path, inputs: Path, reported: list[str]) -> None:
        self.directory = directory
        self.inputs = inputs
        self.reported = reported
        self.manifest = json.loads((directory / "manifest.json").read_text())
        self.windows: dict[str, dict[str, Tile]] = {
            window: {
                path.stem: read_tile(path)
                for path in sorted((directory / "tiles" / window).glob("*.bin"))
            }
            for window in ("morning", "evening")
        }
        # Candidates, names and the walk graph are the same in both windows' tiles.
        self.tiles = self.windows["morning"]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Built:
    root = tmp_path_factory.mktemp("build")
    lock = world.fetch_inputs(root)
    reported: list[str] = []
    ten_minutes_a_tick = iter(range(0, 10**9, 600))
    directory = build(
        world.coverage(), lock.root, root / "builds", today=TODAY,
        report=reported.append, clock=lambda: float(next(ten_minutes_a_tick)),
    )  # fmt: skip
    return Built(directory, lock.root, reported)


def test_a_build_writes_one_tile_per_square_the_coverage_touches_and_a_manifest(built: Built):
    assert sorted(built.tiles) == ["ST5773", "ST5873"]
    assert built.manifest["format"] == 1
    assert built.manifest["build"] == "20261111a"
    assert built.directory.name == "20261111a" and built.directory.parent.name == "f1"


def test_a_build_reports_each_square_as_it_finishes_with_the_time_left(built: Built):
    counts = {ref: entry["candidates"] for ref, entry in built.manifest["tiles"].items()}

    progress = [line for line in built.reported if line.startswith("square ")]

    assert progress == [
        f"square 1/2 ST5773: {counts['ST5773']} Candidates; 10 min elapsed, about 10 min left",
        f"square 2/2 ST5873: {counts['ST5873']} Candidates; 20 min elapsed, about 0 min left",
    ]


def _positions(tile: Tile) -> list[tuple[int, int]]:
    """A tile's Candidates as whole National Grid metres."""
    return [
        tuple(round(v) for v in bng_of(int(lat), int(lon)))
        for lat, lon in zip(tile.candidates.lat_e7, tile.candidates.lon_e7, strict=True)
    ]


def _profile(built: Built, position: tuple[float, float]) -> np.ndarray:
    """The decoded Horizon profile, in degrees, of the Candidate at a National Grid position:
    each sample from whichever window's tile holds it, NaN where neither does."""
    key = (round(position[0]), round(position[1]))
    profile = np.full(PROFILE_SAMPLES, np.nan)
    for tiles in built.windows.values():
        for tile in tiles.values():
            positions = _positions(tile)
            if key in positions:
                held = tile.sector.indexes()
                codes = tile.candidates.profile_codes[positions.index(key), held]
                profile[held] = codes_to_degrees(codes)
    if np.isnan(profile).all():
        raise AssertionError(f"no Candidate at {position}")
    return profile


def test_candidates_come_only_from_inside_the_coverage_and_beside_the_street(built: Built):
    expected = {(x, y) for x in world.CANDIDATE_XS for y in world.CANDIDATE_YS}
    found = [position for tile in built.tiles.values() for position in _positions(tile)]

    assert len(found) == len(expected) == 57
    assert set(found) == expected
    assert len(built.tiles["ST5773"].candidates.lat_e7) == 27
    assert len(built.tiles["ST5873"].candidates.lat_e7) == 30


def test_every_candidate_is_named_for_its_street(built: Built):
    for tile in built.tiles.values():
        assert tile.names == ("Ridge Road",)


def test_the_edge_that_crosses_the_tile_boundary_is_in_both_tiles(built: Built):
    def edges(tile: Tile) -> set[tuple[int, int]]:
        ids = tile.walk_graph.node_id
        return {
            (int(ids[a]), int(ids[b]))
            for a, b in zip(tile.walk_graph.edge_from, tile.walk_graph.edge_to, strict=True)
        }

    west, east = edges(built.tiles["ST5773"]), edges(built.tiles["ST5873"])
    assert west == {(1, 2), (2, 3)}
    assert east == {(2, 3), (3, 4)}


def test_a_wall_on_a_true_bearing_shows_at_that_true_azimuth(built: Built):
    # The wall is 180 m due true east of P. Cast along grid east instead, it
    # would show 0.47 deg (two samples) away: the true-north guard of #15.
    x0, x1, y0, y1 = world.wall_block()
    true_bearing = world.true_azimuth(world.P, ((x0 + x1) / 2, (y0 + y1) / 2))
    profile = _profile(built, world.P)
    east = np.arange(300, 420)
    wall = east[profile[east] > 5.0]

    assert true_bearing == pytest.approx(90.0, abs=0.2)
    assert wall.mean() * 0.25 == pytest.approx(true_bearing, abs=0.2)
    # atan((40 - 11.6) / 180) = 8.97 deg; the wall's near face is 1.5 m nearer.
    assert profile[east].max() == pytest.approx(9.0, abs=0.2)


def test_a_bare_crowned_tree_blocks_the_sky_at_its_first_return_height(built: Built):
    # True north-east of T the first return is 25 m and the last return is the
    # ground; the crown's near corner is 33 m east and 33 m north of T, 46.7 m
    # along the ray: atan((25 - 11.6) / 46.7) = 16.0 deg. Without the crown
    # envelope the horizon there would be the far ridge, under 3 deg.
    assert _profile(built, world.T)[180] == pytest.approx(16.0, abs=0.7)


def test_the_far_ridge_from_terrain_50_sets_the_horizon_where_nothing_nearer_does(built: Built):
    # North-east of P the near field is flat ground. The ridge's first full-height
    # Terrain 50 cells are 4,550 m north of P, so 4550 x sqrt(2) = 6,435 m along
    # the ray: atan((310 - 11.6 - 2.88) / 6435) = 2.63 deg, 2.88 m being the
    # curvature drop 6435^2 / (2 * 1.13 * 6371000). Due north is in no tile.
    assert _profile(built, world.P)[180] == pytest.approx(2.63, abs=0.1)
    assert np.isnan(_profile(built, world.P)[0])


# --- The manifest -------------------------------------------------------------


def test_the_manifest_credits_every_source_and_licenses_the_bundle_odbl(built: Built):
    credits = {line["source"]: line for line in built.manifest["attribution"]}

    assert list(credits) == [
        "Environment Agency",
        "Ordnance Survey",
        "OpenStreetMap",
        "Protomaps",
        "Met Office",
        "Open-Meteo",
    ]
    assert credits["Environment Agency"]["text"] == (
        "© Environment Agency copyright and/or database right 2022. All rights reserved."
    )
    assert credits["Ordnance Survey"]["text"] == (
        "Contains OS data © Crown copyright and database right 2026"
    )
    assert "Open Government Licence v3" in credits["Environment Agency"]["licence"]
    assert "Open Government Licence v3" in credits["Ordnance Survey"]["licence"]
    assert "OpenStreetMap" in credits["OpenStreetMap"]["text"]
    assert "ODbL" in credits["OpenStreetMap"]["licence"]
    assert "Protomaps" in credits["Protomaps"]["text"]
    # The forecast's credits, as the sky slot words them (spec #27, story 50).
    assert credits["Met Office"]["text"] == (
        "Forecast data from the Met Office via Open-Meteo, cloud cover categorised by Ciao Sun"
    )
    assert credits["Met Office"]["licence"] == "CC BY-SA 4.0"
    assert credits["Met Office"]["licenceUrl"] == "https://creativecommons.org/licenses/by-sa/4.0/"
    assert credits["Open-Meteo"]["text"] == "Weather data by Open-Meteo.com"
    assert credits["Open-Meteo"]["licence"] == "CC BY 4.0"
    assert credits["Open-Meteo"]["licenceUrl"] == "https://creativecommons.org/licenses/by/4.0/"
    assert built.manifest["licence"]["spdx"] == "ODbL-1.0"
    assert "ODbL" in built.manifest["licence"]["name"]


def test_the_manifest_lists_the_years_the_lidar_was_flown(built: Built):
    # From the survey dates in the EA tile's metadata, not the composite's year.
    assert built.manifest["lidarSurveyYears"] == [2019, 2021]


def test_the_manifest_records_every_input_with_its_version_and_sha256(built: Built):
    lock = read_lockfile(built.inputs)
    listed = {(line["kind"], line["tile"]): line for line in built.manifest["inputs"]}

    assert len(listed) == len(lock.inputs)
    for entry in lock.inputs:
        line = listed[(entry.kind, entry.tile)]
        assert line["source"] == entry.source and line["version"] == entry.version
        assert line["absent"] == entry.absent
        if not entry.absent:
            digest = hashlib.sha256(lock.path_of(entry).read_bytes()).hexdigest()
            assert line["sha256"] == digest
    versions = {kind: line["version"] for (kind, tile), line in listed.items() if not tile}
    assert versions == {"terrain50": "2026-07", "osm": "261110", "basemap": "20260811"}
    assert listed[("dsm", world.EA_TILE)]["version"] == "2022"
    # EA publishes nothing for the other 5 km tiles within 3 km of the coverage.
    assert listed[("dsm", "ST6070")]["absent"] and listed[("dsm", "ST6070")]["sha256"] is None


def test_the_manifest_dates_the_osm_data_by_its_replication_timestamp(built: Built):
    (osm,) = [line for line in built.manifest["inputs"] if line["kind"] == "osm"]
    assert osm["timestamp"] == world.OSM_TIMESTAMP


def test_the_manifest_holds_the_coverage_polygon(built: Built):
    assert built.manifest["coverage"] == world.coverage().geometry


def test_the_manifest_indexes_exactly_the_tiles_written(built: Built):
    index = built.manifest["tiles"]

    for window in ("morning", "evening"):
        assert sorted(index) == sorted(built.windows[window])
    for grid_ref, line in index.items():
        assert line["candidates"] == len(built.tiles[grid_ref].candidates.lat_e7)
        for window in ("morning", "evening"):
            data = (built.directory / "tiles" / window / f"{grid_ref}.bin").read_bytes()
            assert line[window]["bytes"] == len(data)
            assert line[window]["sha256"] == hashlib.sha256(data).hexdigest()


def test_each_windows_tiles_hold_only_its_sector_as_the_manifest_records(built: Built):
    sectors = built.manifest["sectors"]

    for window in ("morning", "evening"):
        for tile in built.windows[window].values():
            assert (tile.sector.first, tile.sector.samples) == (
                sectors[window]["firstSample"],
                sectors[window]["samples"],
            )
    # Bristol: the morning from before the earliest sunrise to past solar noon,
    # the evening from before solar noon to past the latest sunset.
    morning, evening = (sectors[w]["firstSample"] * 0.25 for w in ("morning", "evening"))
    assert morning == pytest.approx(35.0, abs=1.5)
    assert evening == pytest.approx(169.0, abs=1.5)


def test_the_manifest_records_the_tolerances_the_build_checks_passed_at(built: Built):
    checks = built.manifest["buildChecks"]

    # #61: far-field lattice p99 0.040 deg at 50 m; #6: far sampling p99 0.014 deg; on
    # top of the storage code's half step (0.05 deg to 10 deg, 0.25 deg above).
    assert checks["profile"]["toleranceDeg"] == 0.05
    assert checks["profile"]["storageHalfStepDeg"] == {"upTo10Deg": 0.05, "above10Deg": 0.25}
    assert checks["profile"]["fractionWithin"] == 0.99
    assert checks["profile"]["candidatesChecked"] == 32  # 16 in each tile
    assert checks["waterGuard"] == {
        "candidatesAllowed": 0,
        "candidatesFound": 0,
        "riverCandidatesToReview": 0,
    }


# --- The basemap --------------------------------------------------------------


def _basemap_tree(directory: Path) -> dict[tuple[int, int, int], bytes]:
    return {
        (int(path.parts[-3]), int(path.parts[-2]), int(path.stem)): path.read_bytes()
        for path in (directory / "basemap").rglob("*")
        if path.is_file()
    }


def test_a_build_holds_the_basemap_tiles_over_the_coverages_bounding_box_at_zooms_10_to_15(
    built: Built,
):
    tree = _basemap_tree(built.directory)

    assert set(tree) == protomaps.tiles_over(world.coverage().bounds_wgs84(), range(10, 16))
    assert {z for z, _, _ in tree} == {10, 11, 12, 13, 14, 15}
    for (z, x, y), content in tree.items():
        assert (built.directory / "basemap" / str(z) / str(x) / f"{y}.mvt").is_file()
        assert content == protomaps.tile_text(z, x, y)  # the vector tile itself, not gzip


def test_the_manifest_describes_the_basemap_and_dates_it_by_its_protomaps_build(built: Built):
    tree = _basemap_tree(built.directory)
    west, south, east, north = world.coverage().bounds_wgs84()

    assert built.manifest["basemap"] == {
        "protomapsBuild": "20260811",
        "tilesetVersion": "4.15.1",
        "osmTimestamp": "2026-08-11T04:00:00Z",
        "minZoom": 10,
        "maxZoom": 15,
        "bounds": [west, south, east, north],
        "tileCount": len(tree),
        "bytes": sum(len(content) for content in tree.values()),
    }
    (line,) = [line for line in built.manifest["inputs"] if line["kind"] == "basemap"]
    assert line["version"] == "20260811"
    assert line["url"] == "https://build.protomaps.com/20260811.pmtiles"
    assert "Protomaps" in line["source"]


def test_the_manifest_credits_protomaps_and_openstreetmap_for_the_basemap(built: Built):
    (credit,) = [line for line in built.manifest["attribution"] if line["source"] == "Protomaps"]

    assert credit["text"] == "Protomaps © OpenStreetMap"
    assert "ODbL" in credit["licence"]
    assert credit["licenceUrl"] == "https://opendatacommons.org/licenses/odbl/1-0/"


def test_no_pmtiles_archive_is_shipped(built: Built):
    files = [path for path in built.directory.rglob("*") if path.is_file()]
    kinds = {(path.relative_to(built.directory).parts[0], path.suffix) for path in files}

    assert kinds == {("manifest.json", ".json"), ("tiles", ".bin"), ("basemap", ".mvt")}
    for path in files:
        assert not path.read_bytes().startswith(b"PMTiles"), path


def test_inputs_fetched_without_a_basemap_are_refused(built: Built, tmp_path: Path):
    inputs = Path(shutil.copytree(built.inputs, tmp_path / "inputs"))
    lockfile = json.loads((inputs / "fetch.lock.json").read_text())
    lockfile["inputs"] = [line for line in lockfile["inputs"] if line["kind"] != "basemap"]
    (inputs / "fetch.lock.json").write_text(json.dumps(lockfile))

    with pytest.raises(BuildError, match="basemap.*ciao-sun fetch"):
        build(world.coverage(), inputs, tmp_path / "builds", today=TODAY)

    assert not (tmp_path / "builds").exists()


def test_a_far_reach_beyond_100_km_is_refused(tmp_path: Path):
    lock = world.fetch_inputs(tmp_path)

    with pytest.raises(ValueError, match="at most 100000 m"):
        build(world.coverage(), lock.root, tmp_path / "builds", today=TODAY, far_reach_m=100_001.0)

    assert not (tmp_path / "builds" / "f1" / "20261111a").exists()


# --- Reproducibility ----------------------------------------------------------


def test_the_same_inputs_give_byte_identical_tiles_whatever_the_build_id_or_workers(built: Built):
    again = build(
        world.coverage(), built.inputs, built.directory.parents[1], today=TODAY, workers=2
    )

    assert again.name == "20261111b"  # the next letter: a build is never overwritten
    for window in ("morning", "evening"):
        for grid_ref in built.tiles:
            first = (built.directory / "tiles" / window / f"{grid_ref}.bin").read_bytes()
            assert (again / "tiles" / window / f"{grid_ref}.bin").read_bytes() == first
    assert json.loads((again / "manifest.json").read_text())["tiles"] == built.manifest["tiles"]


# --- The build checks ---------------------------------------------------------


def _rewrite(
    build_dir: Path, grid_ref: str, change: Callable[[np.ndarray], None], window: str = "morning"
) -> None:
    """Change a written tile's profile codes in place, through the codec. `change` gets
    the codes of the tile's sector only, one row per Candidate."""
    tile = read_tile(build_dir / "tiles" / window / f"{grid_ref}.bin")
    held = tile.sector.indexes()
    codes = tile.candidates.profile_codes.copy()
    in_sector = codes[:, held]
    change(in_sector)
    codes[:, held] = in_sector
    changed = replace(tile, candidates=replace(tile.candidates, profile_codes=codes))
    write_tile(changed, build_dir / "tiles" / window)


def test_the_direct_ray_check_passes_the_build_as_written(built: Built):
    assert check_profiles(built.directory, built.inputs) == 32


def test_a_corrupted_profile_fails_the_direct_ray_check(built: Built, tmp_path: Path):
    copy = Path(shutil.copytree(built.directory, tmp_path / built.directory.name))

    def raise_a_sector(codes: np.ndarray) -> None:
        codes[0, 300:340] += 10  # one Candidate, 10 deg of azimuth, 1 deg too high

    _rewrite(copy, "ST5873", raise_a_sector)

    with pytest.raises(BuildCheckError, match=r"morning: ST5873 Candidate 0: 40 of \d+"):
        check_profiles(copy, built.inputs)


def test_profiles_turned_from_true_north_to_grid_north_fail_the_direct_ray_check(
    built: Built, tmp_path: Path
):
    # Grid north is 0.47 deg from true north here: two samples.
    copy = Path(shutil.copytree(built.directory, tmp_path / built.directory.name))

    def turn(codes: np.ndarray) -> None:
        codes[:] = np.roll(codes, 2, axis=1)

    _rewrite(copy, "ST5773", turn)

    with pytest.raises(BuildCheckError, match="ST5773 Candidate"):
        check_profiles(copy, built.inputs)


def _tiles_bytes(build_dir: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted((build_dir / "tiles").glob("*.bin"))}


def test_a_boat_moored_in_a_dock_sets_no_horizon(tmp_path: Path):
    # #60: boats move, so the dock is as if the boat were not there.
    empty = world.fetch_inputs(tmp_path / "empty", dock=True)
    moored = world.fetch_inputs(tmp_path / "moored", dock=True, boat=True)

    without = build(world.coverage(), empty.root, tmp_path / "empty-builds", today=TODAY)
    with_boat = build(world.coverage(), moored.root, tmp_path / "moored-builds", today=TODAY)

    assert _tiles_bytes(with_boat) == _tiles_bytes(without)
    guard = json.loads((with_boat / "manifest.json").read_text())["buildChecks"]["waterGuard"]
    assert guard["candidatesFound"] == 0


def test_a_moored_boat_left_standing_fails_the_water_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # The guard catches a mask that stops lowering what it marks.
    import ciao_sun.build as build_module

    lower = build_module.lower_moored_boats

    def leave_standing(surface, *args, **kwargs):
        lowered = lower(surface, *args, **kwargs)
        return replace(lowered, surface=surface)

    monkeypatch.setattr(build_module, "lower_moored_boats", leave_standing)
    lock = world.fetch_inputs(tmp_path, dock=True, boat=True)

    with pytest.raises(BuildCheckError, match=r"Water guard: \d+ Candidates"):
        build(world.coverage(), lock.root, tmp_path / "builds", today=TODAY)

    assert not (tmp_path / "builds" / "f1" / "20261111a").exists()
    assert not list((tmp_path / "builds").rglob("manifest.json"))


def test_a_river_standing_proud_is_kept_and_reported_for_review(tmp_path: Path):
    # A tidal river whose first return stands 5 m proud, as in the EA composite:
    # over a river LIDAR cannot tell this from trees, so it stays and is reported.
    lock = world.fetch_inputs(tmp_path, tidal_river=True)
    reported: list[str] = []

    build_dir = build(
        world.coverage(), lock.root, tmp_path / "builds", today=TODAY, report=reported.append
    )

    guard = json.loads((build_dir / "manifest.json").read_text())["buildChecks"]["waterGuard"]
    assert guard["candidatesFound"] == 0
    assert guard["riverCandidatesToReview"] == 57
    assert any(line.startswith("River and pond review: 57 Candidates") for line in reported)


def test_a_coverage_beyond_the_fetched_one_is_refused(built: Built, tmp_path: Path):
    wider = world.coverage((357905.0, 173400.0, 358195.0, 173600.0))

    with pytest.raises(BuildError, match="fetch"):
        build(wider, built.inputs, tmp_path / "builds", today=TODAY)


# --- The command --------------------------------------------------------------


def _coverage_file(path: Path, box: tuple[float, float, float, float] = world.COVERAGE_BOX) -> Path:
    path.write_text(json.dumps({"type": "Feature", "geometry": world.coverage(box).geometry}))
    return path


def test_the_build_command_writes_a_build_directory(built: Built, tmp_path: Path):
    result = CliRunner().invoke(
        app,
        ["build", "--coverage", str(_coverage_file(tmp_path / "coverage.geojson")),
         "--inputs", str(built.inputs), "--out", str(tmp_path / "builds"), "--workers", "1"],
    )  # fmt: skip

    assert result.exit_code == 0, result.output
    (manifest,) = (tmp_path / "builds" / "f1").glob("*/manifest.json")
    assert re.fullmatch(r"\d{8}a", manifest.parent.name)
    assert json.loads(manifest.read_text())["tiles"] == built.manifest["tiles"]
    # Without --queries the golden fixtures are the committed Bristol query set's (#41).
    fixtures = json.loads((manifest.parent / "fixtures" / "index.json").read_text())["fixtures"]
    assert [line["id"] for line in fixtures] == [entry.id for entry in bristol_query_set()]
    assert all((manifest.parent / "fixtures" / line["file"]).is_file() for line in fixtures)


def test_the_build_command_refuses_an_unreadable_query_set_before_building(
    built: Built, tmp_path: Path
):
    queries = tmp_path / "queries.json"
    queries.write_text('{"queries": [{"id": "Not An Id", "query": {}}]}')
    result = CliRunner().invoke(
        app,
        ["build", "--coverage", str(_coverage_file(tmp_path / "coverage.geojson")),
         "--inputs", str(built.inputs), "--out", str(tmp_path / "builds"),
         "--queries", str(queries)],
    )  # fmt: skip

    assert result.exit_code == 1
    assert "queries.json" in result.output and "Traceback" not in result.output
    assert not (tmp_path / "builds").exists()


def test_the_build_command_reports_a_refused_build_without_a_traceback(
    built: Built, tmp_path: Path
):
    wider = _coverage_file(tmp_path / "wider.geojson", (357905.0, 173400.0, 358195.0, 173600.0))
    result = CliRunner().invoke(
        app,
        ["build", "--coverage", str(wider), "--inputs", str(built.inputs),
         "--out", str(tmp_path / "builds")],
    )  # fmt: skip

    assert result.exit_code == 1
    assert "ciao-sun fetch" in result.output and "Traceback" not in result.output
    assert not (tmp_path / "builds").exists()


def test_build_help_names_what_is_written_and_what_fails_a_build():
    result = CliRunner().invoke(app, ["build", "--help"], terminal_width=200)
    assert result.exit_code == 0, result.output
    # Rich colours its output on GitHub Actions, splitting option names with escape codes.
    text = " ".join(re.sub(r"\x1b\[[0-9;]*m", "", result.output).split())
    for phrase in [
        "--coverage", "GeoJSON", "--inputs", "fetch.lock.json", "--out", "manifest.json",
        "tiles/morning/<grid ref>.bin", "tiles/evening/<grid ref>.bin",
        "direct ray casting", "water", "SHA-256", "--workers",
        "basemap/{z}/{x}/{y}.mvt", "Protomaps",
        "--queries", "fixtures/index.json", "golden fixture",
    ]:  # fmt: skip
        assert phrase in text, f"`build --help` does not mention {phrase!r}"
