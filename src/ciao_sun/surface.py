"""The crown-envelope obstruction surface Horizon profiles are cast against (ADR 0003).

Vegetation is where the first-return DSM stands more than 2 m above the DTM,
outside OSM building footprints buffered by 1.5 m. On vegetation cells the
surface is the larger of the last-return and first-return DSM, whatever season
the cell was surveyed in; everywhere else it is the last-return DSM. Trees are
therefore opaque all year, clutter under 2 m is ignored, and there is no water
mask (the build's water guard replaces it).

Building footprints come from a dated `.osm.pbf`, never live Overpass. Read
them once per build with `read_building_footprints`, then call
`crown_envelope_surface` per tile with that tile's three mosaics.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from pyproj import Transformer
from rasterio.crs import CRS

from ciao_sun.raster import RasterGrid, assert_aligned

# ADR 0003: first-return height above the DTM that counts as vegetation.
VEGETATION_MIN_HEIGHT_M = 2.0
# ADR 0003: first returns spill about a cell past walls and eaves, so cells this
# close to a building footprint are never vegetation.
BUILDING_BUFFER_M = 1.5

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
    processor = (
        osmium.FileProcessor(str(pbf_path)).with_areas().with_filter(osmium.filter.KeyFilter(*keys))
    )
    for obj in processor:
        if not isinstance(obj, osmium.osm.Area) or not wanted(obj.tags):
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
