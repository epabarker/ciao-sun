"""PROTOTYPE, throwaway. Two checks on the vegetation side of ticket #23.

1. Leaf-off vs leaf-on crowns: the same trees flown 23 Jan 2019 and 21 Sep 2021
   (per-survey EA DSM tiles D0212705 / D0222095, which overlap by ~0.8 km2).
   How much of a leaf-on crown does a leaf-off last-return DSM still show?
2. Mask agreement: OSM-building mask (DSM - DTM > 2 m outside buffered footprints)
   vs EA's NLP Vegetation Object Model, on the 2018-04-19 survey it was made from.

Needs data/canopy/* downloads and <outdir>/masks.npz.
    uv run python <worktree>/prototype/leaf-on-canopy/crowns.py <outdir>
"""

import glob
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.warp import Resampling, reproject

OUT = Path(sys.argv[1])
M = np.load(OUT / "masks.npz")
T = Affine(*M["transform"].tolist())
SHAPE = M["veg"].shape
CRS = "EPSG:27700"


def onto(path):
    a = np.full(SHAPE, np.nan, "f4")
    with rasterio.open(path) as s:
        reproject(rasterio.band(s, 1), a, src_transform=s.transform, src_crs=s.crs, dst_transform=T,
                  dst_crs=CRS, resampling=Resampling.nearest, src_nodata=s.nodata, dst_nodata=np.nan)
    a[a < -100] = np.nan
    return a


dtm = np.full(SHAPE, np.nan, "f4")
for p in glob.glob("data/dtm/**/*.tif", recursive=True):
    a = onto(p)
    dtm = np.where(np.isfinite(a), a, dtm)
res = {}

# 1. crowns
s19 = onto(glob.glob("data/canopy/lidar_tiles_dsm-2019-ST5575/DSM_D0212705_*.tif")[0])
s21 = onto(glob.glob("data/canopy/lidar_tiles_dsm-2021-ST5575/DSM_D0222095_*.tif")[0])
h19, h21 = s19 - dtm, s21 - dtm
ok = np.isfinite(h19) & np.isfinite(h21) & ~M["bmask"]
crown21 = ok & (h21 > 2)
crown19 = ok & (h19 > 2)
res["crowns"] = {
    "overlap_km2": round(float(ok.sum() / 1e6), 3),
    "leaf_on_crown_cells": int(crown21.sum()),
    "leaf_off_crown_cells": int(crown19.sum()),
    "share_of_leaf_on_crown_still_tall_leaf_off": round(float(np.mean(h19[crown21] > 2)), 3),
    "median_height_leaf_on": round(float(np.median(h21[crown21])), 2),
    "median_height_leaf_off_same_cells": round(float(np.median(h19[crown21])), 2),
    "median_ratio_off_over_on": round(float(np.median(np.clip(h19[crown21], 0, None) / h21[crown21])), 3),
    "share_dropping_over_half": round(float(np.mean(h19[crown21] < 0.5 * h21[crown21])), 3),
}

# 2. VOM agreement on the 2018-04-19 survey
vom = onto(glob.glob("data/canopy/national_lidar_programme_vom-2018-ST5575/VOM_ST5575_*.tif")[0])
dates = list(M["dates"])
sel = (M["prov"] == dates.index("2018-04-19")) & np.isfinite(vom)
v_ea = sel & (vom > 2)
v_osm = sel & M["veg"]
inter = (v_ea & v_osm).sum()
res["mask_vs_vom"] = {
    "cells_km2": round(float(sel.sum() / 1e6), 2),
    "vom_veg_share": round(float(v_ea.sum() / sel.sum()), 3),
    "osm_mask_veg_share": round(float(v_osm.sum() / sel.sum()), 3),
    "iou": round(float(inter / (v_ea | v_osm).sum()), 3),
    "osm_mask_precision_vs_vom": round(float(inter / v_osm.sum()), 3),
    "osm_mask_recall_vs_vom": round(float(inter / v_ea.sum()), 3),
}
v_fz = sel & M["veg_fz"]
i2 = (v_ea & v_fz).sum()
res["first_return_mask_vs_vom"] = {
    "fz_mask_veg_share": round(float(v_fz.sum() / sel.sum()), 3),
    "iou": round(float(i2 / (v_ea | v_fz).sum()), 3),
    "precision_vs_vom": round(float(i2 / v_fz.sum()), 3),
    "recall_vs_vom": round(float(i2 / v_ea.sum()), 3),
}
(OUT / "crowns.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
