"""OS Terrain 50, read straight from the Great Britain zip that `ciao-sun fetch` caches.

OS ships one zip holding a zip per 10 km square
(`data/st/st57_OST50GRID_20260701.zip`), each holding that square's ESRI ASCII
grid (`ST57.asc`): 200 x 200 heights in metres at the centres of 50 m cells.
`load_terrain50` mosaics the squares that touch the area asked for; squares OS
does not publish (open sea) are left as no data.
"""

from __future__ import annotations

import io
import math
import re
import zipfile
from pathlib import Path

import numpy as np
from affine import Affine
from rasterio.crs import CRS

from ciao_sun.raster import NODATA_BELOW, RasterGrid
from ciao_sun.tiles import square_origin

CELL_M = 50
_SQUARE_M = 10_000
_SQUARE_ZIP = re.compile(r"(?:^|/)([A-Za-z]{2})(\d)(\d)_OST50GRID_\d+\.zip$")
_HEADER_KEYS = ("ncols", "nrows", "xllcorner", "yllcorner", "cellsize", "nodata_value")

Bounds = tuple[float, float, float, float]


class Terrain50Error(ValueError):
    """The Terrain 50 zip is not laid out, or gridded, as OS publishes it."""


def load_terrain50(gb_zip: Path, bounds: Bounds) -> RasterGrid:
    """Terrain 50 over every 10 km square that touches `bounds` (minx, miny, maxx, maxy).

    The result is in EPSG:27700 and NaN where there is no data.
    """
    minx, miny, maxx, maxy = bounds
    west = math.floor(minx / _SQUARE_M) * _SQUARE_M
    south = math.floor(miny / _SQUARE_M) * _SQUARE_M
    east = math.ceil(maxx / _SQUARE_M) * _SQUARE_M
    north = math.ceil(maxy / _SQUARE_M) * _SQUARE_M
    data = np.full(((north - south) // CELL_M, (east - west) // CELL_M), np.nan, dtype="float32")

    try:
        with zipfile.ZipFile(gb_zip) as archive:
            for name in sorted(archive.namelist()):
                match = _SQUARE_ZIP.search(name)
                if match is None:
                    continue
                try:
                    e100k, n100k = square_origin(match[1])
                except ValueError:
                    continue
                x0 = e100k + int(match[2]) * _SQUARE_M
                y0 = n100k + int(match[3]) * _SQUARE_M
                if x0 >= east or x0 + _SQUARE_M <= west or y0 >= north or y0 + _SQUARE_M <= south:
                    continue
                heights = _read_square(archive.read(name), name, x0, y0)
                row = (north - y0 - _SQUARE_M) // CELL_M
                col = (x0 - west) // CELL_M
                data[row : row + heights.shape[0], col : col + heights.shape[1]] = heights
    except (OSError, zipfile.BadZipFile) as exc:
        raise Terrain50Error(f"Cannot read Terrain 50 zip {gb_zip}: {exc}") from exc

    return RasterGrid(
        data=data,
        transform=Affine(CELL_M, 0.0, west, 0.0, -CELL_M, north),
        crs=CRS.from_epsg(27700),
    )


def _read_square(square_zip: bytes, name: str, x0: int, y0: int) -> np.ndarray:
    with zipfile.ZipFile(io.BytesIO(square_zip)) as square:
        grids = [member for member in square.namelist() if member.lower().endswith(".asc")]
        if len(grids) != 1:
            raise Terrain50Error(f"{name} should hold one .asc grid, not {len(grids)}.")
        tokens = square.read(grids[0]).split()
    header: dict[str, float] = {}
    while tokens and tokens[0].decode("ascii", "replace").lower() in _HEADER_KEYS:
        header[tokens[0].decode("ascii").lower()] = float(tokens[1])
        tokens = tokens[2:]
    cells = _SQUARE_M // CELL_M
    for key, value in (
        ("ncols", cells), ("nrows", cells), ("xllcorner", x0), ("yllcorner", y0),
        ("cellsize", CELL_M),
    ):  # fmt: skip
        if header.get(key) != value:
            raise Terrain50Error(f"{name}: {key} is {header.get(key)}, expected {value}.")
    if len(tokens) != cells * cells:
        raise Terrain50Error(f"{name}: {len(tokens)} heights, expected {cells * cells}.")
    heights = np.array(tokens, dtype="float32").reshape(cells, cells)
    heights[heights < NODATA_BELOW] = np.nan
    if "nodata_value" in header:
        heights[heights == np.float32(header["nodata_value"])] = np.nan
    return heights
