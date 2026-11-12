"""Cutting the part of a national OSM extract a build needs, once, before the workers start.

The box is (359000, 173000)-(360000, 174000). Everything is asserted on what
the clip holds, read back with pyosmium, or on tiles built from it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import osmium

from ciao_sun.candidates import build_tile, load_walk_network
from ciao_sun.osm_clip import clip_osm
from ciao_sun.tile_codec import PROFILE_SAMPLES, write_tile
from tests.conftest import make_flat_grid
from tests.osm_extract import write_osm_extract

BOX = (359000.0, 173000.0, 360000.0, 174000.0)

NODES = {
    # A street running from outside the box into it.
    1: (358500.0, 173500.0),
    2: (359500.0, 173500.0),
    3: (359800.0, 173500.0),
    # A street far away, wholly outside.
    10: (365000.0, 180000.0),
    11: (365100.0, 180000.0),
    # A park of four open ways, its east side in the box: way 203, its west side,
    # has no node in the box.
    20: (358600.0, 173200.0),
    21: (359100.0, 173200.0),
    22: (359100.0, 173400.0),
    23: (358600.0, 173400.0),
    # A long-distance route's far-away member.
    30: (370000.0, 190000.0),
    31: (370100.0, 190000.0),
}
WAYS = [
    (100, [1, 2, 3], {"highway": "residential", "name": "Long Street"}),
    (101, [10, 11], {"highway": "residential", "name": "Far Street"}),
    (201, [21, 22], {}),
    (202, [22, 23], {}),
    (203, [23, 20], {}),
    (204, [20, 21], {}),
    (300, [30, 31], {"highway": "footway"}),
]
PARK = (
    400,
    [(201, "outer"), (202, "outer"), (203, "outer"), (204, "outer")],
    {"type": "multipolygon", "leisure": "park", "name": "Meadow"},
)
ROUTE = (500, [(100, ""), (300, "")], {"type": "route", "route": "foot", "name": "Long Walk"})


def _contents(path: Path) -> dict[str, set[int]]:
    found: dict[str, set[int]] = {"n": set(), "w": set(), "r": set()}
    for obj in osmium.FileProcessor(str(path)):
        found[obj.type_str()].add(obj.id)
    return found


def _source(tmp_path: Path) -> Path:
    return write_osm_extract(tmp_path / "england.osm.pbf", NODES, WAYS, [PARK, ROUTE])


def test_a_way_with_a_node_in_the_box_is_kept_whole(tmp_path):
    clip = _contents(clip_osm(_source(tmp_path), BOX, tmp_path / "clip.osm.pbf"))
    assert 100 in clip["w"]
    assert {1, 2, 3} <= clip["n"]  # node 1 is outside the box


def test_what_is_wholly_outside_the_box_is_left_out(tmp_path):
    clip = _contents(clip_osm(_source(tmp_path), BOX, tmp_path / "clip.osm.pbf"))
    assert 101 not in clip["w"] and not {10, 11} & clip["n"]


def test_a_multipolygon_reaching_into_the_box_comes_out_whole_and_assembles(tmp_path):
    clip_path = clip_osm(_source(tmp_path), BOX, tmp_path / "clip.osm.pbf")
    clip = _contents(clip_path)
    assert 400 in clip["r"] and {201, 202, 203, 204} <= clip["w"]
    assert {20, 21, 22, 23} <= clip["n"]
    areas = [
        obj.tags["name"]
        for obj in osmium.FileProcessor(str(clip_path)).with_areas()
        if isinstance(obj, osmium.osm.Area) and obj.from_way() is False
    ]
    assert areas == ["Meadow"]


def test_other_relations_do_not_pull_in_their_far_away_members(tmp_path):
    clip = _contents(clip_osm(_source(tmp_path), BOX, tmp_path / "clip.osm.pbf"))
    assert 500 not in clip["r"]
    assert 300 not in clip["w"] and not {30, 31} & clip["n"]


def test_a_tile_built_from_the_clip_is_the_tile_built_from_the_whole_extract(tmp_path):
    source = _source(tmp_path)
    clip = clip_osm(source, BOX, tmp_path / "clip.osm.pbf")
    grid = make_flat_grid(10.0, 358900, 174100, width=1201, height=1201)  # open ground
    written = []
    for name, extract in (("whole", source), ("clip", clip)):
        outline = build_tile(load_walk_network(extract, within=BOX), "ST5973", grid, grid)
        assert outline is not None
        codes = np.full((outline.easting.size, PROFILE_SAMPLES), 20, dtype=np.uint8)
        written.append(write_tile(outline.with_profiles(codes), tmp_path / name).read_bytes())
    assert written[0] == written[1]
