"""OS National Grid references, derived arithmetically -- no lookup table.

Environment Agency LIDAR is published in 5 km squares; `ciao-sun fetch` uses
`tile_codes_near_polygon` to decide which ones a coverage needs. Ciao Sun's own
tiles are 1 km squares named by grid ref (`grid_ref_of`, `grid_ref_origin`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

# 100 km grid letters, derived arithmetically: see OS's "A guide to coordinate
# systems in Great Britain", Annex C. Verified against two well-known reference
# squares: BNG origin (0, 0) is grid square SV, and central London is TQ.
_GRID_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"  # the grid has no I
_TILE_SIZE_M = 5000
_HUNDRED_KM = 100_000
KM = 1000


def _grid_letters(e100k: int, n100k: int) -> str:
    if not (0 <= e100k <= 6 and 0 <= n100k <= 12):
        raise ValueError(
            "Coordinates fall outside the lettered British National Grid area "
            f"(e100k={e100k}, n100k={n100k}); Ciao Sun only covers England."
        )
    l1 = (19 - n100k) - (19 - n100k) % 5 + (e100k + 10) // 5
    l2 = (19 - n100k) % 5 * 5 + e100k % 5
    return _GRID_LETTERS[l1] + _GRID_LETTERS[l2]


_SQUARE_ORIGINS = {
    _grid_letters(e, n): (e * _HUNDRED_KM, n * _HUNDRED_KM) for e in range(7) for n in range(13)
}


def square_origin(letters: str) -> tuple[int, int]:
    """The (easting, northing) of the south-west corner of a 100 km square, e.g. "ST"."""
    origin = _SQUARE_ORIGINS.get(letters.upper())
    if origin is None:
        raise ValueError(f"{letters!r} is not a 100 km National Grid square")
    return origin


def bng_to_tile_code(easting: float, northing: float) -> str:
    """The OS 5 km tile code (e.g. "ST5575") containing a British National Grid point."""
    e100k, n100k = int(easting // _HUNDRED_KM), int(northing // _HUNDRED_KM)
    letters = _grid_letters(e100k, n100k)
    e_in = easting - e100k * _HUNDRED_KM
    n_in = northing - n100k * _HUNDRED_KM
    e5 = int(e_in // _TILE_SIZE_M) * 5
    n5 = int(n_in // _TILE_SIZE_M) * 5
    return f"{letters}{e5:02d}{n5:02d}"


def grid_ref_of(easting: float, northing: float) -> str:
    """The 1 km grid ref (e.g. "ST5873") of the square holding a National Grid point."""
    e100k, n100k = int(easting // _HUNDRED_KM), int(northing // _HUNDRED_KM)
    e_km = int((easting - e100k * _HUNDRED_KM) // KM)
    n_km = int((northing - n100k * _HUNDRED_KM) // KM)
    return f"{_grid_letters(e100k, n100k)}{e_km:02d}{n_km:02d}"


def grid_ref_origin(grid_ref: str) -> tuple[int, int]:
    """The (easting, northing) of the south-west corner of a 1 km grid ref's square."""
    origin = _SQUARE_ORIGINS.get(grid_ref[:2])
    if origin is None or len(grid_ref) != 6 or not grid_ref[2:].isdecimal():
        raise ValueError(f"{grid_ref!r} is not a 1 km OS grid ref like 'ST5873'")
    return (origin[0] + int(grid_ref[2:4]) * KM, origin[1] + int(grid_ref[4:6]) * KM)


Point = tuple[float, float]


def tile_codes_near_polygon(rings: Sequence[Sequence[Point]], margin_m: float) -> list[str]:
    """Sorted 5 km tile codes of every tile within `margin_m` of a polygon.

    `rings` are the polygon's outer rings in British National Grid metres (one
    per part of a multi-part polygon; closing the ring is optional). A tile
    counts when any part of it is within `margin_m` of any ring's interior or
    boundary, so a margin of 0 gives the tiles the polygon touches.
    """
    if margin_m < 0:
        raise ValueError("margin_m must not be negative")
    if not rings or any(len(ring) < 3 for ring in rings):
        raise ValueError("each ring needs at least three points")
    xs = [x for ring in rings for x, _ in ring]
    ys = [y for ring in rings for _, y in ring]
    e_lo = math.floor((min(xs) - margin_m) / _TILE_SIZE_M)
    e_hi = math.floor((max(xs) + margin_m) / _TILE_SIZE_M)
    n_lo = math.floor((min(ys) - margin_m) / _TILE_SIZE_M)
    n_hi = math.floor((max(ys) + margin_m) / _TILE_SIZE_M)

    codes: list[str] = []
    for ei in range(e_lo, e_hi + 1):
        for ni in range(n_lo, n_hi + 1):
            x0, y0 = ei * _TILE_SIZE_M, ni * _TILE_SIZE_M
            rect = (float(x0), float(y0), float(x0 + _TILE_SIZE_M), float(y0 + _TILE_SIZE_M))
            if any(_rect_ring_distance(rect, ring) <= margin_m for ring in rings):
                codes.append(bng_to_tile_code(x0, y0))
    return sorted(codes)


def _rect_ring_distance(rect: tuple[float, float, float, float], ring: Sequence[Point]) -> float:
    """Distance from an axis-aligned rectangle to a filled ring; 0 if they overlap."""
    x0, y0, x1, y1 = rect
    if any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in ring):
        return 0.0
    corners: list[Point] = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if _point_in_ring(corners[0], ring):
        return 0.0
    best = math.inf
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        for j in range(4):
            best = min(best, _segment_distance(a, b, corners[j], corners[(j + 1) % 4]))
            if best == 0.0:
                return 0.0
    return best


def _point_in_ring(p: Point, ring: Sequence[Point]) -> bool:
    inside = False
    px, py = p
    for i in range(len(ring)):
        (ax, ay), (bx, by) = ring[i], ring[(i + 1) % len(ring)]
        if (ay > py) != (by > py) and px < ax + (py - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segment_distance(a: Point, b: Point, c: Point, d: Point) -> float:
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(
        _point_segment_distance(a, c, d),
        _point_segment_distance(b, c, d),
        _point_segment_distance(c, a, b),
        _point_segment_distance(d, a, b),
    )


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    abx, aby = b[0] - a[0], b[1] - a[1]
    length_sq = abx * abx + aby * aby
    t = 0.0
    if length_sq > 0:
        t = max(0.0, min(1.0, ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / length_sq))
    return math.hypot(p[0] - (a[0] + t * abx), p[1] - (a[1] + t * aby))
