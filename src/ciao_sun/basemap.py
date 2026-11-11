"""The basemap: a pinned Protomaps build, cut to the coverage and exploded to `z/x/y`.

    <build directory>/basemap/{z}/{x}/{y}.mvt

The app draws its map with MapLibre GL over these tiles. They are plain files
because the site serves no Range requests, so a PMTiles archive cannot be read
there (ADR 0002); no archive is shipped.

Two steps, either side of the fetch lockfile:

- `extract` (run by `ciao-sun fetch`) reads the tiles the coverage needs out of
  the remote Protomaps build with byte-range reads, and writes them as a small
  local PMTiles archive: one file, so the lockfile can hash it like any input.
- `explode` (run by `ciao-sun build`) writes that archive's tiles into the
  build directory, one decompressed Mapbox Vector Tile per file.

The tiles are those the coverage's WGS84 bounding box touches, at zooms
`MIN_ZOOM` to `MAX_ZOOM`. 15 is the deepest zoom Protomaps builds; MapLibre
overzooms beyond it. At 10 the whole of Bristol fits a phone screen, and the app
does not zoom out further. Nothing is taken beyond the bounding box, so the app
must keep its map inside the manifest's `basemap.bounds`.

Protomaps stores its tiles gzipped. The files written here are not: a static
host would otherwise have to send `Content-Encoding: gzip` for MapLibre to read
them. Whoever publishes a build may compress in transit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from ciao_sun.coverage import Coverage
from ciao_sun.pmtiles import (
    TILE_TYPE_MVT,
    Archive,
    PMTilesError,
    ReadRange,
    Zxy,
    decompress,
    write_archive,
)

MIN_ZOOM = 10
MAX_ZOOM = 15
DIRECTORY = "basemap"
ATTRIBUTION = "Protomaps © OpenStreetMap"

# Tiles this close together in the archive are read in one request.
_MERGE_GAP_BYTES = 64 * 1024

Bounds = tuple[float, float, float, float]


class BasemapError(Exception):
    """The basemap cannot be cut from this archive."""


@dataclass(frozen=True)
class Basemap:
    """What `explode` wrote."""

    min_zoom: int
    max_zoom: int
    bounds: Bounds  # west, south, east, north: the coverage's bounding box, WGS84
    tile_count: int
    bytes: int
    tileset_version: str | None  # the Protomaps basemap version, e.g. "4.15.1"
    osm_timestamp: str | None  # how fresh the OpenStreetMap data in the tiles is


def _tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    """The Web Mercator tile holding a WGS84 position."""
    n = 1 << z
    x = math.floor((lon + 180.0) / 360.0 * n)
    y = math.floor((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tile_range(coverage: Coverage, z: int) -> tuple[int, int, int, int]:
    """The zoom `z` tiles the coverage's bounding box touches: x0, x1, y0, y1, inclusive."""
    west, south, east, north = coverage.bounds_wgs84()
    x0, y0 = _tile_xy(west, north, z)
    x1, y1 = _tile_xy(east, south, z)
    return x0, x1, y0, y1


def tiles_covering(coverage: Coverage) -> list[Zxy]:
    """Every basemap tile the coverage needs, sorted by zoom, then x, then y."""
    tiles: list[Zxy] = []
    for z in range(MIN_ZOOM, MAX_ZOOM + 1):
        x0, x1, y0, y1 = tile_range(coverage, z)
        tiles += [(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    return tiles


def extract(read: ReadRange, coverage: Coverage, dest: Path) -> None:
    """Cut the coverage's tiles from the archive behind `read` into a PMTiles archive at `dest`.

    `read(offset, length)` returns that range of the remote archive. Only the
    directories on the way to the tiles and the tiles themselves are read,
    neighbouring tiles in one read. The archive's metadata is carried over.
    """
    try:
        archive = Archive(read)
        header = archive.header
        if header.tile_type != TILE_TYPE_MVT:
            raise BasemapError("The archive does not hold Mapbox Vector Tiles.")
        if not header.min_zoom <= MIN_ZOOM <= MAX_ZOOM <= header.max_zoom:
            raise BasemapError(
                f"The archive holds zooms {header.min_zoom} to {header.max_zoom}; "
                f"the basemap needs {MIN_ZOOM} to {MAX_ZOOM}."
            )
        where: dict[Zxy, tuple[int, int]] = {}
        for z, x, y in tiles_covering(coverage):
            found = archive.locate(z, x, y)
            if found is None:
                raise BasemapError(f"The archive has no tile {z}/{x}/{y}.")
            where[z, x, y] = found

        runs: list[tuple[int, int]] = []  # (start, end) of each stretch of the file to read
        for offset, length in sorted(set(where.values())):
            if runs and offset - runs[-1][1] <= _MERGE_GAP_BYTES:
                runs[-1] = (runs[-1][0], max(runs[-1][1], offset + length))
            else:
                runs.append((offset, offset + length))
        blocks: list[tuple[int, bytes]] = []
        for start, end in runs:
            data = read(start, end - start)
            if len(data) != end - start:
                raise BasemapError(
                    f"The archive ends early: wanted {end - start} bytes at {start}, "
                    f"got {len(data)}."
                )
            blocks.append((start, data))
        tiles: dict[Zxy, bytes] = {}
        for zxy, (offset, length) in where.items():
            block_start, data = next(b for b in reversed(blocks) if b[0] <= offset)
            tiles[zxy] = data[offset - block_start : offset - block_start + length]

        write_archive(
            dest,
            tiles,
            metadata=archive.metadata(),
            tile_compression=header.tile_compression,
            bounds=coverage.bounds_wgs84(),
        )
    except PMTilesError as exc:
        raise BasemapError(str(exc)) from exc


def explode(archive_path: Path, coverage: Coverage, out: Path) -> Basemap:
    """Write the coverage's tiles from a local archive to `out/{z}/{x}/{y}.mvt`, decompressed."""
    try:
        archive = Archive.open(archive_path)
        metadata = archive.metadata()
        count = size = 0
        for z, x, y in tiles_covering(coverage):
            stored = archive.tile(z, x, y)
            if stored is None:
                raise BasemapError(
                    f"{archive_path} has no tile {z}/{x}/{y}: it was cut for another coverage. "
                    "Run `ciao-sun fetch` with this coverage first."
                )
            content = decompress(stored, archive.header.tile_compression)
            path = out / str(z) / str(x) / f"{y}.mvt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            count += 1
            size += len(content)
    except (PMTilesError, OSError) as exc:
        raise BasemapError(f"{archive_path}: {exc}") from exc

    def text(key: str) -> str | None:
        value = metadata.get(key)
        return value if isinstance(value, str) and value else None

    return Basemap(
        min_zoom=MIN_ZOOM,
        max_zoom=MAX_ZOOM,
        bounds=coverage.bounds_wgs84(),
        tile_count=count,
        bytes=size,
        tileset_version=text("version"),
        osm_timestamp=text("planetiler:osm:osmosisreplicationtime"),
    )
