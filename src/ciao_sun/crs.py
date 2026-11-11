"""The two coordinate transforms Ciao Sun uses, built once for the package.

WGS84 (EPSG:4326) is what tiles, Queries and OSM carry; the British National
Grid (EPSG:27700) is what the rasters, the horizon and the 1 km tiles are laid
out on. Both take and return (x, y), that is (lon, lat) for WGS84.
"""

from __future__ import annotations

from pyproj import Transformer

WGS84_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
BNG_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
