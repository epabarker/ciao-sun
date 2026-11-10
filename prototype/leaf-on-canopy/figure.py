"""PROTOTYPE, throwaway. One map figure for ticket #23.

    uv run --with matplotlib python <worktree>/prototype/leaf-on-canopy/figure.py <outdir> <png>
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from affine import Affine

sys.argv, OUT, PNG = sys.argv[:2] + ["20"], Path(sys.argv[1]), Path(sys.argv[2])
import analyse as A  # noqa: E402  (scores on import; reuses its rules)

M = np.load(OUT / "masks.npz")
T = Affine(*M["transform"].tolist())
dates = list(M["dates"])
months = np.array([int(d[5:7]) for d in dates])
prov = M["prov"]
season = np.where(prov < 0, np.nan, np.where(np.isin(prov, np.nonzero((months >= 5) & (months <= 9))[0]), 2,
                                             np.where(months[np.clip(prov, 0, None)] == 4, 1, 0)))
x0, y0 = T * (0, 0)
x1, y1 = T * (prov.shape[1], prov.shape[0])
ext = [x0, x1, y1, y0]
hx, hy = 358144.6, 174954.9
step = 4  # display decimation

fig, ax = plt.subplots(2, 2, figsize=(14, 14))
a = ax[0, 0]
cm = matplotlib.colors.ListedColormap(["#9db7d5", "#c9d98a", "#2f7d32"])
a.imshow(season[::step, ::step], extent=ext, cmap=cm, vmin=0, vmax=2, interpolation="nearest")
a.set_title("Which season the composite DSM was flown in, per cell\n"
            "blue = Jan 2019 (leaf-off) · light green = 19 Apr 2018 (bud-burst) · dark green = Sep 2021 (leaf-on)")
reach = A.WALK <= 15
a.scatter(A.X[reach][::5], A.Y[reach][::5], s=0.3, c="k", alpha=0.3)
a.plot(hx, hy, "r*", ms=14)

b = ax[0, 1]
veg, vfz = M["veg"], M["veg_fz"]
img = np.zeros(veg.shape, np.uint8)
img[vfz] = 1
img[veg] = 2
b.imshow(img[::step, ::step], extent=ext, cmap=matplotlib.colors.ListedColormap(["white", "#f0a640", "#2f7d32"]),
         interpolation="nearest")
b.set_title("Vegetation over 2 m, outside OSM buildings\n"
            "green = in the last-return DSM the tool uses · orange = only in the first return (bare crowns)")
b.plot(hx, hy, "r*", ms=14)

for k, (ds, win, title) in enumerate([("2027-06-21", "evening", "21 Jun evening: Last sun with summer canopy (proxy) vs as-is"),
                                      ("2026-12-21", "evening", "21 Dec evening: Last sun if Sep-2021 trees were bare vs as-is")]):
    c = ax[1, k]
    sc = A.score(ds, win)
    s = "leafy" if k == 0 else "bare_on"
    a_, b_ = sc["asis"], sc[s]
    sh = np.abs(b_["last"] - a_["last"])
    sh = np.where(np.isfinite(sh), sh, 0)
    gone = a_["vis"] & ~b_["vis"] if k == 0 else ~a_["vis"] & b_["vis"]
    sel = A.WALK <= 20
    c.imshow(season[::step, ::step], extent=ext, cmap=cm, vmin=0, vmax=2, alpha=0.25, interpolation="nearest")
    o = np.argsort(sh[sel])
    p = c.scatter(A.X[sel][o], A.Y[sel][o], c=np.clip(sh[sel][o], 0, 60), s=2, cmap="magma_r", vmin=0, vmax=60)
    c.scatter(A.X[sel & gone], A.Y[sel & gone], s=2, c="#1f6fd1")
    c.plot(hx, hy, "c*", ms=14)
    c.set_title(title + "\n(minutes, capped at 60; blue = sun lost/gained entirely; Candidates within 20 min)")
    fig.colorbar(p, ax=c, shrink=0.7)
for a in ax.ravel():
    a.set_xlim(hx - 2600, hx + 2600)
    a.set_ylim(hy - 2600, hy + 2600)
    a.set_xticks([])
    a.set_yticks([])
fig.suptitle("PROTOTYPE: leaf-on canopy near BS6 (ticket #23). EA LIDAR © EA 2022 OGL; OSM © contributors ODbL", y=0.995)
fig.tight_layout()
fig.savefig(PNG, dpi=110)
print("wrote", PNG)
