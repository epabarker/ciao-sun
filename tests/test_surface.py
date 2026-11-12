"""Crown-envelope obstruction surface (ADR 0003), on a synthetic world.

The world is a 20 x 20 m patch of flat ground at 10 m, on a 1 m grid whose cell
(row, col) is centred on (358000 + col, 175020 - row) in British National Grid.
One 6 m tall building stands on it, and its footprint comes from a synthetic
`.osm.pbf` written by the test, the same way a dated Geofabrik extract is read.

Footprint: x 358004.5..358009.0, y 175005.5..175010.5. The east wall is at
x = 358009.0, so cell centres in col 10 lie 1.0 m outside it (inside the 1.5 m
buffer) and those in col 11 lie 2.0 m outside it (beyond the buffer).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import osmium
import pytest
from osmium.osm import mutable
from pyproj import Transformer

from ciao_sun.raster import RasterGrid
from ciao_sun.surface import (
    BuildingFootprints,
    crown_envelope_surface,
    read_building_footprints,
)
from tests.conftest import BNG, make_flat_grid

X0, Y0 = 358000.0, 175020.0
GROUND = 10.0
ROOF = 16.0
FOOTPRINT = [
    (358004.5, 175005.5),
    (358009.0, 175005.5),
    (358009.0, 175010.5),
    (358004.5, 175010.5),
]
COURTYARD_OUTER = [
    (358100.0, 175100.0),
    (358120.0, 175100.0),
    (358120.0, 175120.0),
    (358100.0, 175120.0),
]
COURTYARD_INNER = [
    (358105.0, 175105.0),
    (358115.0, 175105.0),
    (358115.0, 175115.0),
    (358105.0, 175115.0),
]
PATH = [(358000.0, 175000.0), (358019.0, 175000.0), (358019.0, 175019.0)]

_BNG_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


class _OsmExtract:
    """Writes a small `.osm.pbf` from British National Grid coordinates."""

    def __init__(self, path: Path) -> None:
        self._writer = osmium.SimpleWriter(str(path))
        self._next_id = 1

    def _nodes(self, points: list[tuple[float, float]]) -> list[int]:
        ids = []
        for x, y in points:
            lon, lat = _BNG_TO_WGS84.transform(x, y)
            self._writer.add_node(mutable.Node(id=self._next_id, location=(lon, lat)))
            ids.append(self._next_id)
            self._next_id += 1
        return ids

    def way(self, points: list[tuple[float, float]], tags: dict[str, str], closed: bool) -> int:
        ids = self._nodes(points)
        if closed:
            ids.append(ids[0])
        way_id = self._next_id
        self._next_id += 1
        self._writer.add_way(mutable.Way(id=way_id, nodes=ids, tags=tags))
        return way_id

    def multipolygon(self, outer: int, inner: int, tags: dict[str, str]) -> None:
        self._writer.add_relation(
            mutable.Relation(
                id=self._next_id,
                members=[("w", outer, "outer"), ("w", inner, "inner")],
                tags={"type": "multipolygon", **tags},
            )
        )
        self._next_id += 1

    def close(self) -> None:
        self._writer.close()


@pytest.fixture
def osm_extract(tmp_path: Path) -> Path:
    """A building, a footpath, and a far-off building with a courtyard.

    Nodes, then ways, then relations: the order every `.osm.pbf` uses.
    """
    path = tmp_path / "synthetic-261101.osm.pbf"
    extract = _OsmExtract(path)
    extract.way(FOOTPRINT, {"building": "house"}, closed=True)
    extract.way(PATH, {"highway": "footway"}, closed=False)
    outer = extract.way(COURTYARD_OUTER, {}, closed=True)
    inner = extract.way(COURTYARD_INNER, {}, closed=True)
    extract.multipolygon(outer, inner, {"building": "yes"})
    extract.close()
    return path


@pytest.fixture
def footprints(osm_extract: Path) -> BuildingFootprints:
    return read_building_footprints(osm_extract, BNG)


def _grid(value: float) -> RasterGrid:
    return make_flat_grid(value, X0, Y0, width=20, height=20)


def _world() -> tuple[RasterGrid, RasterGrid, RasterGrid]:
    """(last-return DSM, first-return DSM, DTM) with only the building on it."""
    last, first, dtm = _grid(GROUND), _grid(GROUND), _grid(GROUND)
    # The footprint covers the cells in rows 10..14, cols 5..8, plus col 9 whose
    # centres sit on the east wall.
    last.data[10:15, 5:10] = ROOF
    first.data[10:15, 5:10] = ROOF
    return last, first, dtm


def test_footprints_are_read_from_an_osm_extract_into_the_grid_crs(
    footprints: BuildingFootprints,
) -> None:
    house = min(footprints.geometries, key=lambda g: g.area)
    # OSM stores 1e-7 degrees, about 1 cm; the footprint must land within 2 cm.
    assert house.bounds == pytest.approx((358004.5, 175005.5, 358009.0, 175010.5), abs=0.02)


def test_only_buildings_are_footprints_and_a_courtyard_stays_open(
    footprints: BuildingFootprints,
) -> None:
    # The footpath is not a footprint; the multipolygon relation is one.
    assert len(footprints) == 2
    courtyard_block = max(footprints.geometries, key=lambda g: g.area)
    # 20 x 20 m outer ring less the 10 x 10 m courtyard.
    assert courtyard_block.area == pytest.approx(300.0, abs=1.0)


def test_footprints_can_be_limited_to_the_area_a_build_needs(osm_extract: Path) -> None:
    near_the_house = (358000.0, 175000.0, 358020.0, 175020.0)
    footprints = read_building_footprints(osm_extract, BNG, bounds=near_the_house)
    assert len(footprints) == 1
    assert footprints.geometries[0].area == pytest.approx(4.5 * 5.0, abs=0.5)


def test_a_footprint_is_kept_when_the_bounds_fall_inside_it_away_from_its_corners(
    osm_extract: Path,
) -> None:
    # A 2 m box in the solid west side of the courtyard block: no corner of the
    # block is inside it, but the block covers it.
    inside_the_wall = (358101.0, 175109.0, 358103.0, 175111.0)
    footprints = read_building_footprints(osm_extract, BNG, bounds=inside_the_wall)
    assert len(footprints) == 1
    assert footprints.geometries[0].area == pytest.approx(300.0, abs=1.0)


def test_a_missing_osm_extract_is_reported(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="nowhere.osm.pbf"):
        read_building_footprints(tmp_path / "nowhere.osm.pbf", BNG)


def test_a_building_edge_cell_inside_the_buffer_is_not_raised(
    footprints: BuildingFootprints,
) -> None:
    last, first, dtm = _world()
    # First returns spill a cell past the east wall: col 10, 1.0 m outside it.
    first.data[10:15, 10] = ROOF

    surface = crown_envelope_surface(last, first, dtm, footprints)

    assert np.all(surface.data[10:15, 10] == GROUND)


def test_a_tree_just_beyond_the_building_buffer_is_raised(
    footprints: BuildingFootprints,
) -> None:
    last, first, dtm = _world()
    # Col 11 is 2.0 m outside the east wall, past the 1.5 m buffer.
    first.data[12, 11] = 19.0

    surface = crown_envelope_surface(last, first, dtm, footprints)

    assert surface.data[12, 11] == 19.0


def test_a_roof_keeps_its_last_return_height(footprints: BuildingFootprints) -> None:
    last, first, dtm = _world()
    # An aerial on the roof shows in the first return only.
    first.data[12, 7] = 19.0

    surface = crown_envelope_surface(last, first, dtm, footprints)

    assert surface.data[12, 7] == ROOF


def test_clutter_below_two_metres_leaves_the_last_return_height(
    footprints: BuildingFootprints,
) -> None:
    last, first, dtm = _world()
    # A 1.5 m hedge, and a wall exactly 2 m tall: vegetation is strictly over 2 m.
    first.data[17, 3] = 11.5
    first.data[17, 5] = 12.0

    surface = crown_envelope_surface(last, first, dtm, footprints)

    assert surface.data[17, 3] == GROUND
    assert surface.data[17, 5] == GROUND


def test_a_tree_keeps_the_larger_of_its_two_returns(footprints: BuildingFootprints) -> None:
    last, first, dtm = _world()
    # The two products come from different surveys, so the last return can be
    # the higher one where a crown was surveyed in leaf.
    last.data[3, 3] = 21.0
    first.data[3, 3] = 20.0

    surface = crown_envelope_surface(last, first, dtm, footprints)

    assert surface.data[3, 3] == 21.0


def test_cells_with_no_first_return_keep_the_last_return_height(
    footprints: BuildingFootprints,
) -> None:
    last, first, dtm = _world()
    last.data[6, 16] = 13.0
    first.data[6, 16] = np.nan

    surface = crown_envelope_surface(last, first, dtm, footprints)

    assert surface.data[6, 16] == 13.0


def test_the_last_return_is_left_untouched(footprints: BuildingFootprints) -> None:
    # The build goes on to pick Candidates' open ground from the same last return.
    last, first, dtm = _world()
    first.data[3, 15] = 22.0

    crown_envelope_surface(last, first, dtm, footprints)

    assert last.data[3, 15] == GROUND


def test_misaligned_inputs_are_refused(footprints: BuildingFootprints) -> None:
    last, _, dtm = _world()
    shifted_first = make_flat_grid(GROUND, X0 + 1.0, Y0, width=20, height=20)

    with pytest.raises(ValueError, match="not aligned"):
        crown_envelope_surface(last, shifted_first, dtm, footprints)


def test_a_tile_far_from_any_building_still_gets_its_trees(
    footprints: BuildingFootprints,
) -> None:
    last = make_flat_grid(GROUND, 359000.0, Y0, width=5, height=5)
    first = make_flat_grid(GROUND, 359000.0, Y0, width=5, height=5)
    dtm = make_flat_grid(GROUND, 359000.0, Y0, width=5, height=5)
    first.data[2, 2] = 25.0

    surface = crown_envelope_surface(last, first, dtm, footprints)

    assert surface.data[2, 2] == 25.0


def test_footprints_in_another_crs_are_refused(osm_extract: Path) -> None:
    from rasterio.crs import CRS

    last, first, dtm = _world()
    wrong = read_building_footprints(osm_extract, CRS.from_epsg(32630))

    with pytest.raises(ValueError, match="EPSG:32630"):
        crown_envelope_surface(last, first, dtm, wrong)
