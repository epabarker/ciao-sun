"""Cut the part of a national OSM extract a build needs, once, before the workers start.

Reading an `.osm.pbf` with node locations makes pyosmium store the location of
every node in the file, before any filter runs. For England that is over 7 GB
per pass, in every worker. `clip_osm` reads the big file once and writes a
small one the workers read instead.

What the clip keeps, as `osmium extract --strategy smart` does:

- every node in the box;
- every way with a node in the box, whole, with all its nodes;
- every multipolygon relation with a member in the box, whole, with all its
  member ways and their nodes, so areas at the edge still assemble.

Other relations (routes, boundaries) are left out: nothing in the build reads
them, and keeping one would pull in its members across the country.

A way or area that crosses or encloses the box without a node in it is left
out too, so cut wider than the area the build reads.
"""

from __future__ import annotations

from pathlib import Path

import osmium

from ciao_sun.crs import lonlat_box

Bounds = tuple[float, float, float, float]


def clip_osm(source: Path, within: Bounds, out: Path) -> Path:
    """Write the part of `source` that reaches into `within` (National Grid metres) to `out`.

    `out` must end in `.osm.pbf`. It is written whole or not at all.
    """
    west, south, east, north = (round(v * 1e7) for v in lonlat_box(within))
    tracker = osmium.IdTracker()
    # The one pass in Python, over every node in the file.
    for node in osmium.FileProcessor(str(source), osmium.osm.NODE):
        assert isinstance(node, osmium.osm.Node)
        location = node.location
        if west <= location.x <= east and south <= location.y <= north:
            tracker.add_node(node.id)
    # Ways with a node in the box; relation_depth -1 adds no relations.
    tracker.complete_forward_references(str(source), relation_depth=-1)
    multipolygons = osmium.FileProcessor(str(source), osmium.osm.RELATION).with_filter(
        osmium.filter.TagFilter(("type", "multipolygon"))
    )
    for relation in multipolygons:
        if tracker.contains_any_references(relation):
            tracker.add_relation(relation.id)
    # Every node of every kept way, and every member of every kept relation.
    # relation_depth must be 1: at 0 the relations' members are not added.
    tracker.complete_backward_references(str(source), relation_depth=1)

    partial = out.with_name(f".partial-{out.name}")
    partial.unlink(missing_ok=True)
    with osmium.SimpleWriter(str(partial)) as writer:
        for obj in osmium.FileProcessor(str(source)).with_filter(tracker.id_filter()):
            writer.add(obj)
    partial.replace(out)
    return out
