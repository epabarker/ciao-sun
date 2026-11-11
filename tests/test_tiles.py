"""OS 5 km tile-code correctness: HANDOFF.md #6, test group 7."""

from __future__ import annotations

from ciao_sun.tiles import bng_to_tile_code, tile_codes_for_aoi


def test_bng_origin_is_grid_square_sv():
    # (0, 0) is the true origin of the British National Grid, well-known to be
    # in grid square SV (Isles of Scilly).
    assert bng_to_tile_code(0.0, 0.0) == "SV0000"


def test_central_london_is_grid_square_tq():
    # Central London (easting ~530000, northing ~180000) is well-known to be in
    # grid square TQ.
    assert bng_to_tile_code(530_000.0, 180_000.0) == "TQ3080"


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


def test_tile_codes_for_bristol_aoi_match_downloaded_tiles():
    """Cross-checked against the four EA tile directories actually downloaded
    for this project's area of interest: ST57ne, ST57se, ST67nw, ST67sw. In
    the EA quadrant naming, a 10km square's NE/SE/NW/SW quadrant is exactly
    one 5km tile, e.g. ST57 NE = the tile this project's format calls ST5575.
    """
    codes = tile_codes_for_aoi(51.4720, -2.6040, radius_m=1000)
    downloaded_as_5km_codes = {"ST5575", "ST5570", "ST6070", "ST6075"}
    assert downloaded_as_5km_codes & set(codes), (
        f"expected overlap with downloaded tiles, got {codes}"
    )


def test_tile_codes_are_sorted_and_unique():
    codes = tile_codes_for_aoi(51.4720, -2.6040, radius_m=1500)
    assert codes == sorted(set(codes))
    assert len(codes) > 0
