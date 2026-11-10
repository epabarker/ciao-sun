"""PROTOTYPE, throwaway. Cuts OSM buildings and the walk network out of Geofabrik extracts.

Overpass refused osmnx's pinned address on 2026-11-10, so this reads dated Geofabrik
.pbf files instead (the source the data-refresh ticket #19 chose anyway).

    uv run --with osmium --with geopandas python <worktree>/prototype/leaf-on-canopy/prep_osm.py <outdir>
Writes <outdir>/buildings.gpkg and <outdir>/walk_<region>.osm.
"""

import sys
from pathlib import Path

import geopandas as gpd
import osmium
from pyproj import Transformer
from shapely import wkb

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
LAT, LON = 51.4720, -2.6040
hx, hy = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True).transform(LON, LAT)
inv = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
BOX = [inv.transform(hx + dx, hy + dy) for dx, dy in [(-5000, -5000), (5000, 5000)]]
WBOX = [inv.transform(hx + dx, hy + dy) for dx, dy in [(-2300, -2300), (2300, 2300)]]
(LO0, LA0), (LO1, LA1) = BOX
(WLO0, WLA0), (WLO1, WLA1) = WBOX
REGIONS = ["bristol", "gloucestershire", "somerset"]
# osmnx's "walk" filter, applied by hand
BAD_HW = {"abandoned", "bus_guideway", "construction", "cycleway", "motor", "no", "planned",
          "platform", "proposed", "raceway", "razed", "motorway", "motorway_link"}

wkbf = osmium.geom.WKBFactory()
rows = []
for r in REGIONS:
    src = f"data/canopy/{r}-latest.osm.pbf"
    for obj in osmium.FileProcessor(src).with_areas().with_filter(osmium.filter.KeyFilter("building")):
        if not obj.is_area():
            continue
        try:
            g = wkb.loads(wkbf.create_multipolygon(obj), hex=True)
        except Exception:
            continue
        c = g.representative_point()
        if LO0 <= c.x <= LO1 and LA0 <= c.y <= LA1:
            rows.append({"region": r, "osm_id": obj.orig_id(), "geometry": g})
    # walk ways in the inner box, with their nodes
    with osmium.BackReferenceWriter(str(OUT / f"walk_{r}.osm"), ref_src=src, overwrite=True) as w:
        for obj in osmium.FileProcessor(src, osmium.osm.NODE | osmium.osm.WAY).with_locations():
            if not obj.is_way():
                continue
            t = obj.tags
            hw = t.get("highway")
            if hw is None or hw in BAD_HW or t.get("area") == "yes" or t.get("foot") == "no" \
                    or t.get("service") == "private" or t.get("access") == "private":
                continue
            try:
                inside = any(WLO0 <= n.lon <= WLO1 and WLA0 <= n.lat <= WLA1 for n in obj.nodes)
            except osmium.InvalidLocationError:
                continue
            if inside:
                w.add_way(obj)
    print(r, "done", len(rows), flush=True)

gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326").drop_duplicates("osm_id").to_crs("EPSG:27700")
gdf.to_file(OUT / "buildings.gpkg")
print("buildings", len(gdf))
