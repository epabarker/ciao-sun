"""The crown-envelope obstruction surface Horizon profiles are cast against (ADR 0003).

Vegetation is where the first-return DSM stands more than 2 m above the DTM,
outside OSM building footprints buffered by 1.5 m. On vegetation cells the
surface is the larger of the last-return and first-return DSM, whatever season
the cell was surveyed in; everywhere else it is the last-return DSM. Trees are
therefore opaque all year, and clutter under 2 m is ignored.

Over water (ADR 0003, amended by #60): moored boats are not obstructions, since
they move. `lower_moored_boats` sets every cell in mooring water (docks,
harbours, marinas, locks, basins) to the DTM unless something stands there for
good: a building footprint, a bridge within 20 m, or a tree, told from a hull
by its returns lying more than 1 m apart. Over rivers and ponds everything is
kept, because LIDAR cannot tell a dense tree from a boat there; raised cells
that are neither building nor bridge are marked for the build to report, since
some may be tidal water standing proud in the first return.

Footprints, water and bridges come from a dated `.osm.pbf`, never live
Overpass. Read them once per build, then call `crown_envelope_surface` and
`lower_moored_boats` per tile with that tile's three mosaics.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from pyproj import Transformer
from rasterio.crs import CRS

from ciao_sun.crs import lonlat_box
from ciao_sun.raster import RasterGrid, assert_aligned

# ADR 0003: first-return height above the DTM that counts as vegetation.
VEGETATION_MIN_HEIGHT_M = 2.0
# ADR 0003: first returns spill about a cell past walls and eaves, so cells this
# close to a building footprint are never vegetation.
BUILDING_BUFFER_M = 1.5
# #60: a cell this close to an OSM bridge line is the bridge; decks are wide.
BRIDGE_REACH_M = 20.0
# #60: first and last returns further apart than this mean the laser went into
# something it could pass through: a tree, not a hull.
TREE_RETURN_SPREAD_M = 1.0
# #60: a water cell more than this above the DTM is standing on the water.
RAISED_ON_WATER_M = 1.0
# Water where boats moor: their cells are lowered to the DTM (#60).
_MOORING_WATER = frozenset({"harbour", "marina", "lock", "basin", "dock"})

Bounds = tuple[float, float, float, float]


class BuildingFootprints:
    """OSM building footprints as polygons in a projected CRS."""

    def __init__(self, geometries: list[Any], crs: CRS) -> None:
        self.geometries: tuple[Any, ...] = tuple(geometries)
        self.crs = crs
        self._tree = shapely.STRtree(self.geometries)

    def __len__(self) -> int:
        return len(self.geometries)

    def buffered_mask(self, grid: RasterGrid, buffer_m: float) -> np.ndarray:
        """True for every cell of `grid` whose centre lies within `buffer_m` of a footprint."""
        from rasterio.features import rasterize

        if grid.crs != self.crs:
            raise ValueError(
                f"Building footprints are in {self.crs} but the raster is in {grid.crs}."
            )
        minx, miny, maxx, maxy = grid.bounds
        window = shapely.box(minx - buffer_m, miny - buffer_m, maxx + buffer_m, maxy + buffer_m)
        nearby = [self.geometries[i] for i in self._tree.query(window)]
        if not nearby:
            return np.zeros(grid.shape, dtype=bool)
        buffered = [(g.buffer(buffer_m), 1) for g in nearby]
        mask: np.ndarray = rasterize(
            buffered, out_shape=grid.shape, transform=grid.transform, fill=0, dtype="uint8"
        )
        return mask.astype(bool)


def read_building_footprints(
    pbf_path: Path, crs: CRS, bounds: Bounds | None = None
) -> BuildingFootprints:
    """Every `building=*` area in an OSM extract, projected into `crs`.

    Closed ways and multipolygon relations both count. `bounds`
    (minx, miny, maxx, maxy) in `crs`, when given, keeps only the footprints
    whose bounding box touches it; pass the coverage plus the ray length.
    """
    return _read_areas(pbf_path, crs, bounds, ("building",), lambda tags: True)


# Tags that make an OSM area open water: rivers, docks, lakes, reservoirs.
_WATER_TAGS = {
    "natural": frozenset({"water"}),
    "waterway": frozenset({"riverbank", "dock"}),
    "landuse": frozenset({"reservoir", "basin"}),
}


def read_water_areas(pbf_path: Path, crs: CRS, bounds: Bounds | None = None) -> BuildingFootprints:
    """Every open-water area in an OSM extract, projected into `crs`.

    The result has the shape of building footprints: `buffered_mask(grid, 0.0)`
    is True on the grid's water cells.
    """
    return _read_areas(
        pbf_path,
        crs,
        bounds,
        tuple(_WATER_TAGS),
        lambda tags: any(tags.get(key) in values for key, values in _WATER_TAGS.items()),
    )


def read_mooring_water(
    pbf_path: Path, crs: CRS, bounds: Bounds | None = None
) -> BuildingFootprints:
    """Every area of an OSM extract where boats moor: docks, harbours, marinas, locks, basins."""
    return _read_areas(
        pbf_path,
        crs,
        bounds,
        ("waterway", "water", "leisure"),
        lambda tags: (
            tags.get("waterway") == "dock"
            or tags.get("water") in _MOORING_WATER
            or tags.get("leisure") == "marina"
        ),
    )


def read_bridges(pbf_path: Path, crs: CRS, bounds: Bounds | None = None) -> BuildingFootprints:
    """Every bridge in an OSM extract as a line: ways tagged `bridge=*` (not `no`) and
    `man_made=bridge` outlines. Use `buffered_mask(grid, BRIDGE_REACH_M)` for the deck."""
    import osmium

    box = None if bounds is None else lonlat_box(bounds, crs)
    to_crs = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    lines = []
    processor = (
        osmium.FileProcessor(str(pbf_path), osmium.osm.NODE | osmium.osm.WAY)
        .with_locations()
        .with_filter(osmium.filter.KeyFilter("bridge", "man_made"))
    )
    for way in processor:
        if not isinstance(way, osmium.osm.Way):
            continue
        if way.tags.get("bridge", "no") == "no" and way.tags.get("man_made") != "bridge":
            continue
        points = [(n.lon, n.lat) for n in way.nodes if n.location.valid()]
        if len(points) < 2:
            continue
        if box is not None:
            lons, lats = [p[0] for p in points], [p[1] for p in points]
            if min(lons) > box[2] or max(lons) < box[0] or min(lats) > box[3] or max(lats) < box[1]:
                continue
        x, y = to_crs.transform([p[0] for p in points], [p[1] for p in points])
        lines.append(shapely.LineString(np.column_stack([x, y])))
    return BuildingFootprints(lines, crs)


def _read_areas(
    pbf_path: Path,
    crs: CRS,
    bounds: Bounds | None,
    keys: tuple[str, ...],
    wanted: Callable[[Any], bool],
) -> BuildingFootprints:
    import osmium

    pbf_path = Path(pbf_path)
    if not pbf_path.exists():
        raise FileNotFoundError(f"OSM extract not found: {pbf_path}")

    wkb_factory = osmium.geom.WKBFactory()
    wkbs: list[str] = []
    # A first, cheap cut in lon/lat before anything is built or projected: a
    # national extract holds millions of buildings, and a build needs a city's.
    box = None if bounds is None else lonlat_box(bounds, crs)
    processor = (
        osmium.FileProcessor(str(pbf_path)).with_areas().with_filter(osmium.filter.KeyFilter(*keys))
    )
    for obj in processor:
        if not isinstance(obj, osmium.osm.Area) or not wanted(obj.tags):
            continue
        if box is not None and not _outer_rings_reach(obj, box):
            continue
        try:
            wkbs.append(wkb_factory.create_multipolygon(obj))
        except RuntimeError:
            # An area osmium could not assemble into a valid multipolygon.
            continue

    to_crs = Transformer.from_crs("EPSG:4326", crs, always_xy=True)

    def project(lonlat: np.ndarray) -> np.ndarray:
        x, y = to_crs.transform(lonlat[:, 0], lonlat[:, 1])
        return np.column_stack([x, y])

    projected = shapely.transform(shapely.from_wkb(wkbs), project)
    geometries = [g for g in projected.tolist() if not g.is_empty]
    if bounds is not None:
        window = shapely.box(*bounds)
        geometries = [g for g in geometries if shapely.box(*g.bounds).intersects(window)]
    return BuildingFootprints(geometries, crs)


def _outer_rings_reach(area: Any, box: Bounds) -> bool:
    """Whether the bounding box of an area's outer rings overlaps `box` (lon/lat)."""
    lons = [n.lon for ring in area.outer_rings() for n in ring if n.location.valid()]
    lats = [n.lat for ring in area.outer_rings() for n in ring if n.location.valid()]
    return bool(lons) and (
        min(lons) <= box[2] and max(lons) >= box[0] and min(lats) <= box[3] and max(lats) >= box[1]
    )


def crown_envelope_surface(
    last_return: RasterGrid,
    first_return: RasterGrid,
    dtm: RasterGrid,
    footprints: BuildingFootprints,
) -> RasterGrid:
    """The obstruction surface for one tile, on the grid its three inputs share."""
    assert_aligned(last_return, first_return)
    assert_aligned(last_return, dtm)
    near_building = footprints.buffered_mask(last_return, BUILDING_BUFFER_M)
    with np.errstate(invalid="ignore"):
        # NaN (no data in either input) compares False, so it is never vegetation.
        tall = (first_return.data - dtm.data) > VEGETATION_MIN_HEIGHT_M
    vegetation = tall & ~near_building
    data = last_return.data.astype("float32", copy=True)
    # fmax: where the last return has no data, the first return still stands.
    data[vegetation] = np.fmax(last_return.data[vegetation], first_return.data[vegetation])
    return RasterGrid(data=data, transform=last_return.transform, crs=last_return.crs)


@dataclass(frozen=True, eq=False)
class OpenWater:
    """A tile's obstruction surface with moored boats lowered, and what the build checks over water.

    `flattened` is True on the mooring-water cells lowered to the DTM;
    `raised_river` on cells of other water standing more than 1 m above the DTM
    that are neither building nor bridge (trees, or tidal water standing proud).
    """

    surface: RasterGrid
    flattened: np.ndarray
    raised_river: np.ndarray


def lower_moored_boats(
    surface: RasterGrid,
    first_return: RasterGrid,
    last_return: RasterGrid,
    dtm: RasterGrid,
    *,
    moorings: BuildingFootprints,
    water: BuildingFootprints,
    buildings: BuildingFootprints,
    bridges: BuildingFootprints,
) -> OpenWater:
    """`surface` with every cell of mooring water lowered to the DTM unless something stands
    there for good: a building, a bridge within `BRIDGE_REACH_M`, or a tree."""
    for grid in (first_return, last_return, dtm):
        assert_aligned(surface, grid)
    on_water = water.buffered_mask(surface, 0.0)
    lasting = buildings.buffered_mask(surface, 0.0) | bridges.buffered_mask(surface, BRIDGE_REACH_M)
    with np.errstate(invalid="ignore"):
        tree = (first_return.data - last_return.data) > TREE_RETURN_SPREAD_M
        raised = (surface.data - dtm.data) > RAISED_ON_WATER_M
    flattened = on_water & moorings.buffered_mask(surface, 0.0) & ~lasting & ~tree
    data = surface.data.astype("float32", copy=True)
    data[flattened] = dtm.data[flattened]
    lowered = RasterGrid(data=data, transform=surface.transform, crs=surface.crs)
    raised_river = on_water & ~moorings.buffered_mask(surface, 0.0) & raised & ~lasting
    return OpenWater(lowered, flattened, raised_river)
