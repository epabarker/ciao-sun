"""The basemap: cut from a Protomaps archive by byte range, then exploded to z/x/y."""

from __future__ import annotations

from pathlib import Path

import pytest

from ciao_sun.basemap import MAX_ZOOM, MIN_ZOOM, BasemapError, explode, extract, tiles_covering
from ciao_sun.coverage import Coverage
from ciao_sun.pmtiles import Archive
from tests import basemap_world as protomaps

# About 2.5 km by 1.5 km of central Bristol.
BOUNDS = (-2.62, 51.445, -2.585, 51.458)
ZOOMS = range(MIN_ZOOM, MAX_ZOOM + 1)


def _coverage(bounds: protomaps.Bounds = BOUNDS) -> Coverage:
    west, south, east, north = bounds
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return Coverage.from_geojson({"type": "Polygon", "coordinates": [ring]})


class _Remote:
    """A remote archive that records the byte ranges asked of it."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.reads: list[tuple[int, int]] = []

    def read(self, offset: int, length: int) -> bytes:
        self.reads.append((offset, length))
        return self.body[offset : offset + length]


def _tree(root: Path) -> dict[tuple[int, int, int], bytes]:
    return {
        (int(p.parts[-3]), int(p.parts[-2]), int(p.stem)): p.read_bytes()
        for p in root.rglob("*.mvt")
    }


def test_the_app_zoom_range_runs_from_the_whole_city_to_the_archives_deepest_zoom():
    assert (MIN_ZOOM, MAX_ZOOM) == (10, 15)


def test_tiles_covering_a_coverage_are_those_its_bounding_box_touches():
    # Bristol city centre is in tile 15/16147/10904 and its parents.
    centre = _coverage((-2.5975, 51.4530, -2.5965, 51.4535))

    assert tiles_covering(centre) == [
        (10, 504, 340), (11, 1009, 681), (12, 2018, 1363), (13, 4036, 2726), (14, 8073, 5452),
        (15, 16147, 10904),
    ]  # fmt: skip
    assert set(tiles_covering(_coverage())) == protomaps.tiles_over(BOUNDS, ZOOMS)
    assert len(tiles_covering(_coverage())) > 12


def test_an_extract_then_an_explode_give_the_tile_tree_for_the_bounding_box(tmp_path: Path):
    remote = _Remote(protomaps.archive_bytes(BOUNDS))

    extract(remote.read, _coverage(), tmp_path / "bristol.pmtiles")
    basemap = explode(tmp_path / "bristol.pmtiles", _coverage(), tmp_path / "basemap")

    tree = _tree(tmp_path / "basemap")
    assert set(tree) == protomaps.tiles_over(BOUNDS, ZOOMS)
    for zxy, content in tree.items():
        assert content == protomaps.tile_text(*zxy)  # plain MVT bytes, not gzip
    assert basemap.tile_count == len(tree)
    assert basemap.bytes == sum(len(content) for content in tree.values())
    assert (basemap.min_zoom, basemap.max_zoom) == (10, 15)
    assert basemap.bounds == BOUNDS
    assert basemap.tileset_version == "4.15.1"
    assert basemap.osm_timestamp == "2026-08-11T04:00:00Z"


def test_an_extract_reads_a_small_part_of_the_archive_in_few_requests(tmp_path: Path):
    remote = _Remote(protomaps.archive_bytes(BOUNDS))

    extract(remote.read, _coverage(), tmp_path / "bristol.pmtiles")

    wanted = len(protomaps.tiles_over(BOUNDS, ZOOMS))
    assert len(remote.reads) < wanted / 2  # neighbouring tiles come in one read
    # After the header and root directory, less than the archive is read.
    assert sum(length for _, length in remote.reads[1:]) < len(remote.body) / 2
    held = Archive.open(tmp_path / "bristol.pmtiles")
    assert held.tile(15, 16147, 10904) is not None
    assert held.tile(9, 252, 170) is None  # a zoom the app does not use
    assert held.metadata()["version"] == "4.15.1"


def test_the_same_archive_and_coverage_give_the_same_extract_byte_for_byte(tmp_path: Path):
    body = protomaps.archive_bytes(BOUNDS)

    extract(_Remote(body).read, _coverage(), tmp_path / "one.pmtiles")
    extract(_Remote(body).read, _coverage(), tmp_path / "two.pmtiles")

    assert (tmp_path / "one.pmtiles").read_bytes() == (tmp_path / "two.pmtiles").read_bytes()


def test_a_build_without_one_of_the_tiles_is_refused(tmp_path: Path):
    remote = _Remote(protomaps.archive_bytes(BOUNDS, without=(15, 16147, 10904)))

    with pytest.raises(BasemapError, match="15/16147/10904"):
        extract(remote.read, _coverage(), tmp_path / "bristol.pmtiles")

    assert not (tmp_path / "bristol.pmtiles").exists()


def test_an_extract_cut_for_a_smaller_coverage_cannot_be_exploded_for_a_wider_one(tmp_path: Path):
    remote = _Remote(protomaps.archive_bytes((-2.75, 51.40, -2.50, 51.50)))
    extract(remote.read, _coverage(), tmp_path / "bristol.pmtiles")

    with pytest.raises(BasemapError, match="fetch"):
        explode(
            tmp_path / "bristol.pmtiles", _coverage((-2.75, 51.40, -2.50, 51.50)), tmp_path / "out"
        )


def test_a_smaller_coverage_inside_the_extract_gets_only_its_own_tiles(tmp_path: Path):
    remote = _Remote(protomaps.archive_bytes(BOUNDS))
    extract(remote.read, _coverage(), tmp_path / "bristol.pmtiles")
    centre = (-2.5975, 51.4530, -2.5965, 51.4535)

    explode(tmp_path / "bristol.pmtiles", _coverage(centre), tmp_path / "basemap")

    assert set(_tree(tmp_path / "basemap")) == protomaps.tiles_over(centre, ZOOMS)
