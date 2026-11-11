"""Candidates, the walk graph and Spot names, built from a synthetic OSM extract.

The world straddles the boundary between tiles ST5873 and ST5973 (easting
359000). Everything is asserted on tiles read back through the tile codec.

    northing
    173650        6
                  | steps
    173600        5                 7
          +-------|-+               |
          | park  | |footway        | service ("lane")
          |   10  | |               |
          |    |  | |               |
    173500  1--9--+-2------|--------3---------4    High Street
          +---------+      |        |
    173420                 |        8  private drive
                        359000
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from ciao_sun.candidates import build_tile, grid_ref_origin, load_walk_network
from ciao_sun.raster import RasterGrid
from ciao_sun.tile_codec import PROFILE_SAMPLES, Tile, read_tile, write_tile
from tests.conftest import make_flat_grid
from tests.osm_extract import bng_of, write_osm_extract

SNAP_M = 12.0
# Stored positions are whole units of 1e-7 degrees, about 1 cm.
POSITION_TOLERANCE_M = 0.02

NODES = {
    1: (358850.0, 173500.0),
    2: (358950.0, 173500.0),
    3: (359050.0, 173500.0),
    4: (359150.0, 173500.0),
    5: (358950.0, 173600.0),
    6: (358950.0, 173650.0),
    7: (359050.0, 173600.0),
    8: (359050.0, 173420.0),
    9: (358900.0, 173500.0),
    10: (358900.0, 173580.0),
    # Castle Green's outline, kept off the 10 m grid so no Candidate sits on it.
    20: (358855.0, 173495.0),
    21: (358945.0, 173495.0),
    22: (358945.0, 173595.0),
    23: (358855.0, 173595.0),
}
PUBLIC_WAYS = [
    (100, [1, 9, 2, 3, 4], {"highway": "residential", "name": "High Street"}),
    (101, [2, 5], {"highway": "footway"}),
    (102, [5, 6], {"highway": "steps"}),
    (103, [3, 7], {"highway": "service"}),
    (104, [9, 10], {"highway": "path"}),
]
PRIVATE_WAY = (105, [3, 8], {"highway": "service", "access": "private"})
PARK = (200, [20, 21, 22, 23, 20], {"leisure": "park", "name": "Castle Green"})

# The rasters cover eastings 358800-359200 and northings 173400-173700 at 1 m,
# with a pixel centred on every whole metre.
RASTER_WEST, RASTER_NORTH = 358800, 173700
GROUND_M = 10.0
BUILDING = [(359010, 173490), (359020, 173490), (359030, 173490)]  # beside High Street
KERB = (358880, 173490)  # 0.5 m of clutter
STEP_UP = (358870, 173490)  # exactly 1 m


def _rasters() -> tuple[RasterGrid, RasterGrid]:
    dtm = make_flat_grid(GROUND_M, RASTER_WEST, RASTER_NORTH, width=401, height=301)
    dsm = make_flat_grid(GROUND_M, RASTER_WEST, RASTER_NORTH, width=401, height=301)

    def raise_by(easting: int, northing: int, metres: float, half_width: int = 0) -> None:
        row, col = RASTER_NORTH - northing, easting - RASTER_WEST
        dsm.data[
            row - half_width : row + half_width + 1, col - half_width : col + half_width + 1
        ] = GROUND_M + metres

    for easting, northing in BUILDING:
        raise_by(easting, northing, 8.0, half_width=4)
    raise_by(*KERB, 0.5)
    raise_by(*STEP_UP, 1.0)
    return dsm, dtm


def _build(tmp_path: Path, ways, nodes=NODES) -> dict[str, Tile]:
    """Build both tiles, write them, and read them back through the codec."""
    extract = write_osm_extract(tmp_path / "synthetic.osm.pbf", nodes, ways)
    network = load_walk_network(extract)
    dsm, dtm = _rasters()
    tiles: dict[str, Tile] = {}
    for grid_ref in ("ST5873", "ST5973"):
        outline = build_tile(network, grid_ref, dsm, dtm)
        assert outline is not None
        flat = np.full((outline.easting.size, PROFILE_SAMPLES), 20, dtype=np.uint8)
        path = write_tile(outline.with_profiles(flat), tmp_path / "tiles")
        tiles[grid_ref] = read_tile(path)
    return tiles


@pytest.fixture
def tiles(tmp_path: Path) -> dict[str, Tile]:
    return _build(tmp_path, [*PUBLIC_WAYS, PRIVATE_WAY, PARK])


def _candidates(tile: Tile) -> dict[tuple[int, int], int]:
    """Each Candidate's (easting, northing), to the metre -> its index in the tile."""
    found: dict[tuple[int, int], int] = {}
    c = tile.candidates
    for index in range(c.lat_e7.size):
        easting, northing = bng_of(int(c.lat_e7[index]), int(c.lon_e7[index]))
        assert abs(easting - round(easting)) < POSITION_TOLERANCE_M
        assert abs(northing - round(northing)) < POSITION_TOLERANCE_M
        found[(round(easting), round(northing))] = index
    assert len(found) == c.lat_e7.size
    return found


def _all_candidates(tiles: dict[str, Tile]) -> set[tuple[int, int]]:
    return {position for tile in tiles.values() for position in _candidates(tile)}


def _spot_name(tiles: dict[str, Tile], easting: int, northing: int) -> str:
    for tile in tiles.values():
        index = _candidates(tile).get((easting, northing))
        if index is not None:
            return tile.spot_name(index)
    raise AssertionError(f"no Candidate at {easting}, {northing}")


def _distance_to_way(point: tuple[float, float], refs: list[int]) -> float:
    px, py = point
    best = math.inf
    for a, b in zip(refs, refs[1:], strict=False):
        (ax, ay), (bx, by) = NODES[a], NODES[b]
        t = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)
        t = min(1.0, max(0.0, t))
        best = min(best, math.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay))))
    return best


def _edges(tile: Tile) -> dict[frozenset[int], int]:
    """Each edge's pair of node ids -> its length in centimetres."""
    g = tile.walk_graph
    return {
        frozenset({int(g.node_id[a]), int(g.node_id[b])}): int(length)
        for a, b, length in zip(g.edge_from, g.edge_to, g.edge_length_cm, strict=True)
    }


# --- Where Candidates are ---------------------------------------------------


def test_candidates_are_a_10_m_grid_along_public_walk_edges(tiles):
    found = _all_candidates(tiles)
    # On High Street, 10 m either side of it, and along the unnamed ways.
    for position in [
        (358900, 173500), (358900, 173510), (358900, 173490),
        (358950, 173550), (358950, 173630), (359050, 173550), (359100, 173500),
    ]:  # fmt: skip
        assert position in found
    assert all(easting % 10 == 0 and northing % 10 == 0 for easting, northing in found)


def test_no_candidate_is_more_than_12_m_from_a_public_walk_edge(tiles):
    found = _all_candidates(tiles)
    assert found
    for position in found:
        nearest = min(_distance_to_way(position, refs) for _, refs, _ in PUBLIC_WAYS)
        assert nearest <= SNAP_M + POSITION_TOLERANCE_M, position
    # 20 m from High Street; 30 m from anything, inside the park.
    assert (359000, 173520) not in found
    assert (358870, 173550) not in found


def test_a_candidate_belongs_to_the_tile_whose_square_holds_it(tiles):
    for grid_ref, tile in tiles.items():
        west, south = grid_ref_origin(grid_ref)
        for easting, northing in _candidates(tile):
            assert west <= easting < west + 1000
            assert south <= northing < south + 1000
    # The boundary easting itself is the eastern tile's.
    assert (359000, 173500) in _candidates(tiles["ST5973"])


def test_no_candidate_is_on_a_private_way(tiles):
    found = _all_candidates(tiles)
    # Along the private drive, clear of High Street's 12 m.
    for northing in (173480, 173470, 173450, 173430, 173420):
        assert (359050, northing) not in found
    # The drive is not in the walk graph either.
    for tile in tiles.values():
        assert 8 not in tile.walk_graph.node_id.tolist()


def test_a_way_private_to_cars_but_open_on_foot_is_public(tmp_path):
    drive_with_footpath = (105, [3, 8], {"highway": "service", "access": "private", "foot": "yes"})
    tiles = _build(tmp_path, [*PUBLIC_WAYS, drive_with_footpath])
    assert (359050, 173450) in _all_candidates(tiles)


def test_no_candidate_stands_where_the_surface_is_over_1_m_above_the_ground(tiles):
    found = _all_candidates(tiles)
    for position in BUILDING:
        assert position not in found
    # Beside the building, and on clutter of 0.5 m and of exactly 1 m.
    assert (359040, 173490) in found
    assert KERB in found
    assert STEP_UP in found


def test_no_candidate_stands_outside_the_lidar(tmp_path):
    nodes_beyond = {**NODES, 4: (359300.0, 173500.0)}  # High Street runs off the raster
    extract = write_osm_extract(tmp_path / "synthetic.osm.pbf", nodes_beyond, PUBLIC_WAYS)
    outline = build_tile(load_walk_network(extract), "ST5973", *_rasters())
    assert outline is not None
    assert outline.easting.max() == 359200


# --- Snapping ---------------------------------------------------------------


def test_a_candidate_snaps_to_the_nearer_end_of_its_nearest_edge(tiles):
    tile = tiles["ST5873"]
    c, g = tile.candidates, tile.walk_graph
    found = _candidates(tile)

    on_street = found[(358880, 173500)]  # between nodes 9 (20 m away) and 1 (30 m away)
    assert int(g.node_id[c.node_index[on_street]]) == 9
    assert int(c.offset_cm[on_street]) == pytest.approx(2000, abs=2)

    beside_street = found[(358860, 173510)]  # 10 m east and 10 m north of node 1
    assert int(g.node_id[c.node_index[beside_street]]) == 1
    assert int(c.offset_cm[beside_street]) == pytest.approx(1414, abs=2)


def test_the_outline_gives_candidate_positions_in_candidate_order(tmp_path, tiles):
    ways = [*PUBLIC_WAYS, PRIVATE_WAY, PARK]
    extract = write_osm_extract(tmp_path / "again.osm.pbf", NODES, ways)
    outline = build_tile(load_walk_network(extract), "ST5873", *_rasters())
    assert outline is not None
    by_position = _candidates(tiles["ST5873"])
    for index, position in enumerate(zip(outline.easting, outline.northing, strict=True)):
        assert by_position[(int(position[0]), int(position[1]))] == index


# --- Spot names -------------------------------------------------------------


def test_a_candidate_in_a_named_green_space_takes_its_name(tiles):
    # On High Street, and on the unnamed path, both inside Castle Green.
    assert _spot_name(tiles, 358900, 173500) == "Castle Green"
    assert _spot_name(tiles, 358900, 173560) == "Castle Green"


def test_a_candidate_outside_any_green_space_takes_its_street(tiles):
    assert _spot_name(tiles, 358900, 173490) == "High Street"  # just south of the park
    assert _spot_name(tiles, 359100, 173510) == "High Street"


def test_a_candidate_on_an_unnamed_way_is_named_off_the_nearest_named_street(tiles):
    assert _spot_name(tiles, 358950, 173550) == "Path off High Street"
    assert _spot_name(tiles, 358950, 173630) == "Steps off High Street"
    assert _spot_name(tiles, 359050, 173550) == "Lane off High Street"


def test_the_nearest_named_street_is_the_nearest_along_the_walk_graph(tmp_path):
    # A path from the far end of the lane: 30 m on to Back Road, but 130 m back to
    # High Street.
    nodes = {**NODES, 11: (359050.0, 173630.0), 12: (359100.0, 173630.0)}
    ways = [
        *PUBLIC_WAYS,
        (106, [7, 11], {"highway": "footway"}),
        (107, [11, 12], {"highway": "residential", "name": "Back Road"}),
    ]
    extract = write_osm_extract(tmp_path / "synthetic.osm.pbf", nodes, ways)
    outline = build_tile(load_walk_network(extract), "ST5973", *_rasters())
    assert outline is not None
    names = {
        (int(e), int(n)): outline.names[int(i)]
        for e, n, i in zip(outline.easting, outline.northing, outline.name_index, strict=True)
    }
    assert names[(359050, 173610)] == "Path off Back Road"
    assert names[(359050, 173530)] == "Lane off High Street"


def test_an_unnamed_way_joined_to_no_named_street_is_named_by_its_kind(tmp_path):
    ways = [(101, [2, 5], {"highway": "footway"}), (103, [3, 7], {"highway": "track"})]
    tiles = _build(tmp_path, ways)
    assert _spot_name(tiles, 358950, 173550) == "Path"
    assert _spot_name(tiles, 359050, 173550) == "Lane"


def test_a_green_space_mapped_as_a_multipolygon_names_what_is_inside_it(tmp_path):
    # The same park as a relation of two open ways, with a hole around (358900, 173560).
    nodes = {
        **NODES,
        30: (358885.0, 173545.0),
        31: (358915.0, 173545.0),
        32: (358915.0, 173575.0),
        33: (358885.0, 173575.0),
    }
    ways = [
        *PUBLIC_WAYS,
        (201, [20, 21, 22], {}),
        (202, [22, 23, 20], {}),
        (203, [30, 31, 32, 33, 30], {}),
    ]
    relation = (
        300,
        [(201, "outer"), (202, "outer"), (203, "inner")],
        {"type": "multipolygon", "leisure": "park", "name": "Castle Green"},
    )
    extract = write_osm_extract(tmp_path / "synthetic.osm.pbf", nodes, ways, [relation])
    outline = build_tile(load_walk_network(extract), "ST5873", *_rasters())
    assert outline is not None
    names = {
        (int(e), int(n)): outline.names[int(i)]
        for e, n, i in zip(outline.easting, outline.northing, outline.name_index, strict=True)
    }
    assert names[(358900, 173520)] == "Castle Green"
    assert names[(358900, 173560)] == "Path off High Street"  # in the hole


def test_the_smallest_containing_green_space_names_the_candidate(tmp_path):
    nodes = {
        **NODES,
        40: (358885.0, 173545.0),
        41: (358915.0, 173545.0),
        42: (358915.0, 173575.0),
        43: (358885.0, 173575.0),
    }
    rose_garden = (204, [40, 41, 42, 43, 40], {"leisure": "park", "name": "Rose Garden"})
    tiles = _build(tmp_path, [*PUBLIC_WAYS, PARK, rose_garden], nodes)
    assert _spot_name(tiles, 358900, 173560) == "Rose Garden"
    assert _spot_name(tiles, 358900, 173520) == "Castle Green"


# --- The walk graph ---------------------------------------------------------


def test_the_walk_graph_holds_the_public_ways_with_their_lengths(tiles):
    edges = _edges(tiles["ST5873"])
    assert edges[frozenset({1, 9})] == pytest.approx(5000, abs=3)
    assert edges[frozenset({2, 5})] == pytest.approx(10000, abs=3)
    assert edges[frozenset({5, 6})] == pytest.approx(5000, abs=3)
    assert frozenset({3, 8}) not in edges


def test_an_edge_crossing_the_tile_boundary_is_in_both_tiles_with_the_same_node_ids(tiles):
    west, east = _edges(tiles["ST5873"]), _edges(tiles["ST5973"])
    crossing = frozenset({2, 3})
    assert crossing in west and crossing in east
    assert west[crossing] == east[crossing] == pytest.approx(10000, abs=3)
    # Edges wholly on one side are in that tile only.
    assert frozenset({1, 9}) not in east
    assert frozenset({3, 4}) not in west


def test_a_tile_holds_its_walk_edges_even_where_nobody_can_stand(tmp_path):
    extract = write_osm_extract(tmp_path / "synthetic.osm.pbf", NODES, PUBLIC_WAYS)
    network = load_walk_network(extract)
    dsm, dtm = _rasters()
    dsm.data[:] = GROUND_M + 5.0  # under trees or roofs everywhere
    for grid_ref in ("ST5873", "ST5973"):
        outline = build_tile(network, grid_ref, dsm, dtm)
        assert outline is not None
        assert outline.easting.size == 0
        tile = outline.with_profiles(np.zeros((0, PROFILE_SAMPLES), dtype=np.uint8))
        assert frozenset({2, 3}) in _edges(read_tile(write_tile(tile, tmp_path / "tiles")))


def test_node_ids_and_positions_are_the_same_in_every_tile(tiles):
    seen: dict[int, tuple[int, int]] = {}
    for tile in tiles.values():
        g = tile.walk_graph
        for node_id, lat, lon in zip(g.node_id, g.node_lat_e7, g.node_lon_e7, strict=True):
            position = (int(lat), int(lon))
            assert seen.setdefault(int(node_id), position) == position
            easting, northing = bng_of(*position)
            assert math.hypot(
                easting - NODES[int(node_id)][0], northing - NODES[int(node_id)][1]
            ) < POSITION_TOLERANCE_M
    assert {2, 3} <= set(seen)


def test_a_square_with_no_candidates_and_no_walk_edges_has_no_tile(tmp_path):
    extract = write_osm_extract(tmp_path / "synthetic.osm.pbf", NODES, PUBLIC_WAYS)
    network = load_walk_network(extract)
    assert build_tile(network, "ST6073", *_rasters()) is None
    assert network.grid_refs() == ["ST5873", "ST5973"]
