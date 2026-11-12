"""Moored boats are not obstructions; what stands over water for good is (#60).

The world is a 60 x 60 m patch of flat ground at 5 m on a 1 m grid whose cell
(row, col) is centred on (360000 + col, 180059 - row). Its west half is a dock
and its east half a river, and a bridge crosses both along y = 180050:

    y 180050  ========================= bridge ==========================
              |  boat (by the bridge)      |                            |
              |                            |                            |
    y 180005  |  boat   tree   building    |  hull-like   building      |
              x 0       15     21..25      x 30   40      50..53       59
                         dock                         river

The boat by the bridge is 9 m from it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import shapely

from ciao_sun.raster import RasterGrid
from ciao_sun.surface import (
    BuildingFootprints,
    crown_envelope_surface,
    lower_moored_boats,
    read_bridges,
    read_mooring_water,
)
from tests.conftest import BNG, make_flat_grid
from tests.osm_extract import write_osm_extract

X0, Y_TOP = 360000.0, 180059.0
GROUND = 5.0

DOCK = shapely.box(X0 - 0.5, 179999.5, X0 + 29.5, 180059.5)
RIVER = shapely.box(X0 + 29.5, 179999.5, X0 + 59.5, 180059.5)
BRIDGE = shapely.LineString([(X0, 180050.0), (X0 + 59, 180050.0)])
DOCK_BUILDING = shapely.box(X0 + 20.5, 180004.5, X0 + 25.5, 180008.5)
RIVER_BUILDING = shapely.box(X0 + 49.5, 180004.5, X0 + 53.5, 180008.5)


def _cells(grid: RasterGrid, x0: int, x1: int, y0: int, y1: int, value: float) -> None:
    """Set the cells centred on x0..x1, y0..y1 (offsets from X0, absolute northings)."""
    grid.data[int(Y_TOP) - y1 : int(Y_TOP) - y0 + 1, x0 : x1 + 1] = value


def _at(grid: RasterGrid | np.ndarray, x: int, y: int) -> float:
    data = grid.data if isinstance(grid, RasterGrid) else grid
    return float(data[int(Y_TOP) - y, x])


@pytest.fixture
def world():
    def flat() -> RasterGrid:
        return make_flat_grid(GROUND, X0, Y_TOP, width=60, height=60)

    last, first, dtm = flat(), flat(), flat()
    for grid in (last, first):
        _cells(grid, 5, 7, 180005, 180007, GROUND + 3)  # boat in the dock
        _cells(grid, 5, 7, 180040, 180042, GROUND + 3)  # boat by the bridge
        _cells(grid, 21, 25, 180005, 180008, GROUND + 7)  # building over the dock
        _cells(grid, 40, 42, 180005, 180007, GROUND + 4)  # hull-like solid on the river
        _cells(grid, 50, 53, 180005, 180008, GROUND + 7)  # building over the river
    _cells(first, 15, 17, 180005, 180007, GROUND + 10)  # tree: first return high,
    _cells(last, 15, 17, 180005, 180007, GROUND + 1)  # last return near the ground
    buildings = BuildingFootprints([DOCK_BUILDING, RIVER_BUILDING], BNG)
    surface = crown_envelope_surface(last, first, dtm, buildings)
    return lower_moored_boats(
        surface, first, last, dtm,
        moorings=BuildingFootprints([DOCK], BNG),
        water=BuildingFootprints([DOCK, RIVER], BNG),
        buildings=buildings,
        bridges=BuildingFootprints([BRIDGE], BNG),
    )  # fmt: skip


def test_a_boat_moored_in_a_dock_is_lowered_to_the_ground(world):
    assert _at(world.surface, 6, 180006) == GROUND
    assert world.flattened[int(Y_TOP) - 180006, 6]


def test_what_stands_over_a_dock_for_good_stays(world):
    assert _at(world.surface, 16, 180006) == GROUND + 10  # tree
    assert _at(world.surface, 23, 180006) == GROUND + 7  # building
    assert _at(world.surface, 6, 180041) == GROUND + 3  # within 20 m of the bridge


def test_what_stands_over_a_river_stays_and_is_marked_for_review(world):
    assert _at(world.surface, 41, 180006) == GROUND + 4
    assert world.raised_river[int(Y_TOP) - 180006, 41]


def test_a_building_over_a_river_is_not_marked_for_review(world):
    assert _at(world.surface, 51, 180006) == GROUND + 7
    assert not world.raised_river[int(Y_TOP) - 180006, 51]


def test_level_water_is_neither_flattened_nor_marked(world):
    assert not world.raised_river[int(Y_TOP) - 180020, 45]
    assert _at(world.surface, 45, 180020) == GROUND


# --- Reading moorings and bridges from OSM ----------------------------------

NODES = {
    1: (X0, 180000.0), 2: (X0 + 29, 180000.0), 3: (X0 + 29, 180059.0), 4: (X0, 180059.0),
    5: (X0 + 30, 180000.0), 6: (X0 + 59, 180000.0), 7: (X0 + 59, 180059.0), 8: (X0 + 30, 180059.0),
    9: (X0, 180050.0), 10: (X0 + 59, 180050.0),
    11: (X0, 180020.0), 12: (X0 + 59, 180020.0),
    13: (X0 + 10, 180030.0), 14: (X0 + 12, 180030.0),
    15: (X0 + 12, 180032.0), 16: (X0 + 10, 180032.0),
}  # fmt: skip


def test_docks_harbours_and_marinas_are_moorings_and_rivers_are_not(tmp_path: Path):
    ways = [
        (100, [1, 2, 3, 4, 1], {"natural": "water", "water": "harbour"}),
        (101, [5, 6, 7, 8, 5], {"natural": "water", "water": "river"}),
        (102, [13, 14, 15, 16, 13], {"leisure": "marina"}),
    ]
    extract = write_osm_extract(tmp_path / "x.osm.pbf", NODES, ways)
    moorings = read_mooring_water(extract, BNG)
    assert sorted(round(g.area) for g in moorings.geometries) == [4, 29 * 59]


def test_bridges_are_ways_tagged_bridge_and_bridge_structures(tmp_path: Path):
    ways = [
        (200, [9, 10], {"highway": "primary", "bridge": "yes"}),
        (201, [11, 12], {"highway": "primary", "bridge": "no"}),
        (202, [13, 14, 15, 16, 13], {"man_made": "bridge"}),
    ]
    extract = write_osm_extract(tmp_path / "x.osm.pbf", NODES, ways)
    bridges = read_bridges(extract, BNG)
    assert len(bridges) == 2
    assert sorted(round(g.length) for g in bridges.geometries) == [8, 59]
