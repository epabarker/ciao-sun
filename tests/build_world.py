"""A tiny synthetic set of build inputs, fetched through the real `fetch` from a fake web.

The world is 600 m x 400 m of flat ground at 10 m in Bristol, astride the
boundary between the 1 km squares ST5773 and ST5873 (easting 358000):

    x 357700..358300, y 173300..173700, 1 m cells, inside EA tile ST5570.

- "Ridge Road" runs east-west along y = 173500 from x = 357850 to 358150,
  through nodes 1..4 at x = 357850, 357950, 358050, 358150. Edge 2-3 crosses
  the tile boundary.
- The coverage is x 357905..358095, y 173400..173600, so the Candidates are the
  10 m grid points x = 357910..358090, y = 173490, 173500, 173510: 27 in
  ST5773 and 30 in ST5873. The street runs on beyond the coverage each way.
- A 40 m wall stands 180 m due *true* east of the Candidate P = (358050, 173500).
- A bare-crowned tree, 25 m in the first return and invisible in the last,
  stands 50 m grid north of the Candidate T = (357950, 173510).
- A dozen 20 m posts stand in a row 60 m south of the street.
- A pond lies flat between the street and the posts.
- OS Terrain 50 is flat at 10 m over the 10 km squares ST47, ST57 and ST67,
  except a 310 m ridge along their northern 2 km (y >= 178000), 4.5 km north
  of the street.
- The Protomaps build is the synthetic one of `tests/basemap_world.py`, over the
  coverage.

`tidal_river=True` adds a river north of the street whose first return stands
5 m above the ground, as tidal water does in the EA composite.
"""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import osmium
import rasterio
from affine import Affine
from osmium.osm.mutable import Node, Way
from pyproj import Geod, Transformer

from ciao_sun.coverage import Coverage
from ciao_sun.fetch import Lockfile, Response, fetch
from tests import basemap_world as protomaps

_BNG_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
_WGS84_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
_GEOD = Geod(ellps="WGS84")

X0, X1, Y0, Y1 = 357700, 358300, 173300, 173700
GROUND = 10.0
EYE = GROUND + 1.6
EA_TILE = "ST5570"
STREET_Y = 173500
COVERAGE_BOX = (357905.0, 173400.0, 358095.0, 173600.0)
CANDIDATE_XS = tuple(range(357910, 358100, 10))
CANDIDATE_YS = (173490, 173500, 173510)

P = (358050.0, 173500.0)
WALL_TOP = 40.0
WALL_DISTANCE = 180.0
T = (357950.0, 173510.0)
TREE_TOP = 25.0
POST_TOP = 20.0
RIDGE_TOP = 310.0
RIDGE_SOUTH_EDGE = 178000

OSM_TIMESTAMP = "2026-11-09T21:20:45Z"
SURVEY_DATES = ("2019-02-14", "2021-09-03", "2021-09-04")


def _cells(array: np.ndarray, x0: int, x1: int, y0: int, y1: int, value: float) -> None:
    """Set the 1 m cells covering x0..x1, y0..y1."""
    array[Y1 - y1 : Y1 - y0, x0 - X0 : x1 - X0] = value


def wall_block() -> tuple[int, int, int, int]:
    """The wall's cells (x0, x1, y0, y1): 3 m by 7 m about the point 180 m from P on a true
    bearing of 90 degrees."""
    lon, lat = _BNG_TO_WGS84.transform(*P)
    wall_lon, wall_lat, _ = _GEOD.fwd(lon, lat, 90.0, WALL_DISTANCE)
    x, y = _WGS84_TO_BNG.transform(wall_lon, wall_lat)
    x0, y0 = round(x - 1.5), round(y - 3.5)
    return x0, x0 + 3, y0, y0 + 7


def true_azimuth(origin: tuple[float, float], target: tuple[float, float]) -> float:
    """The true (geodesic) azimuth in degrees from one National Grid point to another."""
    lon0, lat0 = _BNG_TO_WGS84.transform(*origin)
    lon1, lat1 = _BNG_TO_WGS84.transform(*target)
    azimuth, _, _ = _GEOD.inv(lon0, lat0, lon1, lat1)
    return float(azimuth % 360.0)


def _geotiff(data: np.ndarray) -> bytes:
    with rasterio.MemoryFile() as memory:
        with memory.open(
            driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
            dtype="float32", crs="EPSG:27700", transform=Affine(1.0, 0.0, X0, 0.0, -1.0, Y1),
            nodata=-9999.0,
        ) as dst:  # fmt: skip
            dst.write(data.astype("float32"), 1)
        return bytes(memory.read())


def _survey_metadata(scratch: Path) -> bytes:
    """The part of an EA tile's `*_Metadata.gpkg` the build reads: when each survey was flown."""
    path = scratch / "metadata.gpkg"
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE lidar_used_in_merging_process (fid INTEGER, SD_FLOWN TEXT)")
    db.executemany(
        "INSERT INTO lidar_used_in_merging_process VALUES (?, ?)", list(enumerate(SURVEY_DATES))
    )
    db.commit()
    db.close()
    return path.read_bytes()


def _zip(members: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return buffer.getvalue()


def _terrain50_zip() -> bytes:
    """OS's layout: one zip per 10 km square, inside the GB zip, each holding an ASCII grid."""
    heights = np.full((200, 200), GROUND)
    heights[: (180000 - RIDGE_SOUTH_EDGE) // 50, :] = RIDGE_TOP
    rows = "\n".join(" ".join(f"{value:g}" for value in row) for row in heights)
    members = {"docs/licence.txt": b"OGL"}
    for square, west in (("ST47", 340000), ("ST57", 350000), ("ST67", 360000)):
        header = f"ncols 200\nnrows 200\nxllcorner {west}\nyllcorner 170000\ncellsize 50\n"
        grid = _zip({f"{square}.asc": (header + rows + "\n").encode(), f"{square}.prj": b"PROJCS"})
        members[f"data/st/{square.lower()}_OST50GRID_20260701.zip"] = grid
    return _zip(members)


def _osm_extract(path: Path, tidal_river: bool) -> bytes:
    nodes: dict[int, tuple[float, float]] = {
        1: (357850, STREET_Y), 2: (357950, STREET_Y), 3: (358050, STREET_Y), 4: (358150, STREET_Y),
        # the pond
        11: (357960, 173455), 12: (357990, 173455), 13: (357990, 173475), 14: (357960, 173475),
    }  # fmt: skip
    ways: list[tuple[int, list[int], dict[str, str]]] = [
        (100, [1, 2, 3, 4], {"highway": "residential", "name": "Ridge Road"}),
        (101, [11, 12, 13, 14, 11], {"natural": "water"}),
    ]
    if tidal_river:
        nodes |= {
            21: (357800, 173530), 22: (358200, 173530), 23: (358200, 173560), 24: (357800, 173560),
        }  # fmt: skip
        ways.append((102, [21, 22, 23, 24, 21], {"natural": "water", "water": "river"}))
    header = osmium.io.Header()
    header.set("osmosis_replication_timestamp", OSM_TIMESTAMP)
    writer = osmium.SimpleWriter(str(path), header=header, overwrite=True)
    try:
        for node_id, (easting, northing) in sorted(nodes.items()):
            lon, lat = _BNG_TO_WGS84.transform(easting, northing)
            writer.add_node(Node(id=node_id, location=(lon, lat)))
        for way_id, refs, tags in ways:
            writer.add_way(Way(id=way_id, nodes=refs, tags=tags))
    finally:
        writer.close()
    return path.read_bytes()


def coverage(box: tuple[float, float, float, float] = COVERAGE_BOX) -> Coverage:
    west, south, east, north = box
    ring = [(west, south), (east, south), (east, north), (west, north), (west, south)]
    lonlat = [list(_BNG_TO_WGS84.transform(x, y)) for x, y in ring]
    return Coverage.from_geojson({"type": "Polygon", "coordinates": [lonlat]})


class _FakeWeb:
    def __init__(self, bodies: Mapping[str, bytes]) -> None:
        self._bodies = bodies

    def get(self, url: str, headers: Mapping[str, str]) -> Response:
        for ending, body in self._bodies.items():
            if url.endswith(ending):
                return protomaps.serve_range(body, headers)
        return Response(404, [])


def fetch_inputs(root: Path, *, tidal_river: bool = False) -> Lockfile:
    """Write the synthetic inputs under `root` by running the real fetch against a fake web."""
    root.mkdir(parents=True, exist_ok=True)
    ground = np.full((Y1 - Y0, X1 - X0), GROUND)
    last, first = ground.copy(), ground.copy()

    for returns in (last, first):
        _cells(returns, *wall_block(), WALL_TOP)
        for post_x in range(357920, 358090, 15):
            _cells(returns, post_x, post_x + 2, 173438, 173440, POST_TOP)
    _cells(first, 357948, 357953, 173558, 173563, TREE_TOP)
    if tidal_river:
        _cells(first, 357800, 358200, 173530, 173560, GROUND + 5.0)

    scratch = root / "scratch"
    scratch.mkdir(exist_ok=True)
    survey = _survey_metadata(scratch)
    osm = _osm_extract(scratch / "extract.osm.pbf", tidal_river)
    bodies = {
        f"/lidar_composite_last_return_dsm/2022/1/{EA_TILE}": _zip(
            {f"{EA_TILE}_LAST_RETURN_DSM_1m.tif": _geotiff(last),
             f"{EA_TILE}_Metadata.gpkg": survey}
        ),
        f"/lidar_composite_dtm/2022/1/{EA_TILE}": _zip({f"{EA_TILE}_DTM_1m.tif": _geotiff(ground)}),
        f"/lidar_composite_first_return_dsm/2022/1/{EA_TILE}": _zip(
            {f"{EA_TILE}_FIRST_RETURN_DSM_1m.tif": _geotiff(first)}
        ),
        "/products/Terrain50": json.dumps({"id": "Terrain50", "version": "2026-07"}).encode(),
        "&redirect": _terrain50_zip(),
        ".osm.pbf": osm,
        "/builds.json": protomaps.builds_json(),
        f"/{protomaps.BUILD}.pmtiles": protomaps.archive_bytes(coverage().bounds_wgs84()),
    }  # fmt: skip
    clock = iter(range(0, 10**9, 2))
    return fetch(
        coverage(),
        root / "inputs",
        osm_date="261110",
        client=_FakeWeb(bodies),
        osm_region="europe/united-kingdom/england/bristol",
        clock=lambda: float(next(clock)),
        sleep=lambda seconds: None,
        now=lambda: datetime(2026, 11, 11, 9, 0, tzinfo=UTC),
    )
