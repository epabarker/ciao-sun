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
from ciao_sun.tile_codec import Tile, read_tile, write_tile
from tests import build_world as world
from tests.osm_extract import bng_of

TODAY = date(2026, 11, 11)


class Built:
    def __init__(self, directory: Path, inputs: Path) -> None:
        self.directory = directory
        self.inputs = inputs
        self.manifest = json.loads((directory / "manifest.json").read_text())
        self.tiles: dict[str, Tile] = {
            path.stem: read_tile(path) for path in sorted((directory / "tiles").glob("*.bin"))
        }


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Built:
    root = tmp_path_factory.mktemp("build")
    lock = world.fetch_inputs(root)
    directory = build(world.coverage(), lock.root, root / "builds", today=TODAY)
    return Built(directory, lock.root)


def test_a_build_writes_one_tile_per_square_the_coverage_touches_and_a_manifest(built: Built):
    assert sorted(built.tiles) == ["ST5773", "ST5873"]
    assert built.manifest["format"] == 1
    assert built.manifest["build"] == "20261111a"
    assert built.directory.name == "20261111a" and built.directory.parent.name == "f1"


def _positions(tile: Tile) -> list[tuple[int, int]]:
    """A tile's Candidates as whole National Grid metres."""
    return [
        tuple(round(v) for v in bng_of(int(lat), int(lon)))
        for lat, lon in zip(tile.candidates.lat_e7, tile.candidates.lon_e7, strict=True)
    ]


def _profile(built: Built, position: tuple[float, float]) -> np.ndarray:
    """The decoded Horizon profile, in degrees, of the Candidate at a National Grid position."""
    key = (round(position[0]), round(position[1]))
    for tile in built.tiles.values():
        positions = _positions(tile)
        if key in positions:
            return tile.horizon_profile_degrees(positions.index(key))
    raise AssertionError(f"no Candidate at {position}")


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
    # 50 m north of T the first return is 25 m and the last return is the
    # ground: atan((25 - 11.6) / 48) = 15.6 deg. Without the crown envelope the
    # horizon there would be the far ridge, under 4 deg.
    assert _profile(built, world.T)[0] == pytest.approx(15.6, abs=0.5)


def test_the_far_ridge_from_terrain_50_sets_the_horizon_where_nothing_nearer_does(built: Built):
    # North of P the near field is flat ground. The ridge's first full-height
    # Terrain 50 cell is 4,550 m away: atan((310 - 11.6 - 1.44) / 4550) = 3.73 deg,
    # 1.44 m being the curvature drop 4550^2 / (2 * 1.13 * 6371000).
    assert _profile(built, world.P)[0] == pytest.approx(3.73, abs=0.06)


# --- The manifest -------------------------------------------------------------


def test_the_manifest_credits_every_source_and_licenses_the_bundle_odbl(built: Built):
    credits = {line["source"]: line for line in built.manifest["attribution"]}

    assert list(credits) == ["Environment Agency", "Ordnance Survey", "OpenStreetMap", "Protomaps"]
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
    assert versions == {"terrain50": "2026-07", "osm": "261110"}
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

    assert sorted(index) == sorted(built.tiles)
    for grid_ref, line in index.items():
        data = (built.directory / "tiles" / f"{grid_ref}.bin").read_bytes()
        assert line["bytes"] == len(data)
        assert line["sha256"] == hashlib.sha256(data).hexdigest()
        assert line["candidates"] == len(built.tiles[grid_ref].candidates.lat_e7)


def test_the_manifest_records_the_tolerances_the_build_checks_passed_at(built: Built):
    checks = built.manifest["buildChecks"]

    # #6: far-field lattice p99 0.035 deg and far sampling p99 0.014 deg, on
    # top of the storage code's half step (0.05 deg to 10 deg, 0.25 deg above).
    assert checks["profile"]["toleranceDeg"] == 0.05
    assert checks["profile"]["storageHalfStepDeg"] == {"upTo10Deg": 0.05, "above10Deg": 0.25}
    assert checks["profile"]["fractionWithin"] == 0.99
    assert checks["profile"]["candidatesChecked"] == 32  # 16 in each tile
    assert checks["waterGuard"] == {"candidatesAllowed": 0, "candidatesFound": 0}


# --- Reproducibility ----------------------------------------------------------


def test_the_same_inputs_give_byte_identical_tiles_whatever_the_build_id_or_workers(built: Built):
    again = build(
        world.coverage(), built.inputs, built.directory.parents[1], today=TODAY, workers=2
    )

    assert again.name == "20261111b"  # the next letter: a build is never overwritten
    for grid_ref in built.tiles:
        first = (built.directory / "tiles" / f"{grid_ref}.bin").read_bytes()
        assert (again / "tiles" / f"{grid_ref}.bin").read_bytes() == first
    assert json.loads((again / "manifest.json").read_text())["tiles"] == built.manifest["tiles"]


# --- The build checks ---------------------------------------------------------


def _rewrite(build_dir: Path, grid_ref: str, change: Callable[[np.ndarray], None]) -> None:
    """Change a written tile's profile codes in place, through the codec."""
    tile = read_tile(build_dir / "tiles" / f"{grid_ref}.bin")
    codes = tile.candidates.profile_codes.copy()
    change(codes)
    changed = replace(tile, candidates=replace(tile.candidates, profile_codes=codes))
    write_tile(changed, build_dir / "tiles")


def test_the_direct_ray_check_passes_the_build_as_written(built: Built):
    assert check_profiles(built.directory, built.inputs) == 32


def test_a_corrupted_profile_fails_the_direct_ray_check(built: Built, tmp_path: Path):
    copy = Path(shutil.copytree(built.directory, tmp_path / built.directory.name))

    def raise_a_sector(codes: np.ndarray) -> None:
        codes[0, 600:640] += 10  # one Candidate, 10 deg of azimuth, 1 deg too high

    _rewrite(copy, "ST5873", raise_a_sector)

    with pytest.raises(BuildCheckError, match=r"ST5873 Candidate 0: 40 of 1440"):
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


def test_a_water_cell_on_the_horizon_fails_the_build(tmp_path: Path):
    # A tidal river whose first return stands 5 m proud, as in the EA composite.
    lock = world.fetch_inputs(tmp_path, tidal_river=True)

    with pytest.raises(BuildCheckError, match="Water guard: 57 Candidates"):
        build(world.coverage(), lock.root, tmp_path / "builds", today=TODAY)

    assert not (tmp_path / "builds" / "f1" / "20261111a").exists()
    assert not list((tmp_path / "builds").rglob("manifest.json"))


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
        "tiles/<grid ref>.bin", "direct ray casting", "water", "SHA-256", "--workers",
    ]:  # fmt: skip
        assert phrase in text, f"`build --help` does not mention {phrase!r}"
