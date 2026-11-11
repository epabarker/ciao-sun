"""OS 5 km tile-code correctness: HANDOFF.md #6, test group 7."""

from __future__ import annotations

from ciao_sun.tiles import bng_to_tile_code, grid_ref_origin, tile_codes_near_polygon


def test_bng_origin_is_grid_square_sv():
    # (0, 0) is the true origin of the British National Grid, well-known to be
    # in grid square SV (Isles of Scilly).
    assert bng_to_tile_code(0.0, 0.0) == "SV0000"


def test_central_london_is_grid_square_tq():
    # Central London (easting ~530000, northing ~180000) is well-known to be in
    # grid square TQ.
    assert bng_to_tile_code(530_000.0, 180_000.0) == "TQ3080"


def test_a_1km_grid_ref_names_the_square_by_its_south_west_corner():
    # docs/tile-format-f1.md: ST5873.bin is the square whose south-west corner
    # is 358000 E, 173000 N.
    assert grid_ref_origin("ST5873") == (358000, 173000)
    assert grid_ref_origin("TQ3080") == (530000, 180000)
    assert grid_ref_origin("SV0000") == (0, 0)


def test_100km_boundary_crossing():
    # e100k=2 (SO/SS/...) vs e100k=3 (ST/SU/...) boundary at easting 300000,
    # same 100km northing band (n100k=1). The two-letter prefix must change
    # exactly at the boundary.
    just_below = bng_to_tile_code(299_999.0, 150_000.0)
    just_above = bng_to_tile_code(300_000.0, 150_000.0)
    assert just_below[:2] != just_above[:2]
    assert just_below[:2] == "SS"
    assert just_above[:2] == "ST"


def test_tile_code_within_square_is_5km_aligned():
    code = bng_to_tile_code(356_234.0, 174_876.0)
    assert code[:2] == "ST"
    e5, n5 = int(code[2:4]), int(code[4:6])
    assert e5 % 5 == 0 and n5 % 5 == 0
    assert code == "ST5570"


def _square(cx: float, cy: float, half: float) -> list[tuple[float, float]]:
    return [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half),
            (cx - half, cy + half)]


# The centre of ST5570, whose edges are 2.5 km away and corners 3.5 km away.
_ST5570_CENTRE = (357_500.0, 172_500.0)


def test_polygon_inside_one_tile_needs_only_that_tile_without_a_margin():
    rings = [_square(*_ST5570_CENTRE, 50.0)]
    assert tile_codes_near_polygon(rings, 0.0) == ["ST5570"]


def test_3km_margin_reaches_edge_neighbours_but_not_diagonal_ones():
    # 50 m square at the tile centre: edge neighbours are 2450 m away,
    # diagonal neighbours 2450 * sqrt(2) = 3465 m away.
    rings = [_square(*_ST5570_CENTRE, 50.0)]
    assert tile_codes_near_polygon(rings, 3000.0) == [
        "ST5070", "ST5565", "ST5570", "ST5575", "ST6070",
    ]
    assert len(tile_codes_near_polygon(rings, 3500.0)) == 9


def test_tile_wholly_inside_the_polygon_is_included():
    # A 14 km square around the tile: no polygon vertex or edge touches ST5570.
    rings = [_square(*_ST5570_CENTRE, 7000.0)]
    codes = tile_codes_near_polygon(rings, 0.0)
    assert "ST5570" in codes
    assert len(codes) == 9


def test_thin_polygon_crossing_a_tile_with_no_vertex_in_it_is_included():
    sliver = [(352_000.0, 172_400.0), (363_000.0, 172_400.0), (363_000.0, 172_600.0),
              (352_000.0, 172_600.0)]
    assert tile_codes_near_polygon([sliver], 0.0) == ["ST5070", "ST5570", "ST6070"]


def test_every_part_of_a_multi_part_coverage_is_served():
    rings = [_square(*_ST5570_CENTRE, 50.0), _square(377_500.0, 172_500.0, 50.0)]
    assert tile_codes_near_polygon(rings, 0.0) == ["ST5570", "ST7570"]
