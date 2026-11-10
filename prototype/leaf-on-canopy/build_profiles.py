"""PROTOTYPE, throwaway. Horizon profiles near BS6 with and without tree canopy.

Ticket: "How much does leaf-on tree canopy change winter answers in Bristol?"
(epabarker/daylight-viewing#23). Never merged.

Builds, for every reachable Candidate (open ground, within 12 m of the OSM walk
network, <= 20 min walk of home), Horizon profiles over true azimuth 40-320 deg at
0.25 deg for three surfaces:

  asis      the EA 2022 composite DSM as shipped
  bare_on   vegetated cells set to DTM only where the composite came from a
            leaf-on survey (May-Sep flight date)
  bare_all  every vegetated cell set to DTM (upper bound for any tree effect)

Vegetation = DSM - DTM > 2 m outside OSM building footprints buffered 1.5 m.
Each near profile (EA 1 m, 3 km) is merged with a far field from OS Terrain 50
(3-50 km, canopy-independent), cast at grid azimuth = true - convergence.

Run from the main checkout root:
    uv run --with osmium --with geopandas python <worktree>/prototype/leaf-on-canopy/prep_osm.py <outdir>
    uv run --with osmnx --with scipy python <worktree>/prototype/leaf-on-canopy/build_profiles.py <outdir>
"""

from __future__ import annotations

import glob
import multiprocessing as mp
import sys
import time
import warnings
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from pyproj import CRS, Proj, Transformer
from rasterio.features import rasterize
from scipy.ndimage import binary_dilation

from sunspot.horizon import R_EFF, horizon_angle, ray_samples
from sunspot.raster import RasterGrid, assert_aligned, find_tiles, load_mosaic_cached, sample
from sunspot.search import candidate_grid

warnings.filterwarnings("ignore")
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
LAT, LON = 51.4720, -2.6040
RADIUS, SPACING, EYE, MAX_RAY = 1800.0, 10.0, 1.6, 3000.0
WALK_SPEED, MAX_WALK_MIN, SNAP_M = 83.0, 20.0, 12.0
VEG_MIN_H, BLDG_BUF_M = 2.0, 1.5
AZ = np.round(np.arange(40.0, 320.0 + 1e-9, 0.25), 2)  # true azimuth
AZ_FAR = np.arange(40.0, 321.0, 1.0)
FAR_D = np.arange(MAX_RAY, 50_000.0 + 1, 50.0)
T50_NPY = Path("data/farfield/terr50/gb_terr50_dm.npy")
T0 = time.perf_counter()


def log(*a):
    print(f"[{time.perf_counter() - T0:6.0f}s]", *a, flush=True)


fwd = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
hx, hy = fwd.transform(LON, LAT)
CONV = float(Proj(CRS.from_epsg(27700)).get_factors(LON, LAT).meridian_convergence)
log("home", round(hx), round(hy), "convergence", round(CONV, 4))

pad = RADIUS + MAX_RAY
b = (hx - pad, hy - pad, hx + pad, hy + pad)
dsm = load_mosaic_cached(find_tiles(Path("data/dsm")), b, Path("data/cache"), "dsm")
dtm = load_mosaic_cached(find_tiles(Path("data/dtm")), b, Path("data/cache"), "dtm")
assert_aligned(dsm, dtm)
ndsm = dsm.data - dtm.data

# --- Survey provenance: the composite keeps the newest survey per cell (verified on ST5575).
gs = [gpd.read_file(p, layer="lidar_used_in_merging_process")
      for p in sorted(glob.glob("data/dsm/**/*_Metadata.gpkg", recursive=True))]
surv = gpd.GeoDataFrame(pd.concat(gs), crs=gs[0].crs)
surv["flown"] = pd.to_datetime(surv["SD_FLOWN"].astype(str).str[:10])
dates = sorted(surv["flown"].unique())
prov = np.full(dsm.shape, -1, np.int16)
for i, d in enumerate(dates):  # ascending, so the newest overwrites
    geom = surv[surv["flown"] == d].union_all()
    m = rasterize([(geom, 1)], out_shape=dsm.shape, transform=dsm.transform, fill=0).astype(bool)
    prov[m] = i
months = np.array([pd.Timestamp(d).month for d in dates])
leaf_on_idx = np.nonzero((months >= 5) & (months <= 9))[0]
leaf_on = np.isin(prov, leaf_on_idx)
log("surveys", [str(pd.Timestamp(d).date()) for d in dates], "leaf-on idx", leaf_on_idx.tolist())

# --- Buildings from OSM, buffered, rasterised.
ox.settings.cache_folder = str(OUT / "osmnx")
inv = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
bl = gpd.read_file(OUT / "buildings.gpkg")  # from prep_osm.py (Geofabrik extracts)
bmask = rasterize([(g, 1) for g in bl.geometry.buffer(BLDG_BUF_M)], out_shape=dsm.shape,
                  transform=dsm.transform, fill=0).astype(bool)
log("buildings", len(bl))
veg = np.isfinite(ndsm) & (ndsm > VEG_MIN_H) & ~bmask
log(f"vegetated share of tall cells {veg.sum() / np.sum(ndsm > VEG_MIN_H):.1%}; leaf-on cells {leaf_on.mean():.1%}")

surfaces = {"asis": dsm.data}
for name, sel in [("bare_on", veg & leaf_on), ("bare_all", veg)]:
    a = dsm.data.copy()
    a[sel] = dtm.data[sel]
    surfaces[name] = a

# Summer proxy. A leaf-off last return passes through bare crowns, but the first return
# still hits the branches, so FZ - DTM traces the crown envelope. In leaf-off-surveyed cells,
# raise vegetation to the first-return height (leaf-on-surveyed cells are already in leaf).
fz = load_mosaic_cached(find_tiles(Path("data/canopy/fz")), b, Path("data/cache"), "fz")
assert_aligned(fz, dtm)
veg_fz = np.isfinite(fz.data) & (fz.data - dtm.data > VEG_MIN_H) & ~bmask
leafy = dsm.data.copy()
sel = veg_fz & ~leaf_on
leafy[sel] = np.fmax(dsm.data[sel], fz.data[sel])
surfaces["leafy"] = leafy
log(f"first-return vegetation {veg_fz.mean():.1%} of cells vs last-return {veg.mean():.1%}")

np.savez_compressed(OUT / "masks.npz", veg=veg, veg_fz=veg_fz, bmask=bmask, prov=prov, leaf_on=leaf_on,
                    transform=np.array(tuple(dsm.transform)[:6]),
                    dates=np.array([str(pd.Timestamp(d).date()) for d in dates]))

# --- Candidates: open ground on the as-is surface, near the walk network, reachable.
gx, gy, _ = candidate_grid(hx, hy, RADIUS, SPACING)
g, s = sample(dtm, gx, gy), sample(dsm, gx, gy)
keep = np.isfinite(g) & np.isfinite(s) & ((s - g) <= 1.0)
s_bare = sample(RasterGrid(surfaces["bare_all"], dsm.transform, dsm.crs), gx, gy)
extra = np.isfinite(g) & ~keep & ((s_bare - g) <= 1.0)  # under canopy, open if trees vanished
G = nx.compose_all([ox.graph_from_xml(p, bidirectional=True, retain_all=True)
                    for p in sorted(OUT.glob("walk_*.osm"))])
Gp = ox.project_graph(G, to_crs="EPSG:27700")
Gp = Gp.subgraph(max(nx.connected_components(Gp.to_undirected()), key=len)).copy()
home = ox.distance.nearest_nodes(Gp, hx, hy)
dn = nx.single_source_dijkstra_path_length(Gp.to_undirected(), home, weight="length")


def walk_m(px, py):
    eids, edist = ox.distance.nearest_edges(Gp, px, py, return_dist=True)
    out = np.full(len(px), np.inf)
    nd = Gp.nodes
    for i in np.nonzero(np.asarray(edist) <= SNAP_M)[0]:
        u, v, _ = eids[i]
        out[i] = min((dn[n] + float(np.hypot(px[i] - nd[n]["x"], py[i] - nd[n]["y"]))
                      for n in (u, v) if n in dn), default=np.inf)
    return out


w_all = walk_m(gx[keep], gy[keep])
reach = w_all <= MAX_WALK_MIN * WALK_SPEED
cx, cy, cw = gx[keep][reach], gy[keep][reach], w_all[reach]
cz = g[keep][reach] + EYE
w_extra = walk_m(gx[extra], gy[extra])
n_extra = int(np.sum(w_extra <= MAX_WALK_MIN * WALK_SPEED))
N = len(cx)
cprov = sample(RasterGrid(prov.astype("float32"), dsm.transform, dsm.crs), cx, cy).astype(int)
log("reachable candidates", N, "| extra under-canopy candidates if trees vanished", n_extra)

# --- Profiles. Parallel over azimuths (fork shares the big arrays).
RAY_D = ray_samples(MAX_RAY)
_T50 = None


def near_job(args):
    name, az_true = args
    grid = RasterGrid(surfaces[name], dsm.transform, dsm.crs)
    return horizon_angle(grid, cx, cy, cz, az_true - CONV, RAY_D, curvature=True)


def far_job(az_true):
    global _T50
    if _T50 is None:
        _T50 = np.load(T50_NPY, mmap_mode="r")
    a = _T50
    th = np.radians(az_true - CONV)
    out = np.full(N, -90.0, np.float32)
    for st in range(0, N, 2000):
        sl = slice(st, st + 2000)
        xs = cx[sl, None] + FAR_D[None, :] * np.sin(th)
        ys = cy[sl, None] + FAR_D[None, :] * np.cos(th)
        cf, rf = xs / 50.0 - 0.5, (1_300_000.0 - ys) / 50.0 - 0.5
        c0, r0 = np.floor(cf).astype(np.int64), np.floor(rf).astype(np.int64)
        fx, fy = cf - c0, rf - r0
        z = (a[r0, c0] * (1 - fx) * (1 - fy) + a[r0, c0 + 1] * fx * (1 - fy)
             + a[r0 + 1, c0] * (1 - fx) * fy + a[r0 + 1, c0 + 1] * fx * fy) / 10.0
        rise = z - cz[sl, None] - (FAR_D**2 / (2.0 * R_EFF))[None, :]
        out[sl] = np.degrees(np.arctan2(rise, FAR_D[None, :])).max(axis=1)
    return out


ctx = mp.get_context("fork")
with ctx.Pool(10) as pool:
    far = np.stack(pool.map(far_job, AZ_FAR), axis=1)
    log("far field", far.shape)
    far_q = np.stack([np.interp(AZ, AZ_FAR, far[i]) for i in range(N)]).astype(np.float32)
    prof = {}
    for name in surfaces:
        near = np.stack(pool.map(near_job, [(name, a) for a in AZ], chunksize=8), axis=1)
        prof[name] = np.fmax(np.nan_to_num(near, nan=90.0), far_q).astype(np.float32)
        log("profiles", name, prof[name].shape)

np.savez_compressed(OUT / "profiles.npz", az=AZ, x=cx, y=cy, walk_m=cw, prov=cprov, far=far_q,
                    n_extra=n_extra, conv=CONV, **prof)
log("wrote", OUT / "profiles.npz")
