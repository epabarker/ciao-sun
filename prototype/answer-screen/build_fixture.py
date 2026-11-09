"""PROTOTYPE, throwaway. Builds the real-Bristol fixture for the answer-screen UI prototype.

Ticket: "What does the phone answer screen look like?" (epabarker/daylight-viewing#10).

Per reachable Candidate (on the OSM walk network, open ground, within ~22 min walk
of home) it ships a Horizon profile over 40-200 deg at 1 deg, quantised to 0.5 deg,
plus walk metres and a place name. Per date it ships the sun track at 2-min steps.
Everything else (Morning window, Sun minutes, openness over that day's sun path,
ranking, leave-by) is computed in the browser so Wake time / cloud / cut-off can be
changed live.

Run from the repo root of the main checkout (needs data/dsm, data/dtm):
    uv run --with osmnx python <worktree>/prototype/answer-screen/build_fixture.py <outdir>
"""

import base64
import json
import sys
import time
import warnings
from pathlib import Path

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import pvlib
from pyproj import Transformer
from shapely.geometry import Point

from sunspot.horizon import horizon_angle, ray_samples
from sunspot.raster import assert_aligned, find_tiles, load_mosaic_cached, sample
from sunspot.search import candidate_grid
from sunspot.solar import find_sunrise

warnings.filterwarnings("ignore")
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
LAT, LON = 51.4720, -2.6040
RADIUS, SPACING, EYE, MAX_RAY, CHUNK = 1800.0, 10.0, 1.6, 3000.0, 4000
WALK_SPEED = 83.0  # m/min, 5 km/h
MAX_WALK_MIN = 22.0
SNAP_M = 12.0
AZ = np.arange(40.0, 200.0 + 1e-9, 1.0)
T0 = time.perf_counter()

fwd = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
inv = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
hx, hy = fwd.transform(LON, LAT)
pad = RADIUS + MAX_RAY
b = (hx - pad, hy - pad, hx + pad, hy + pad)
dsm = load_mosaic_cached(find_tiles(Path("data/dsm")), b, OUT / "cache", "dsm")
dtm = load_mosaic_cached(find_tiles(Path("data/dtm")), b, OUT / "cache", "dtm")
assert_aligned(dsm, dtm)

# Candidates: open ground (DSM - DTM <= 1 m), as in the sky-openness research.
gx, gy, _ = candidate_grid(hx, hy, RADIUS, SPACING)
g, s = sample(dtm, gx, gy), sample(dsm, gx, gy)
keep = np.isfinite(g) & np.isfinite(s) & ((s - g) <= 1.0)
gx, gy, gz = gx[keep], gy[keep], g[keep] + EYE
print("open-ground candidates", len(gx))

# Reachability on the OSM walk network.
ox.settings.cache_folder = str(OUT / "osmnx")
G = ox.graph_from_point((LAT, LON), dist=RADIUS + 300, network_type="walk")
Gp = ox.project_graph(G, to_crs="EPSG:27700")
home = ox.distance.nearest_nodes(Gp, hx, hy)
dn = nx.single_source_dijkstra_path_length(Gp.to_undirected(), home, weight="length")
edges = ox.distance.nearest_edges(Gp, gx, gy, return_dist=True)
(eids, edist) = edges
edist = np.asarray(edist)
near = edist <= SNAP_M
walk = np.full(len(gx), np.inf)
ename = np.empty(len(gx), dtype=object)
ndata = Gp.nodes
for i in np.nonzero(near)[0]:
    u, v, k = eids[i]
    best = np.inf
    for n in (u, v):
        if n in dn:
            best = min(best, dn[n] + float(np.hypot(gx[i] - ndata[n]["x"], gy[i] - ndata[n]["y"])))
    walk[i] = best
    nm = Gp.edges[u, v, k].get("name")
    hw = Gp.edges[u, v, k].get("highway")
    if isinstance(nm, list):
        nm = nm[0]
    if isinstance(hw, list):
        hw = hw[0]
    ename[i] = nm or (f"unnamed {hw}" if hw else "path")
reach = np.isfinite(walk) & (walk <= MAX_WALK_MIN * WALK_SPEED)
gx, gy, gz, walk, ename = gx[reach], gy[reach], gz[reach], walk[reach], ename[reach]
N = len(gx)
print("reachable candidates", N, f"{time.perf_counter() - T0:.0f}s")

# Names: containing named green space, else the path/street.
feats = ox.features_from_point(
    (LAT, LON),
    tags={"leisure": ["park", "common", "recreation_ground", "nature_reserve", "playing_fields"],
          "landuse": ["recreation_ground", "grass", "meadow", "cemetery"]},
    dist=RADIUS + 300,
).to_crs("EPSG:27700")
feats = feats[feats.geometry.type.isin(["Polygon", "MultiPolygon"]) & feats["name"].notna()]
feats = feats.assign(area=feats.geometry.area).sort_values("area")
pts = [Point(x, y) for x, y in zip(gx, gy)]
park = np.empty(N, dtype=object)
import geopandas as gpd

pg = gpd.GeoDataFrame(geometry=pts, crs="EPSG:27700")
joined = gpd.sjoin(pg, feats[["name", "area", "geometry"]], predicate="within", how="left")
joined = joined.sort_values("area").groupby(level=0).first()
park[:] = joined["name"].reindex(range(N)).values
print("in named green space", int(pd.notna(park).sum()))

# Horizon profiles 40-200 deg.
ray_d = ray_samples(MAX_RAY)
prof = np.empty((N, len(AZ)), np.float32)
for st in range(0, N, CHUNK):
    sl = slice(st, st + CHUNK)
    for j, a in enumerate(AZ):
        prof[sl, j] = horizon_angle(dsm, gx[sl], gy[sl], gz[sl], a, ray_d, curvature=True)
print("profiles", prof.shape, f"{time.perf_counter() - T0:.0f}s", "nan", float(np.isnan(prof).mean()))
# quantise: byte = round((angle + 10) * 2), clipped; NaN -> 255 (treated as blocked)
q = np.where(np.isnan(prof), 255, np.clip(np.round((prof + 10.0) * 2.0), 0, 254)).astype(np.uint8)

lon, lat = inv.transform(gx, gy)
cands = {
    "lat": np.round(lat, 6).tolist(),
    "lon": np.round(lon, 6).tolist(),
    "walk_m": np.round(walk).astype(int).tolist(),
    "street": [str(x) for x in ename],
    "park": [None if pd.isna(x) else str(x) for x in park],
    "prof_b64": base64.b64encode(q.tobytes()).decode(),
}

# Sun tracks, 2-min steps 04:00-13:00 local, for every day of a year from tomorrow.
dates = pd.date_range("2026-11-10", periods=365, freq="D")
tracks = {}
for d in dates:
    ds = d.strftime("%Y-%m-%d")
    t = pd.date_range(f"{ds} 04:00", f"{ds} 13:00", freq="2min", tz="Europe/London")
    sp = pvlib.solarposition.get_solarposition(t, LAT, LON)
    sr = find_sunrise(LAT, LON, ds)
    tracks[ds] = {
        "t0": t[0].isoformat(),
        "sunrise": sr.strftime("%H:%M"),
        "az": np.round(sp.azimuth.values, 2).tolist(),
        "el": np.round(sp.apparent_elevation.values, 2).tolist(),
    }

fixture = {
    "_note": "PROTOTYPE fixture, real Bristol LIDAR + OSM walk network. Throwaway.",
    "home": {"lat": LAT, "lon": LON, "label": "Home (BS6)"},
    "params": {"az0": float(AZ[0]), "az_step": 1.0, "n_az": len(AZ), "walk_speed_m_per_min": WALK_SPEED,
               "step_min": 2, "spacing_m": SPACING, "eye_m": EYE, "max_ray_m": MAX_RAY},
    "attribution": {
        "lidar": "© Environment Agency copyright and/or database right 2022. Open Government Licence. Surveyed 2018–2022.",
        "osm": "Paths © OpenStreetMap contributors (ODbL)",
        "cloud": "Forecast: Met Office UKV via Open-Meteo (CC BY-SA 4.0)",
    },
    "candidates": cands,
    "tracks": tracks,
}
(OUT / "fixture.js").write_text("window.FIXTURE = " + json.dumps(fixture, separators=(",", ":")) + ";\n")
print("wrote", OUT / "fixture.js", f"{(OUT / 'fixture.js').stat().st_size / 1e6:.1f} MB", f"{time.perf_counter() - T0:.0f}s")
