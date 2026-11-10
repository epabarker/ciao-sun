"""PROTOTYPE, throwaway. Does a leaf-off first return stand in for a leaf-on crown?

Where the composite is the 21 Sep 2021 leaf-on survey, compare its last-return crowns (truth)
with the NLP 17 Jan 2019 leaf-off first-return DSM of the same ground (the 'leafy' proxy).

    uv run python <worktree>/prototype/leaf-on-canopy/validate_proxy.py <outdir>
"""

import glob
import json
import sys
from pathlib import Path

import numpy as np
from affine import Affine

sys.path.insert(0, str(Path(__file__).parent))
from crowns import M, onto  # noqa: E402  (also reruns crowns.py; cheap)

OUT = Path(sys.argv[1])
dates = list(M["dates"])
on = M["prov"] == dates.index("2021-09-21")
dtm = np.full(M["veg"].shape, np.nan, "f4")
lz = dtm.copy()
fz19 = dtm.copy()
for p in glob.glob("data/dtm/**/*.tif", recursive=True):
    a = onto(p); dtm = np.where(np.isfinite(a), a, dtm)
for p in glob.glob("data/dsm/**/*.tif", recursive=True):
    a = onto(p); lz = np.where(np.isfinite(a), a, lz)
for p in glob.glob("data/canopy/nlpfz-2019-*/*.tif"):
    a = onto(p); fz19 = np.where(np.isfinite(a), a, fz19)
ok = on & ~M["bmask"] & np.isfinite(lz) & np.isfinite(fz19) & np.isfinite(dtm)
truth = ok & (lz - dtm > 2)
proxy = ok & (fz19 - dtm > 2)
i = (truth & proxy).sum()
ht, hp = (lz - dtm)[truth & proxy], (fz19 - dtm)[truth & proxy]
res = {
    "cells_km2": round(float(ok.sum() / 1e6), 2),
    "leaf_on_crown_share": round(float(truth.sum() / ok.sum()), 3),
    "proxy_crown_share": round(float(proxy.sum() / ok.sum()), 3),
    "iou": round(float(i / (truth | proxy).sum()), 3),
    "proxy_recall_of_leaf_on_crown": round(float(i / truth.sum()), 3),
    "proxy_precision": round(float(i / proxy.sum()), 3),
    "median_height_leaf_on": round(float(np.median(ht)), 2),
    "median_height_proxy": round(float(np.median(hp)), 2),
    "median_proxy_minus_truth_m": round(float(np.median(hp - ht)), 2),
}
(OUT / "proxy_validation.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
