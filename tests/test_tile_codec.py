"""Tile format f1 (#30): the storage code and the tile codec.

Every assertion reads tile output through the codec's public functions. The
expected values come from the format document (`docs/tile-format-f1.md`), not
from the codec's own arithmetic.
"""

from __future__ import annotations

import dataclasses
import gzip
import re
import struct
from pathlib import Path

import numpy as np
import pytest

from ciao_sun.tile_codec import (
    FULL_CIRCLE,
    OUTSIDE_SECTOR,
    PROFILE_SAMPLES,
    Candidates,
    Sector,
    Tile,
    TileFormatError,
    UnsupportedFormatError,
    WalkGraph,
    codes_to_degrees,
    decode_tile,
    degrees_to_codes,
    encode_tile,
    read_tile,
    write_tile,
)


def test_horizon_profile_angles_below_10_degrees_are_stored_in_tenth_degree_steps():
    codes = degrees_to_codes([-2.0, -1.9, 0.0, 3.7, 10.0])

    assert codes.dtype == np.uint8
    assert codes.tolist() == [0, 1, 20, 57, 120]
    assert codes_to_degrees([0, 1, 20, 57, 120]) == pytest.approx([-2.0, -1.9, 0.0, 3.7, 10.0])


def test_horizon_profile_angles_above_10_degrees_are_stored_in_half_degree_steps():
    assert degrees_to_codes([10.5, 11.0, 37.0, 63.5]).tolist() == [121, 122, 174, 227]
    assert codes_to_degrees([121, 122, 174, 227]) == pytest.approx([10.5, 11.0, 37.0, 63.5])


def test_horizon_profile_angle_survives_storage_within_one_step_at_both_ends():
    low = np.array([-2.0, -1.96, -1.94, 0.04, 9.96, 10.0])
    high = np.array([10.5, 10.7, 10.8, 40.2, 63.3, 63.5])

    assert np.abs(codes_to_degrees(degrees_to_codes(low)) - low).max() <= 0.05 + 1e-9
    assert np.abs(codes_to_degrees(degrees_to_codes(high)) - high).max() <= 0.25 + 1e-9


def test_horizon_profile_angle_between_the_two_steps_takes_the_nearer_code():
    # 10.0 deg (code 120) and 10.5 deg (code 121) are neighbours.
    assert degrees_to_codes([10.2, 10.3]).tolist() == [120, 121]


def test_horizon_profile_angles_outside_the_stored_range_clamp_to_its_ends():
    assert degrees_to_codes([-2.01, -30.0, -90.0]).tolist() == [0, 0, 0]
    assert degrees_to_codes([63.51, 75.0, 90.0]).tolist() == [227, 227, 227]


def test_horizon_profile_angle_that_is_not_a_number_is_refused():
    with pytest.raises(ValueError, match="NaN"):
        degrees_to_codes([1.0, float("nan")])


def test_codes_above_227_are_not_horizon_profile_angles():
    with pytest.raises(ValueError, match="228"):
        codes_to_degrees([0, 228])


# --- The tile codec -------------------------------------------------------


def synthetic_tile() -> Tile:
    """Three Candidates on two Spot names, over a three-node walk graph."""
    rng = np.random.default_rng(30)
    profile_codes = rng.integers(0, 228, size=(3, PROFILE_SAMPLES), dtype=np.uint8)
    # The largest swings a profile can make between adjacent azimuths, both ways
    # and across the 359.75 deg -> 0 deg join.
    profile_codes[0, :4] = [227, 0, 227, 0]
    profile_codes[1, 0], profile_codes[1, -1] = 0, 227
    return Tile(
        grid_ref="ST5873",
        names=("Brandon Hill", "Path off Jacob's Wells Road", "Café Lane"),
        candidates=Candidates(
            lat_e7=np.array([514541000, 514541900, 514550000], dtype=np.int32),
            lon_e7=np.array([-26070000, -26068500, -26059999], dtype=np.int32),
            node_index=np.array([2, 0, 1], dtype=np.uint32),
            offset_cm=np.array([0, 730, 1199], dtype=np.uint32),
            name_index=np.array([0, 0, 2], dtype=np.uint32),
            profile_codes=profile_codes,
        ),
        walk_graph=WalkGraph(
            node_id=np.array([101, 2**53 - 1, 12_345_678_901], dtype=np.uint64),
            node_lat_e7=np.array([514540000, 514545000, 514639999], dtype=np.int32),
            node_lon_e7=np.array([-26071000, -26066000, -25990001], dtype=np.int32),
            edge_from=np.array([0, 1], dtype=np.uint32),
            edge_to=np.array([1, 2], dtype=np.uint32),
            edge_length_cm=np.array([6543, 123_456], dtype=np.uint32),
        ),
    )


def assert_same_tile(actual: Tile, expected: Tile) -> None:
    assert actual.grid_ref == expected.grid_ref
    assert actual.names == expected.names
    for part in ("candidates", "walk_graph"):
        got, want = getattr(actual, part), getattr(expected, part)
        for field in dataclasses.fields(want):
            a, e = getattr(got, field.name), getattr(want, field.name)
            assert a.dtype == e.dtype, f"{part}.{field.name}"
            assert a.shape == e.shape, f"{part}.{field.name}"
            assert a.tobytes() == e.tobytes(), f"{part}.{field.name}"


def test_tile_round_trips_every_candidate_and_walk_graph_field_byte_exact():
    tile = synthetic_tile()

    assert_same_tile(decode_tile(encode_tile(tile)), tile)


def test_tile_with_no_candidates_and_no_walk_graph_round_trips():
    empty = Tile(
        grid_ref="ST5873",
        names=(),
        candidates=Candidates(
            lat_e7=np.zeros(0, np.int32),
            lon_e7=np.zeros(0, np.int32),
            node_index=np.zeros(0, np.uint32),
            offset_cm=np.zeros(0, np.uint32),
            name_index=np.zeros(0, np.uint32),
            profile_codes=np.zeros((0, PROFILE_SAMPLES), np.uint8),
        ),
        walk_graph=WalkGraph(
            node_id=np.zeros(0, np.uint64),
            node_lat_e7=np.zeros(0, np.int32),
            node_lon_e7=np.zeros(0, np.int32),
            edge_from=np.zeros(0, np.uint32),
            edge_to=np.zeros(0, np.uint32),
            edge_length_cm=np.zeros(0, np.uint32),
        ),
    )

    assert_same_tile(decode_tile(encode_tile(empty)), empty)


def test_candidates_on_one_spot_share_its_spot_name():
    tile = decode_tile(encode_tile(synthetic_tile()))

    assert tile.spot_name(0) == "Brandon Hill"
    assert tile.spot_name(1) == "Brandon Hill"
    assert tile.spot_name(2) == "Café Lane"


def test_same_tile_always_encodes_to_the_same_bytes():
    # Published builds are immutable, so a rebuild of the same data must not
    # differ by a gzip timestamp.
    assert encode_tile(synthetic_tile()) == encode_tile(synthetic_tile())


def worked_example_payload() -> bytes:
    """The uncompressed bytes of the format document's worked example.

    Built by hand from the document's field tables, independently of the
    writer: one Candidate on a two-node, one-edge walk graph.
    """
    deltas = bytearray(PROFILE_SAMPLES)
    # Codes: 20 (0.0 deg) all round, except a ridge due east: samples 360, 361
    # and 362 hold codes 25, 130, 25.
    deltas[0] = 20
    deltas[360] = 5  # 20 -> 25
    deltas[361] = 105  # 25 -> 130
    deltas[362] = 151  # 130 -> 25 is -105, stored mod 256
    deltas[363] = 251  # 25 -> 20 is -5, stored mod 256
    name = b"Brandon Hill"
    return b"".join(
        [
            b"CSUN",
            struct.pack("<H", 1),
            b"ST5873",
            struct.pack("<IIII", 1, 2, 1, 1),  # Candidates, nodes, edges, names
            struct.pack("<HH", 0, 1440),  # sector: first sample, samples (the full circle)
            struct.pack("<i", 514541000),  # Candidate latitude
            struct.pack("<i", -26070000),  # Candidate longitude
            struct.pack("<I", 1),  # snapped walk node (index)
            struct.pack("<I", 730),  # offset, cm
            struct.pack("<I", 0),  # Spot name (index)
            struct.pack("<QQ", 101, 2**40 + 7),  # node ids
            struct.pack("<ii", 514540000, 514545000),  # node latitudes
            struct.pack("<ii", -26071000, -26066000),  # node longitudes
            struct.pack("<I", 0),  # edge from (index)
            struct.pack("<I", 1),  # edge to (index)
            struct.pack("<I", 6543),  # edge length, cm
            bytes(deltas),
            struct.pack("<H", len(name)),
            name,
        ]
    )


def test_format_documents_worked_example_reads_as_the_tile_it_describes():
    tile = decode_tile(gzip.compress(worked_example_payload()))

    assert tile.grid_ref == "ST5873"
    assert tile.spot_name(0) == "Brandon Hill"
    assert tile.candidates.lat_e7.tolist() == [514541000]
    assert tile.candidates.lon_e7.tolist() == [-26070000]
    assert tile.candidates.node_index.tolist() == [1]
    assert tile.candidates.offset_cm.tolist() == [730]
    assert tile.walk_graph.node_id.tolist() == [101, 2**40 + 7]
    assert tile.walk_graph.node_lat_e7.tolist() == [514540000, 514545000]
    assert tile.walk_graph.node_lon_e7.tolist() == [-26071000, -26066000]
    assert tile.walk_graph.edge_from.tolist() == [0]
    assert tile.walk_graph.edge_to.tolist() == [1]
    assert tile.walk_graph.edge_length_cm.tolist() == [6543]


def test_horizon_profile_is_indexed_by_true_azimuth_in_quarter_degree_steps():
    tile = decode_tile(gzip.compress(worked_example_payload()))

    profile = tile.horizon_profile_degrees(0)

    assert profile.shape == (PROFILE_SAMPLES,)
    # The worked example's ridge is due east: true azimuth 90 deg is sample 360.
    assert profile[359:364] == pytest.approx([0.0, 0.5, 15.0, 0.5, 0.0])
    assert profile[0] == pytest.approx(0.0)  # north
    assert profile[1439] == pytest.approx(0.0)  # 359.75 deg


def test_writer_produces_the_format_documents_worked_example():
    tile = decode_tile(gzip.compress(worked_example_payload()))

    assert gzip.decompress(encode_tile(tile)) == worked_example_payload()


# --- Sectors: a tile holds only the azimuths its window can need ----------


def _in_sector(first: int, samples: int) -> Tile:
    return dataclasses.replace(synthetic_tile(), sector=Sector(first, samples))


def test_a_tile_holding_a_sector_reads_back_with_the_rest_of_the_circle_marked_outside():
    tile = _in_sector(144, 616)  # 36 deg to 190 deg, as a Bristol morning

    back = decode_tile(encode_tile(tile))

    assert back.sector == Sector(144, 616)
    codes = back.candidates.profile_codes
    assert codes.shape == (3, PROFILE_SAMPLES)
    sector = slice(144, 760)
    assert codes[:, sector].tobytes() == tile.candidates.profile_codes[:, sector].tobytes()
    assert (codes[:, :144] == OUTSIDE_SECTOR).all()
    assert (codes[:, 760:] == OUTSIDE_SECTOR).all()


def test_a_sector_may_run_on_past_north():
    tile = _in_sector(1400, 100)  # 350 deg round to 15 deg

    codes = decode_tile(encode_tile(tile)).candidates.profile_codes

    kept = np.r_[1400:1440, 0:60]
    assert codes[:, kept].tobytes() == tile.candidates.profile_codes[:, kept].tobytes()
    assert (codes[:, 60:1400] == OUTSIDE_SECTOR).all()


def test_the_writer_stores_only_the_sectors_samples():
    whole = gzip.decompress(encode_tile(synthetic_tile()))
    morning = gzip.decompress(encode_tile(_in_sector(144, 616)))

    assert len(whole) - len(morning) == 3 * (PROFILE_SAMPLES - 616)


def test_a_tile_holds_the_full_circle_unless_given_a_sector():
    assert synthetic_tile().sector == FULL_CIRCLE == Sector(0, PROFILE_SAMPLES)


def test_reading_a_horizon_profile_outside_its_sector_is_refused():
    tile = decode_tile(encode_tile(_in_sector(144, 616)))

    with pytest.raises(ValueError, match="228"):
        tile.horizon_profile_degrees(0)


@pytest.mark.parametrize(("first", "samples"), [(1440, 10), (0, 0), (0, 1441)])
def test_a_sector_outside_the_circle_is_refused(first, samples):
    with pytest.raises(TileFormatError, match="sector"):
        encode_tile(_in_sector(first, samples))
    payload = bytearray(worked_example_payload())
    payload[28:32] = struct.pack("<HH", first, samples)
    with pytest.raises(TileFormatError, match="sector"):
        decode_tile(gzip.compress(bytes(payload)))


# --- What the codec refuses ----------------------------------------------


def test_tile_in_a_later_format_is_refused_as_unsupported():
    payload = bytearray(worked_example_payload())
    payload[4:6] = struct.pack("<H", 2)

    with pytest.raises(UnsupportedFormatError, match="f2"):
        decode_tile(gzip.compress(bytes(payload)))


def test_bytes_that_are_not_a_tile_are_refused():
    with pytest.raises(TileFormatError, match="gzip"):
        decode_tile(b"not a tile")
    with pytest.raises(TileFormatError, match="magic"):
        decode_tile(gzip.compress(b"NOPE" + worked_example_payload()[4:]))


def test_tile_cut_short_or_with_trailing_bytes_is_refused():
    payload = worked_example_payload()

    with pytest.raises(TileFormatError, match="truncated"):
        decode_tile(gzip.compress(payload[:-1]))
    with pytest.raises(TileFormatError, match="truncated"):
        decode_tile(gzip.compress(payload[:10]))
    with pytest.raises(TileFormatError, match="after its last field"):
        decode_tile(gzip.compress(payload + b"\x00"))


def test_horizon_profile_holding_a_code_above_227_is_refused_by_writer_and_reader():
    tile = synthetic_tile()
    tile.candidates.profile_codes[2, 700] = 228
    with pytest.raises(TileFormatError, match="228"):
        encode_tile(tile)

    payload = bytearray(worked_example_payload())
    profile_start = 32 + 5 * 4 + 2 * 16 + 3 * 4
    payload[profile_start] = 240  # first delta is the first code itself
    with pytest.raises(TileFormatError, match="storage codes"):
        decode_tile(gzip.compress(bytes(payload)))


@pytest.mark.parametrize(
    ("part", "field", "what"),
    [
        ("candidates", "node_index", "walk node"),
        ("candidates", "name_index", "Spot name"),
        ("walk_graph", "edge_from", "'from' node"),
        ("walk_graph", "edge_to", "'to' node"),
    ],
)
def test_candidate_or_edge_pointing_outside_its_table_is_refused(part, field, what):
    tile = synthetic_tile()
    getattr(getattr(tile, part), field)[0] = 3  # three nodes, three names: 0-2

    with pytest.raises(TileFormatError, match=what):
        encode_tile(tile)


def test_walk_node_id_too_large_for_a_double_is_refused():
    tile = synthetic_tile()
    tile.walk_graph.node_id[0] = 2**53

    with pytest.raises(TileFormatError, match="2\\^53"):
        encode_tile(tile)


def test_two_walk_nodes_sharing_an_id_in_one_tile_are_refused():
    tile = synthetic_tile()
    tile.walk_graph.node_id[2] = tile.walk_graph.node_id[0]

    with pytest.raises(TileFormatError, match="unique"):
        encode_tile(tile)


def test_candidate_field_of_the_wrong_width_is_refused_rather_than_cast():
    tile = synthetic_tile()
    wide = dataclasses.replace(tile.candidates, lat_e7=tile.candidates.lat_e7.astype(np.int64))

    with pytest.raises(TileFormatError, match="Candidate latitude"):
        encode_tile(dataclasses.replace(tile, candidates=wide))


def test_tile_named_by_something_other_than_a_1km_grid_ref_is_refused():
    with pytest.raises(TileFormatError, match="grid ref"):
        encode_tile(dataclasses.replace(synthetic_tile(), grid_ref="ST5570x"))


# --- Tile files -----------------------------------------------------------


def test_tile_file_is_named_by_its_os_grid_ref_and_reads_back(tmp_path):
    tile = synthetic_tile()

    path = write_tile(tile, tmp_path / "tiles")

    assert path == tmp_path / "tiles" / "ST5873.bin"
    assert_same_tile(read_tile(path), tile)


def test_tile_file_renamed_to_another_grid_ref_is_refused(tmp_path):
    path = write_tile(synthetic_tile(), tmp_path)
    moved = path.rename(tmp_path / "ST5874.bin")

    with pytest.raises(TileFormatError, match="ST5873"):
        read_tile(moved)


def test_format_document_prints_the_worked_example_byte_for_byte():
    """The hex in the document is what a builder in another language will copy."""
    document = (Path(__file__).parent.parent / "docs" / "tile-format-f1.md").read_text()
    table = document.split("## Worked example")[1].split("## Not in the tile")[0]
    payload = worked_example_payload()

    described = 0
    for row in re.findall(r"^\| (\d[\d,]*) \| (.+?) \|", table, flags=re.MULTILINE):
        offset, cell = int(row[0].replace(",", "")), row[1]
        assert offset == described, f"gap or overlap before offset {offset}"
        for run in cell.split(", then "):
            hex_bytes, _, repeat = run.strip("`").partition("` × ")
            expected = bytes.fromhex(hex_bytes) * int(repeat or 1)
            assert payload[described : described + len(expected)] == expected, f"at {offset}"
            described += len(expected)
    assert described == len(payload) == 1550
