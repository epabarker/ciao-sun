"""Raster mosaic, clip, alignment and sampling helpers.

DSM/DTM tiles are merged on demand into a single in-memory grid clipped to the
area actually needed (home +/- radius +/- max_ray), never a full 5 km tile.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from affine import Affine
from rasterio.crs import CRS

# EA nodata is typically -9999; anything below this is masked to NaN.
NODATA_BELOW = -100.0

# EA's composite tiles declare their nodata tag as the float32 minimum
# (-3.4028234663852886e+38). rasterio.merge can't safely round-trip that exact
# value through its own dtype check (it warns "cannot safely be represented"
# and silently falls back), which in practice makes it fill the whole output
# with 0 instead of real elevation data. Passing this override makes merge use
# the documented EA sentinel instead, which *is* representable; NODATA_BELOW
# then masks it (and it) to NaN as normal.
_MERGE_NODATA_OVERRIDE = -9999.0


@dataclass(frozen=True)
class RasterGrid:
    """A single-band float32 raster in a projected CRS, NaN where there is no data."""

    data: np.ndarray
    transform: Affine
    crs: CRS

    @property
    def shape(self) -> tuple[int, int]:
        return (int(self.data.shape[0]), int(self.data.shape[1]))

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        rows, cols = self.shape
        x0, y0 = self.transform * (0, 0)
        x1, y1 = self.transform * (cols, rows)
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


class TilesNotFoundError(FileNotFoundError):
    """Raised when no tiles are found, or none cover the requested area of interest."""


def find_tiles(tile_dir: Path) -> list[Path]:
    """All GeoTIFFs under tile_dir.

    EA deliveries put one .tif per tile in its own subdirectory
    (e.g. data/dtm/lidar_composite_dtm-2022-1-ST57ne/ST57ne_DTM_1m.tif), so this
    searches recursively rather than assuming a flat layout.
    """
    tile_dir = Path(tile_dir)
    if not tile_dir.exists():
        return []
    return sorted(tile_dir.rglob("*.tif"))


def load_mosaic(
    paths: list[Path],
    bounds: tuple[float, float, float, float] | None = None,
) -> RasterGrid:
    """Merge tiles into one raster, masking nodata to NaN.

    `bounds` (minx, miny, maxx, maxy), when given, restricts the merge to that
    window via rasterio's windowed reads, so full 5 km tiles are never fully
    materialised for a small query.
    """
    import rasterio
    from rasterio.merge import merge

    if not paths:
        raise TilesNotFoundError(
            "No LIDAR tiles found. See the README for the manual download steps "
            "from https://environment.data.gov.uk/ (search 'LIDAR' -> "
            "'Download the Survey Data'), and check --config / data directory paths."
        )
    srcs = [rasterio.open(p) for p in paths]
    try:
        crs = srcs[0].crs
        for s in srcs:
            if s.crs != crs:
                raise ValueError(f"Tile CRS mismatch: {s.name} is {s.crs}, expected {crs}")
        arr, transform = merge(srcs, bounds=bounds, nodata=_MERGE_NODATA_OVERRIDE)
    finally:
        for s in srcs:
            s.close()
    if arr.shape[1] == 0 or arr.shape[2] == 0:
        raise TilesNotFoundError(
            f"No tile data covers the requested area {bounds}. "
            "Run `ciao-sun tiles` for this AOI and check all listed tiles are downloaded."
        )
    band = arr[0].astype("float32")
    band[band < NODATA_BELOW] = np.nan
    return RasterGrid(data=band, transform=transform, crs=crs)


def assert_aligned(a: RasterGrid, b: RasterGrid) -> None:
    """Raise a clear error if two grids are not on the same pixel grid."""
    if a.transform != b.transform or a.shape != b.shape:
        raise ValueError(
            "DSM and DTM mosaics are not aligned "
            f"(transform {a.transform} vs {b.transform}, shape {a.shape} vs {b.shape}). "
            "Both should be built from the same-resolution EA tiles over the same AOI."
        )


def sample(grid: RasterGrid, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Nearest-neighbour sample of `grid` at projected coordinates `x`, `y`.

    Mirrors GDAL/rasterio's own pixel-index convention: the affine inverse gives
    a corner-based fractional (col, row), and flooring it selects the containing
    pixel -- which, on a regular grid, is exactly the nearest-centre pixel.
    Points outside the grid extent return NaN.
    """
    x = np.asarray(x, dtype="float64")
    y = np.asarray(y, dtype="float64")
    inv = ~grid.transform
    col_f = inv.a * x + inv.b * y + inv.c
    row_f = inv.d * x + inv.e * y + inv.f
    col_i = np.floor(col_f).astype(np.int64)
    row_i = np.floor(row_f).astype(np.int64)
    rows, cols = grid.shape
    ok = (row_i >= 0) & (row_i < rows) & (col_i >= 0) & (col_i < cols)
    out = np.full(x.shape, np.nan, dtype="float32")
    out[ok] = grid.data[row_i[ok], col_i[ok]]
    return out


def sample_bilinear(grid: RasterGrid, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Bilinear sample of `grid` at projected coordinates `x`, `y`.

    Cell values are heights at cell centres, as in OS Terrain 50. A point is
    interpolated between the four centres around it; it returns NaN when any of
    the four is off the grid or has no data.
    """
    x = np.asarray(x, dtype="float64")
    y = np.asarray(y, dtype="float64")
    inv = ~grid.transform
    col_f = inv.a * x + inv.b * y + inv.c - 0.5
    row_f = inv.d * x + inv.e * y + inv.f - 0.5
    col_i = np.floor(col_f).astype(np.int64)
    row_i = np.floor(row_f).astype(np.int64)
    rows, cols = grid.shape
    ok = (row_i >= 0) & (row_i < rows - 1) & (col_i >= 0) & (col_i < cols - 1)
    r, c = row_i[ok], col_i[ok]
    fx, fy = col_f[ok] - c, row_f[ok] - r
    data = grid.data
    out = np.full(x.shape, np.nan, dtype="float64")
    out[ok] = (
        data[r, c] * (1 - fx) * (1 - fy)
        + data[r, c + 1] * fx * (1 - fy)
        + data[r + 1, c] * (1 - fx) * fy
        + data[r + 1, c + 1] * fx * fy
    )
    return out


def cache_key(paths: list[Path], bounds: tuple[float, float, float, float]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        st = p.stat()
        h.update(f"{p}:{st.st_mtime_ns}:{st.st_size}".encode())
    h.update(str(tuple(round(b, 1) for b in bounds)).encode())
    return h.hexdigest()[:16]


def load_mosaic_cached(
    paths: list[Path],
    bounds: tuple[float, float, float, float],
    cache_dir: Path,
    label: str,
) -> RasterGrid:
    """Like `load_mosaic`, but memoises the clipped result as a .npz under cache_dir."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = cache_key(paths, bounds) if paths else "empty"
    cache_file = cache_dir / f"{label}_{key}.npz"
    if cache_file.exists():
        npz = np.load(cache_file, allow_pickle=False)
        transform = Affine(*npz["transform"].tolist())
        crs = CRS.from_user_input(str(npz["crs"].item()))
        return RasterGrid(data=npz["data"], transform=transform, crs=crs)
    grid = load_mosaic(paths, bounds=bounds)
    np.savez_compressed(
        cache_file,
        data=grid.data,
        transform=np.array(tuple(grid.transform)[:6], dtype="float64"),
        crs=np.array(grid.crs.to_string()),
    )
    return grid
