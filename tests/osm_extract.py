"""Write a small synthetic OSM extract (`.osm.pbf`) for tests.

Positions are given in British National Grid metres, which is how the tests
reason about distances; they are stored, as in any OSM file, as WGS84.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import osmium
from osmium.osm.mutable import Node, Relation, Way
from pyproj import Transformer

_BNG_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
_WGS84_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)

Tags = Mapping[str, str]


def write_osm_extract(
    path: Path,
    nodes: Mapping[int, tuple[float, float]],
    ways: Sequence[tuple[int, Sequence[int], Tags]],
    relations: Sequence[tuple[int, Sequence[tuple[int, str]], Tags]] = (),
) -> Path:
    """`nodes` maps id -> (easting, northing); a relation lists (way id, role) members."""
    writer = osmium.SimpleWriter(str(path), overwrite=True)
    try:
        for node_id, (easting, northing) in sorted(nodes.items()):
            lon, lat = _BNG_TO_WGS84.transform(easting, northing)
            writer.add_node(Node(id=node_id, location=(lon, lat)))
        for way_id, refs, tags in ways:
            writer.add_way(Way(id=way_id, nodes=list(refs), tags=dict(tags)))
        for relation_id, members, tags in relations:
            writer.add_relation(
                Relation(
                    id=relation_id,
                    members=[("w", way_id, role) for way_id, role in members],
                    tags=dict(tags),
                )
            )
    finally:
        writer.close()
    return path


def bng_of(lat_e7: int, lon_e7: int) -> tuple[float, float]:
    """A stored tile position -> (easting, northing) in metres."""
    easting, northing = _WGS84_TO_BNG.transform(lon_e7 / 1e7, lat_e7 / 1e7)
    return float(easting), float(northing)
