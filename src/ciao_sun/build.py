"""`ciao-sun build`: fetched inputs -> one build directory of f1 tiles and a manifest.

    <out>/f1/<build>/manifest.json
    <out>/f1/<build>/tiles/<grid ref>.bin
    <out>/f1/<build>/fixtures/              golden fixtures, when given a query set

`build` reads everything through the fetch lockfile (`fetch.read_lockfile`),
and makes a tile for every 1 km square the coverage touches that has a
Candidate or a walk edge. Tile by tile, on `workers` processes:

1. mosaic the EA last-return DSM, first-return DSM and DTM, straight from
   their zips, over the square plus the 3 km near reach;
2. Candidates and walk graph (`candidates.build_tile`), Candidates only from
   inside the coverage;
3. the crown-envelope surface (`surface.crown_envelope_surface`);
4. Horizon profiles (`horizon_precompute.cast_tile`), which also counts the
   Candidates the water guard is looking for;
5. write the tile, read it back through the codec and run the direct-ray
   profile check on it (`build_checks.check_tile_profiles`).

The build id is the UTC date plus the first letter not yet used under
`<out>/f1/`. Tiles are written to `<build>.partial/` and the directory takes its
name only once both build checks have passed and the manifest and the golden
fixtures (`reference.fixtures`) are written, so a directory named by a build id
is always a whole, checked build. A failed build
leaves its `.partial` directory behind for inspection; the next build removes it.

Tiles depend only on the inputs, never on the build id, the clock or
`workers`: the same inputs give byte-identical tiles.

`check_profiles` reruns the direct-ray check on a finished build directory.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import re
import shutil
import sqlite3
import string
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import shapely
from affine import Affine
from rasterio.crs import CRS

from ciao_sun.build_checks import BuildCheckError, Tolerances, check_tile_profiles
from ciao_sun.candidates import WalkNetwork, build_tile, load_walk_network
from ciao_sun.coverage import Coverage
from ciao_sun.fetch import EA_PRODUCTS, Lockfile, read_lockfile
from ciao_sun.horizon_precompute import (
    FAR_REACH_M,
    NEAR_REACH_M,
    TileWorld,
    cast_tile,
    precompute_tiles,
)
from ciao_sun.manifest import manifest_document, read_manifest, write_manifest
from ciao_sun.raster import RasterGrid, load_mosaic
from ciao_sun.reference.fixtures import SetQuery, write_fixtures
from ciao_sun.surface import (
    BuildingFootprints,
    crown_envelope_surface,
    read_building_footprints,
    read_water_areas,
)
from ciao_sun.terrain50 import load_terrain50
from ciao_sun.tile_codec import FORMAT, read_tile, write_tile
from ciao_sun.tiles import KM, grid_ref_of, grid_ref_origin

_BNG = CRS.from_epsg(27700)
_SURVEY_LAYER = "lidar_used_in_merging_process"
_SURVEY_COLUMN = "SD_FLOWN"

Bounds = tuple[float, float, float, float]


class BuildError(Exception):
    """The build cannot run on these inputs."""


def _silent(message: str) -> None:
    return None


# --- What each worker process holds ------------------------------------------


@dataclass(frozen=True)
class _Job:
    """Everything a worker needs to find its inputs; small, hashable and picklable."""

    inputs_root: Path
    coverage_json: str
    tiles_dir: Path
    far_reach_m: float
    tolerances: Tolerances


class _Inputs:
    """A job's inputs, each loaded the first time a tile needs it and then kept."""

    def __init__(self, job: _Job) -> None:
        self.job = job
        self.lock = read_lockfile(job.inputs_root)
        self.polygon = Coverage.from_geojson(json.loads(job.coverage_json)).polygon_bng()
        minx, miny, maxx, maxy = self.polygon.bounds
        self._near_bounds = (
            minx - NEAR_REACH_M - KM, miny - NEAR_REACH_M - KM,
            maxx + NEAR_REACH_M + KM, maxy + NEAR_REACH_M + KM,
        )  # fmt: skip
        self._far_bounds = (
            minx - job.far_reach_m - KM, miny - job.far_reach_m - KM,
            maxx + job.far_reach_m + KM, maxy + job.far_reach_m + KM,
        )  # fmt: skip

    def _only(self, kind: str) -> Path:
        (entry,) = [entry for entry in self.lock.inputs if entry.kind == kind]
        return self.lock.path_of(entry)

    @functools.cached_property
    def network(self) -> WalkNetwork:
        return load_walk_network(self._only("osm"))

    @functools.cached_property
    def footprints(self) -> BuildingFootprints:
        return read_building_footprints(self._only("osm"), _BNG, self._near_bounds)

    @functools.cached_property
    def water(self) -> BuildingFootprints:
        return read_water_areas(self._only("osm"), _BNG, self._near_bounds)

    @functools.cached_property
    def terrain50(self) -> RasterGrid:
        return load_terrain50(self._only("terrain50"), self._far_bounds)

    @functools.cached_property
    def rasters(self) -> dict[str, list[tuple[str, Bounds]]]:
        """Per EA product, each GeoTIFF inside its zip as a GDAL path, with its extent."""
        import rasterio

        found: dict[str, list[tuple[str, Bounds]]] = {kind: [] for kind in EA_PRODUCTS}
        for entry in self.lock.inputs:
            if entry.kind not in EA_PRODUCTS or entry.absent:
                continue
            archive = self.lock.path_of(entry)
            with zipfile.ZipFile(archive) as opened:
                members = [name for name in opened.namelist() if name.lower().endswith(".tif")]
            for member in sorted(members):
                path = f"/vsizip/{archive.resolve()}/{member}"
                with rasterio.open(path) as source:
                    if source.crs != _BNG:
                        raise BuildError(f"{archive}: {member} is in {source.crs}, not EPSG:27700.")
                    found[entry.kind].append((path, tuple(source.bounds)))
        return found

    def contains(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return np.asarray(shapely.contains_xy(self.polygon, x, y), dtype=bool)


@functools.lru_cache(maxsize=1)
def _inputs(job: _Job) -> _Inputs:
    return _Inputs(job)


def _overlaps(a: Bounds, b: Bounds) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@dataclass(frozen=True)
class _TileRasters:
    last_return: RasterGrid
    first_return: RasterGrid
    dtm: RasterGrid


def _tile_rasters(inputs: _Inputs, grid_ref: str) -> _TileRasters:
    """The three EA mosaics over a square plus the near reach, on one shared grid."""
    west, south = grid_ref_origin(grid_ref)
    wanted: Bounds = (
        west - NEAR_REACH_M, south - NEAR_REACH_M,
        west + KM + NEAR_REACH_M, south + KM + NEAR_REACH_M,
    )  # fmt: skip
    # Clip to what the last return covers, on whole metres, so a small extract
    # is not padded out to 7 km of nothing.
    touching = [bounds for _, bounds in inputs.rasters["dsm"] if _overlaps(bounds, wanted)]
    if touching:
        window: Bounds = (
            max(wanted[0], math.floor(min(b[0] for b in touching))),
            max(wanted[1], math.floor(min(b[1] for b in touching))),
            min(wanted[2], math.ceil(max(b[2] for b in touching))),
            min(wanted[3], math.ceil(max(b[3] for b in touching))),
        )
    else:
        window = (west, south, west + 1.0, south + 1.0)

    def mosaic(kind: str) -> RasterGrid:
        paths = [path for path, bounds in inputs.rasters[kind] if _overlaps(bounds, window)]
        if not paths:
            shape = (round(window[3] - window[1]), round(window[2] - window[0]))
            return RasterGrid(
                data=np.full(shape, np.nan, dtype="float32"),
                transform=Affine(1.0, 0.0, window[0], 0.0, -1.0, window[3]),
                crs=_BNG,
            )
        return load_mosaic(paths, bounds=window)

    return _TileRasters(mosaic("dsm"), mosaic("first_return_dsm"), mosaic("dtm"))


def _surface(inputs: _Inputs, rasters: _TileRasters) -> RasterGrid:
    return crown_envelope_surface(
        rasters.last_return, rasters.first_return, rasters.dtm, inputs.footprints
    )


@dataclass(frozen=True)
class _TileReport:
    """What a worker sends back about one square. `candidates` is None if it has no tile."""

    candidates: int | None = None
    water_candidates: int = 0
    candidates_checked: int = 0
    profile_failures: tuple[str, ...] = ()


def _build_one(job: _Job, grid_ref: str) -> _TileReport:
    inputs = _inputs(job)
    rasters = _tile_rasters(inputs, grid_ref)
    outline = build_tile(
        inputs.network, grid_ref, rasters.last_return, rasters.dtm, within=inputs.contains
    )
    if outline is None:
        return _TileReport()
    surface = _surface(inputs, rasters)
    water = RasterGrid(
        data=inputs.water.buffered_mask(surface, 0.0).astype("float32"),
        transform=surface.transform,
        crs=surface.crs,
    )
    world = TileWorld(
        surface=surface, dtm=rasters.dtm, terrain50=inputs.terrain50,
        x=outline.easting, y=outline.northing, water=water,
    )  # fmt: skip
    horizons = cast_tile(world, far_reach_m=job.far_reach_m)
    path = write_tile(outline.with_profiles(horizons.codes), job.tiles_dir)
    check = check_tile_profiles(
        read_tile(path), surface, rasters.dtm, inputs.terrain50,
        far_reach_m=job.far_reach_m, tolerances=job.tolerances,
    )  # fmt: skip
    return _TileReport(
        candidates=len(outline.easting),
        water_candidates=int(horizons.set_by_water.sum()),
        candidates_checked=check.candidates_checked,
        profile_failures=check.failures,
    )


def _check_one(job: _Job, grid_ref: str) -> _TileReport:
    inputs = _inputs(job)
    rasters = _tile_rasters(inputs, grid_ref)
    check = check_tile_profiles(
        read_tile(job.tiles_dir / f"{grid_ref}.bin"), _surface(inputs, rasters), rasters.dtm,
        inputs.terrain50, far_reach_m=job.far_reach_m, tolerances=job.tolerances,
    )  # fmt: skip
    return _TileReport(candidates_checked=check.candidates_checked, profile_failures=check.failures)


# --- The build ----------------------------------------------------------------


def grid_refs_touching(coverage: Coverage) -> list[str]:
    """The 1 km squares a coverage touches, sorted."""
    polygon = coverage.polygon_bng()
    minx, miny, maxx, maxy = polygon.bounds
    return sorted(
        grid_ref_of(i * KM, j * KM)
        for i in range(math.floor(minx / KM), math.floor(maxx / KM) + 1)
        for j in range(math.floor(miny / KM), math.floor(maxy / KM) + 1)
        if polygon.intersects(shapely.box(i * KM, j * KM, (i + 1) * KM, (j + 1) * KM))
    )


def _next_build_id(format_dir: Path, today: date) -> str:
    stamp = today.strftime("%Y%m%d")
    for letter in string.ascii_lowercase:
        if not (format_dir / f"{stamp}{letter}").exists():
            return f"{stamp}{letter}"
    raise BuildError(f"{format_dir} already holds 26 builds dated {stamp}.")


def osm_replication_timestamp(osm_pbf: Path) -> str | None:
    """The replication timestamp in an OSM extract's header: how fresh its data is."""
    import osmium

    reader = osmium.io.Reader(str(osm_pbf))
    try:
        return reader.header().get("osmosis_replication_timestamp") or None
    finally:
        reader.close()


def lidar_survey_years(lock: Lockfile) -> list[int]:
    """The years the LIDAR in the fetched EA tiles was flown.

    Each EA tile zip carries a `*_Metadata.gpkg` whose `lidar_used_in_merging_process`
    layer dates every survey merged into the composite (`SD_FLOWN`). Where no
    tile has one, the composite's own year stands in.
    """
    years: set[int] = set()
    for entry in lock.inputs:
        if entry.kind != "dsm" or entry.absent:
            continue
        with zipfile.ZipFile(lock.path_of(entry)) as archive:
            for member in archive.namelist():
                if member.lower().endswith(".gpkg"):
                    years |= _survey_years(archive.read(member))
    if not years:
        years = {int(entry.version) for entry in lock.inputs if entry.kind in EA_PRODUCTS}
    return sorted(years)


def _survey_years(geopackage: bytes) -> set[int]:
    # A GeoPackage is an SQLite database, and SQLite reads only from a file.
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "metadata.gpkg"
        path.write_bytes(geopackage)
        db = sqlite3.connect(path)
        try:
            rows = db.execute(f'SELECT DISTINCT "{_SURVEY_COLUMN}" FROM "{_SURVEY_LAYER}"')
            flown = [str(row[0]) for row in rows if row[0] is not None]
        except sqlite3.Error:
            return set()
        finally:
            db.close()
    return {int(year) for text in flown for year in re.findall(r"(?<!\d)(?:19|20)\d\d(?!\d)", text)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raise_on_failures(reports: dict[str, _TileReport], tolerances: Tolerances) -> None:
    problems: list[str] = []
    water = {ref: r.water_candidates for ref, r in reports.items() if r.water_candidates}
    if sum(water.values()) > tolerances.water_candidates_allowed:
        where = ", ".join(f"{ref} ({count})" for ref, count in sorted(water.items()))
        problems.append(
            f"Water guard: {sum(water.values())} Candidates have a horizon set by a water "
            f"cell; {tolerances.water_candidates_allowed} allowed. Tiles: {where}."
        )
    failures = [line for ref in sorted(reports) for line in reports[ref].profile_failures]
    if failures:
        shown = "\n  ".join(failures[:20])
        more = f"\n  ... and {len(failures) - 20} more" if len(failures) > 20 else ""
        problems.append(
            f"Direct-ray profile check: {len(failures)} Candidates disagree with direct "
            f"ray casting:\n  {shown}{more}"
        )
    if problems:
        raise BuildCheckError("\n".join(problems))


def build(
    coverage: Coverage,
    inputs: Path,
    out: Path,
    *,
    workers: int = 1,
    today: date | None = None,
    far_reach_m: float = FAR_REACH_M,
    tolerances: Tolerances | None = None,
    queries: Sequence[SetQuery] | None = None,
    report: Callable[[str], None] = _silent,
) -> Path:
    """Build `coverage` from the fetched `inputs` into a new build directory under `out`.

    Returns `<out>/f1/<build>/`. Raises BuildCheckError, and leaves no build
    directory, if the direct-ray profile check or the water guard fails.
    `today` is the UTC date the build id is cut from. `queries` is the query
    set whose golden fixtures go in the build's `fixtures/`; None writes none.
    """
    tolerances = tolerances or Tolerances()
    lock = read_lockfile(inputs)
    if not lock.coverage.polygon_bng().buffer(0.01).covers(coverage.polygon_bng()):
        raise BuildError(
            f"The coverage reaches outside the one {inputs} was fetched for. "
            "Run `ciao-sun fetch` with this coverage first."
        )
    for entry in lock.inputs:
        if not entry.absent and not lock.path_of(entry).is_file():
            raise BuildError(f"{lock.path_of(entry)} is in the lockfile but missing. Fetch again.")

    format_dir = out / f"f{FORMAT}"
    build_id = _next_build_id(format_dir, today or datetime.now(UTC).date())
    build_dir = format_dir / build_id
    partial = format_dir / f"{build_id}.partial"
    if partial.exists():
        shutil.rmtree(partial)
    tiles_dir = partial / "tiles"
    tiles_dir.mkdir(parents=True)

    job = _Job(
        inputs_root=inputs.resolve(),
        coverage_json=json.dumps(coverage.geometry, sort_keys=True),
        tiles_dir=tiles_dir.resolve(),
        far_reach_m=far_reach_m,
        tolerances=tolerances,
    )
    grid_refs = grid_refs_touching(coverage)
    report(f"build {build_id}: {len(grid_refs)} squares on {workers} workers")
    reports = precompute_tiles(grid_refs, functools.partial(_build_one, job), workers=workers)
    _raise_on_failures(reports, tolerances)

    tiles = {
        grid_ref: {
            "bytes": (tiles_dir / f"{grid_ref}.bin").stat().st_size,
            "sha256": _sha256(tiles_dir / f"{grid_ref}.bin"),
            "candidates": tile_report.candidates,
        }
        for grid_ref, tile_report in reports.items()
        if tile_report.candidates is not None
    }
    checks = tolerances.as_manifest()
    checks["profile"]["candidatesChecked"] = sum(r.candidates_checked for r in reports.values())
    checks["waterGuard"]["candidatesFound"] = sum(r.water_candidates for r in reports.values())
    (osm,) = [entry for entry in lock.inputs if entry.kind == "osm"]
    write_manifest(
        partial,
        manifest_document(
            build_id=build_id,
            inputs=lock.inputs,
            osm_timestamp=osm_replication_timestamp(lock.path_of(osm)),
            lidar_survey_years=lidar_survey_years(lock),
            coverage=coverage,
            horizon={"nearReachM": NEAR_REACH_M, "farReachM": far_reach_m},
            tiles=tiles,
            build_checks=checks,
        ),
    )
    if queries is not None:
        write_fixtures(partial, queries, report)
    partial.rename(build_dir)
    report(
        f"build {build_id}: {len(tiles)} tiles, "
        f"{sum(r.candidates or 0 for r in reports.values())} Candidates, in {build_dir}"
    )
    return build_dir


def check_profiles(
    build_dir: Path, inputs: Path, *, workers: int = 1, tolerances: Tolerances | None = None
) -> int:
    """Rerun the direct-ray profile check on a finished build, against the inputs it was made from.

    Returns the number of Candidates checked; raises BuildCheckError if any
    disagrees with direct ray casting.
    """
    tolerances = tolerances or Tolerances()
    manifest = read_manifest(build_dir)
    job = _Job(
        inputs_root=inputs.resolve(),
        coverage_json=json.dumps(manifest["coverage"], sort_keys=True),
        tiles_dir=(build_dir / "tiles").resolve(),
        far_reach_m=float(manifest["horizon"]["farReachM"]),
        tolerances=tolerances,
    )
    grid_refs: Sequence[str] = sorted(manifest["tiles"])
    reports = precompute_tiles(grid_refs, functools.partial(_check_one, job), workers=workers)
    _raise_on_failures(reports, tolerances)
    return sum(r.candidates_checked for r in reports.values())
