"""OS National Grid 5 km tile codes, derived arithmetically -- no lookup table.

Downloading LIDAR tiles from environment.data.gov.uk is a manual step (the
portal is an interactive ESRI widget); `sunspot tiles` tells the user which
5 km squares to select.
"""

from __future__ import annotations

from pyproj import Transformer

# 100 km grid letters, A-Z with no lookup table: see OS's "A guide to coordinate
# systems in Great Britain", Annex C. Verified against two well-known reference
# squares: BNG origin (0, 0) is grid square SV, and central London is TQ.
_GRID_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_TILE_SIZE_M = 5000
_HUNDRED_KM = 100_000

_WGS84_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)


def _grid_letters(e100k: int, n100k: int) -> str:
    if not (0 <= e100k <= 6 and 0 <= n100k <= 12):
        raise ValueError(
            "Coordinates fall outside the lettered British National Grid area "
            f"(e100k={e100k}, n100k={n100k}); sunspot only covers England."
        )
    l1 = (19 - n100k) - (19 - n100k) % 5 + (e100k + 10) // 5
    l2 = (19 - n100k) % 5 * 5 + e100k % 5
    if l1 > 7:
        l1 += 1
    if l2 > 7:
        l2 += 1
    return _GRID_LETTERS[l1] + _GRID_LETTERS[l2]


def bng_to_tile_code(easting: float, northing: float) -> str:
    """The OS 5 km tile code (e.g. "ST5575") containing a British National Grid point."""
    e100k, n100k = int(easting // _HUNDRED_KM), int(northing // _HUNDRED_KM)
    letters = _grid_letters(e100k, n100k)
    e_in = easting - e100k * _HUNDRED_KM
    n_in = northing - n100k * _HUNDRED_KM
    e5 = int(e_in // _TILE_SIZE_M) * 5
    n5 = int(n_in // _TILE_SIZE_M) * 5
    return f"{letters}{e5:02d}{n5:02d}"


def tile_codes_for_aoi(lat: float, lon: float, radius_m: float) -> list[str]:
    """Sorted, unique 5 km tile codes covering a circle of radius_m around lat/lon."""
    if radius_m <= 0:
        raise ValueError("radius_m must be positive")
    x, y = _WGS84_TO_BNG.transform(lon, lat)
    xmin, xmax = x - radius_m, x + radius_m
    ymin, ymax = y - radius_m, y + radius_m
    e0 = int(xmin // _TILE_SIZE_M) * _TILE_SIZE_M
    n0 = int(ymin // _TILE_SIZE_M) * _TILE_SIZE_M

    codes: set[str] = set()
    ee = e0
    while ee <= xmax:
        nn = n0
        while nn <= ymax:
            codes.add(bng_to_tile_code(ee, nn))
            nn += _TILE_SIZE_M
        ee += _TILE_SIZE_M
    return sorted(codes)
