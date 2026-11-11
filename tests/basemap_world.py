"""A tiny synthetic Protomaps build: the archive and the list of builds, as the web serves them.

The archive holds, at every zoom 0..15, the tiles over a place plus a ring of
`RING` tiles around them. Each tile is the gzipped text `mvt z/x/y`, so a test
can tell which tile it is looking at.
"""

from __future__ import annotations

import gzip
import json
import tempfile
from collections.abc import Mapping
from pathlib import Path

from pyproj import Transformer

from ciao_sun.fetch import Response
from ciao_sun.pmtiles import COMPRESSION_GZIP, write_archive

BUILD = "20260811"
TILESET_VERSION = "4.15.1"
OSM_TIMESTAMP = "2026-08-11T04:00:00Z"
BUILDS_URL = "https://build-metadata.protomaps.dev/builds.json"
ARCHIVE_URL = f"https://build.protomaps.com/{BUILD}.pmtiles"
RING = 2

# Four builds as Protomaps lists them: 20260811 is the last of 4.15.1, and 4.15.2
# is still being built every day.
BUILDS = [
    {"key": "20260722.pmtiles", "size": 136951449547, "version": "4.15.0"},
    {"key": "20260810.pmtiles", "size": 137295889000, "version": "4.15.1"},
    {"key": f"{BUILD}.pmtiles", "size": 137295889397, "version": TILESET_VERSION},
    {"key": "20261110.pmtiles", "size": 139416504818, "version": "4.15.2"},
    {"key": "20261111.pmtiles", "size": 139406074356, "version": "4.15.2"},
]

_TO_WEB_MERCATOR = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
_HALF_WORLD_M = 20037508.342789244

Bounds = tuple[float, float, float, float]


def tile_of(lon: float, lat: float, z: int) -> tuple[int, int]:
    """The `x, y` of the zoom `z` tile holding a position, by way of Web Mercator metres."""
    mx, my = _TO_WEB_MERCATOR.transform(lon, lat)
    size = 2 * _HALF_WORLD_M / (1 << z)
    return int((mx + _HALF_WORLD_M) // size), int((_HALF_WORLD_M - my) // size)


def tiles_over(bounds: Bounds, zooms: range, ring: int = 0) -> set[tuple[int, int, int]]:
    """Every tile at `zooms` touching WGS84 `bounds` (west, south, east, north), plus a ring."""
    west, south, east, north = bounds
    found = set()
    for z in zooms:
        x0, y0 = tile_of(west, north, z)
        x1, y1 = tile_of(east, south, z)
        last = (1 << z) - 1
        for x in range(max(0, x0 - ring), min(last, x1 + ring) + 1):
            for y in range(max(0, y0 - ring), min(last, y1 + ring) + 1):
                found.add((z, x, y))
    return found


def tile_text(z: int, x: int, y: int) -> bytes:
    """What the synthetic tile `z/x/y` holds once decompressed."""
    return f"mvt {z}/{x}/{y}".encode()


def archive_bytes(bounds: Bounds, *, without: tuple[int, int, int] | None = None) -> bytes:
    """The synthetic build over `bounds`, optionally lacking one tile."""
    tiles = {
        zxy: gzip.compress(tile_text(*zxy), mtime=0)
        for zxy in tiles_over(bounds, range(0, 16), RING)
        if zxy != without
    }
    metadata = {
        "name": "Protomaps Basemap",
        "version": TILESET_VERSION,
        "planetiler:osm:osmosisreplicationtime": OSM_TIMESTAMP,
        "attribution": '<a href="https://www.openstreetmap.org/copyright">&copy; OpenStreetMap</a>',
    }
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "build.pmtiles"
        write_archive(
            path, tiles, metadata=metadata, tile_compression=COMPRESSION_GZIP,
            bounds=(-180.0, -85.0511287, 180.0, 85.0511287),
        )  # fmt: skip
        return path.read_bytes()


def builds_json() -> bytes:
    return json.dumps(BUILDS).encode()


def serve_range(body: bytes, headers: Mapping[str, str]) -> Response:
    """Serve `body` as a server that honours `Range: bytes=a-b` does."""
    wanted = headers.get("Range")
    if not wanted:
        return Response(200, iter([body]))
    first, _, last = wanted.removeprefix("bytes=").partition("-")
    return Response(206, iter([body[int(first) : int(last) + 1 if last else None]]))
