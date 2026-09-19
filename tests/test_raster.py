"""Raster sampling correctness: HANDOFF.md #6, test group 5."""

from __future__ import annotations

import numpy as np
from affine import Affine
from rasterio.crs import CRS

from sunspot.raster import RasterGrid, sample

# 4x4 grid, pixel size 1, corner origin (0, 4): cell (row, col) covers
# x in [col, col+1), y in (4-row-1, 4-row], i.e. cell (0, 0) covers x in [0, 1),
# y in (3, 4], centre (0.5, 3.5).
KNOWN = np.array(
    [
        [0.0, 1.0, 2.0, 3.0],
        [10.0, 11.0, 12.0, 13.0],
        [20.0, 21.0, 22.0, 23.0],
        [30.0, 31.0, 32.0, 33.0],
    ],
    dtype="float32",
)
TRANSFORM = Affine(1.0, 0.0, 0.0, 0.0, -1.0, 4.0)
GRID = RasterGrid(data=KNOWN, transform=TRANSFORM, crs=CRS.from_epsg(27700))


def test_sample_at_cell_centres():
    # cell (row=1, col=2) covers x in [2,3), y in (2,3], centre (2.5, 2.5), value 12.
    out = sample(GRID, np.array([2.5]), np.array([2.5]))
    assert out[0] == 12.0
    # cell (row=0, col=0), centre (0.5, 3.5), value 0.
    out = sample(GRID, np.array([0.5]), np.array([3.5]))
    assert out[0] == 0.0
    # cell (row=3, col=3), centre (3.5, 0.5), value 33.
    out = sample(GRID, np.array([3.5]), np.array([0.5]))
    assert out[0] == 33.0


def test_sample_at_cell_edges_uses_gdal_floor_convention():
    # x=2.0 is the shared edge between col 1 and col 2; floor((x-c)/a)=floor(2.0)=2
    # puts it in col 2 (the pixel that starts there), same GDAL/rasterio convention
    # rasterio.transform.rowcol uses by default.
    from rasterio.transform import rowcol

    xs, ys = [2.0, 1.0, 0.0], [2.0, 3.0, 4.0]
    rows, cols = rowcol(TRANSFORM, xs, ys)
    out = sample(GRID, np.array(xs), np.array(ys))
    for i in range(len(xs)):
        assert out[i] == KNOWN[rows[i], cols[i]]
    # spot check the values rowcol resolves to, so this test fails loudly if the
    # convention ever changes rather than passing vacuously: (2,2)->row2,col2=22;
    # (1,3)->row1,col1=11; (0,4)->row0,col0=0.
    assert list(out) == [22.0, 11.0, 0.0]


def test_sample_outside_grid_is_nan():
    out = sample(GRID, np.array([-1.0, 100.0, 2.0]), np.array([2.0, 2.0, -50.0]))
    assert np.isnan(out[0])
    assert np.isnan(out[1])
    assert np.isnan(out[2])


def test_sample_broadcasts_over_arrays():
    xs = np.array([0.5, 1.5, 2.5, 3.5])
    ys = np.array([3.5, 3.5, 3.5, 3.5])
    out = sample(GRID, xs, ys)
    assert np.array_equal(out, np.array([0.0, 1.0, 2.0, 3.0], dtype="float32"))
