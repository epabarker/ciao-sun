"""The two coordinate transforms Ciao Sun uses, built once for the package.

WGS84 (EPSG:4326) is what tiles, Queries and OSM carry; the British National
Grid (EPSG:27700) is what the rasters, the horizon and the 1 km tiles are laid
out on. Both take and return (x, y), that is (lon, lat) for WGS84.
"""

from __future__ import annotations

import numpy as np
from pyproj import Transformer

WGS84_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
BNG_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


def lonlat_box(
    bounds: tuple[float, float, float, float], crs: object = "EPSG:27700"
) -> tuple[float, float, float, float]:
    """A (min lon, min lat, max lon, max lat) box holding `bounds` (minx, miny, maxx, maxy).

    `bounds` are in `crs`, the National Grid unless given.

    It is a little larger than `bounds`, never smaller: grid lines curve in
    WGS84, so each side is sampled densely and the result is padded by about
    10 m. Use it to skip OSM objects cheaply before projecting them.
    """
    to_wgs84 = (
        BNG_TO_WGS84
        if crs == "EPSG:27700"
        else Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    )
    minx, miny, maxx, maxy = bounds
    steps = np.linspace(0.0, 1.0, 65)
    xs = np.concatenate([minx + (maxx - minx) * steps, np.full(65, maxx),
                         maxx - (maxx - minx) * steps, np.full(65, minx)])  # fmt: skip
    ys = np.concatenate([np.full(65, miny), miny + (maxy - miny) * steps,
                         np.full(65, maxy), maxy - (maxy - miny) * steps])  # fmt: skip
    lon, lat = to_wgs84.transform(xs, ys)
    pad = 1e-4  # degrees: about 11 m of latitude, 7 m of longitude here
    return (
        float(np.min(lon)) - pad, float(np.min(lat)) - pad,
        float(np.max(lon)) + pad, float(np.max(lat)) + pad,
    )  # fmt: skip
