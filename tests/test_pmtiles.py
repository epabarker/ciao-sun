"""PMTiles v3 archives: tile ids, and reading back what was written."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from ciao_sun.pmtiles import (
    COMPRESSION_GZIP,
    COMPRESSION_NONE,
    ROOT_REACH_BYTES,
    Archive,
    PMTilesError,
    tile_id,
    write_archive,
    zxy_of,
)

BRISTOL = (-2.72, 51.39, -2.51, 51.55)


def test_tile_ids_follow_the_hilbert_curve_of_the_pmtiles_spec():
    # The worked examples of the PMTiles v3 spec, section 4.1.
    examples = {
        (0, 0, 0): 0, (1, 0, 0): 1, (1, 0, 1): 2, (1, 1, 1): 3, (1, 1, 0): 4, (2, 0, 0): 5,
        (12, 3423, 1763): 19078479,
    }  # fmt: skip
    for zxy, expected in examples.items():
        assert tile_id(*zxy) == expected
        assert zxy_of(expected) == zxy


def test_a_tile_outside_its_zoom_level_has_no_id():
    with pytest.raises(PMTilesError, match="2/4/0"):
        tile_id(2, 4, 0)


def test_an_archive_gives_back_its_tiles_metadata_and_header(tmp_path: Path):
    tiles = {(0, 0, 0): b"world", (14, 8072, 5446): b"bristol", (14, 8073, 5446): b"next door"}
    write_archive(
        tmp_path / "a.pmtiles", tiles, metadata={"version": "4.15.1"},
        tile_compression=COMPRESSION_NONE, bounds=BRISTOL,
    )  # fmt: skip

    archive = Archive.open(tmp_path / "a.pmtiles")

    for (z, x, y), content in tiles.items():
        assert archive.tile(z, x, y) == content
    assert archive.tile(14, 8074, 5446) is None
    assert archive.tile(1, 0, 0) is None
    assert archive.metadata() == {"version": "4.15.1"}
    assert (archive.header.min_zoom, archive.header.max_zoom) == (0, 14)
    assert archive.header.bounds == BRISTOL
    assert archive.header.tile_compression == COMPRESSION_NONE


def test_an_archive_too_big_for_one_directory_is_read_through_leaf_directories(tmp_path: Path):
    # Scattered tiles with unequal lengths, so the directory does not compress away.
    tiles = {
        (15, x * 7 % 32768, y * 13 % 32768): bytes([x % 251]) * (1 + (x * y) % 97)
        for x in range(0, 300)
        for y in range(1, 60)
    }
    write_archive(
        tmp_path / "big.pmtiles", tiles, metadata={},
        tile_compression=COMPRESSION_NONE, bounds=BRISTOL,
    )  # fmt: skip

    archive = Archive.open(tmp_path / "big.pmtiles")

    assert archive.header.leaf_length > 0
    assert archive.header.root_offset + archive.header.root_length <= ROOT_REACH_BYTES
    for (z, x, y), content in tiles.items():
        assert archive.tile(z, x, y) == content


def test_writing_the_same_tiles_twice_gives_the_same_bytes(tmp_path: Path):
    tiles = {(3, 1, 2): gzip.compress(b"a", mtime=0), (3, 2, 2): gzip.compress(b"b", mtime=0)}
    for name in ("one", "two"):
        write_archive(
            tmp_path / name, dict(reversed(tiles.items())) if name == "two" else tiles,
            metadata={"b": 1, "a": 2}, tile_compression=COMPRESSION_GZIP, bounds=BRISTOL,
        )  # fmt: skip

    assert (tmp_path / "one").read_bytes() == (tmp_path / "two").read_bytes()


def test_a_file_that_is_not_pmtiles_is_refused(tmp_path: Path):
    (tmp_path / "not.pmtiles").write_bytes(b"PK\x03\x04" + b"\0" * 200)

    with pytest.raises(PMTilesError, match="PMTiles"):
        Archive.open(tmp_path / "not.pmtiles")


def test_an_archive_cut_short_is_refused(tmp_path: Path):
    write_archive(
        tmp_path / "a.pmtiles", {(0, 0, 0): b"world" * 100}, metadata={},
        tile_compression=COMPRESSION_NONE, bounds=BRISTOL,
    )  # fmt: skip
    whole = (tmp_path / "a.pmtiles").read_bytes()
    (tmp_path / "a.pmtiles").write_bytes(whole[:-10])

    with pytest.raises(PMTilesError, match="ends early"):
        Archive.open(tmp_path / "a.pmtiles").tile(0, 0, 0)
