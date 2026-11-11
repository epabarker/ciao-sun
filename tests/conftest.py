"""Shared synthetic-raster fixtures for tests."""

from __future__ import annotations

import numpy as np
import pytest
from affine import Affine
from rasterio.crs import CRS

from ciao_sun.raster import RasterGrid

BNG = CRS.from_epsg(27700)


def make_flat_grid(
    value: float,
    xmin: float,
    ymax: float,
    width: int,
    height: int,
    pixel_size: float = 1.0,
) -> RasterGrid:
    """A constant-elevation raster, north-up, `pixel_size` resolution.

    `xmin`/`ymax` are the *centre* of the first (top-left) pixel, not its
    corner -- so integer-valued real-world coordinates land exactly on pixel
    centres rather than on the knife-edge between two pixels, which keeps
    tests robust to last-bit floating point noise from sin/cos (e.g. a ray
    point meant to be exactly x=100.0 landing at 99.999999999999994).
    """
    data = np.full((height, width), value, dtype="float32")
    half = pixel_size / 2.0
    transform = Affine(pixel_size, 0.0, xmin - half, 0.0, -pixel_size, ymax + half)
    return RasterGrid(data=data, transform=transform, crs=BNG)


@pytest.fixture
def flat_grid_factory():
    return make_flat_grid
