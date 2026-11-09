"""RESEARCH, throwaway. Check the Terrain 50 mosaic against the local EA 1 m DTM.

Block-averages the six local 1 m DTM tiles to 50 m and compares with Terrain 50 at
the cell centres, plus shifted by half a cell to test the grid registration.
    uv run python -I validate_terr50.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from farlib import FWD, MAIN, T50  # noqa: E402

from sunspot.raster import find_tiles, load_mosaic  # noqa: E402

t50 = T50()
b = (350000.0, 170000.0, 365000.0, 180000.0)
dtm = load_mosaic(find_tiles(MAIN / "data/dtm"), bounds=b)
a = dtm.data
nr, nc = a.shape[0] // 50, a.shape[1] // 50
blk = a[: nr * 50, : nc * 50].reshape(nr, 50, nc, 50)
with np.errstate(all="ignore"):
    mean = np.nanmean(blk, axis=(1, 3))
    frac = np.isfinite(blk).mean(axis=(1, 3))
x0, y1 = dtm.transform.c, dtm.transform.f
cx = x0 + 25 + 50 * np.arange(nc)
cy = y1 - 25 - 50 * np.arange(nr)
X, Y = np.meshgrid(cx, cy)
ok = frac > 0.95
print("1 m DTM origin", x0, y1, "blocks", nr, nc)
for dx, dy, lab in [(0, 0, "as registered"), (25, -25, "shift +25E -25N"), (-25, 25, "shift -25E +25N")]:
    v = t50.sample(X + dx, Y + dy)
    d = (v - mean)[ok & np.isfinite(v)]
    print(f"{lab:18s} n={d.size} bias={d.mean():+.2f} m  rmse={np.sqrt((d**2).mean()):.2f} m  "
          f"p95|d|={np.percentile(np.abs(d), 95):.2f} m")

for name, (lat, lon) in {"home": (51.4720, -2.6040), "Lansdown (Bath) ~": (51.4180, -2.3880),
                         "Dundry Hill ~": (51.3990, -2.6390)}.items():
    x, y = FWD.transform(lon, lat)
    print(f"{name:18s} T50 {float(t50.sample(np.array([x]), np.array([y]))[0]):7.1f} m  at {x:.0f},{y:.0f}")
x, y = FWD.transform(-5.0037, 56.7969)  # Ben Nevis summit 1345 m
print("Ben Nevis T50", float(t50.sample(np.array([x]), np.array([y]))[0]))
