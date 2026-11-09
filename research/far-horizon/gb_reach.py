"""RESEARCH, throwaway. How far must a ray reach elsewhere in GB? Terrain-only (OS Terrain 50).

Observers on a 10 km lattice over GB land (ground + 1.6 m), true azimuths 35-165 deg at 1 deg,
rays 50 m - 250 km on Terrain 50 (no buildings or trees, so the near field is lower than any
real street and the far field wins more often than it would with a DSM: conservative).
For each (point, azimuth) the "required reach" is the smallest R in REACH such that
horizon(<= R) is within TOL of horizon(<= 250 km).

    uv run python -I gb_reach.py <outdir>
"""

import sys
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from farlib import INV, T50, nanmax, ray_angles  # noqa: E402

from sunspot.horizon import R_EFF  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
t50 = T50()
AZ = np.arange(35.0, 165.0 + 1e-9, 1.0)
D = np.concatenate([np.arange(50, 20000, 50.0), np.arange(20000, 50000, 100.0),
                    np.arange(50000, 250000, 250.0)])
REACH = np.array([3, 5, 10, 15, 20, 30, 50, 75, 100, 150, 200, 250]) * 1000.0
TOLS = (0.05, 0.1, 0.25)

xs, ys = np.meshgrid(np.arange(5000, 700000, 10000.0), np.arange(5000, 1250000, 10000.0))
xs, ys = xs.ravel(), ys.ravel()
g = t50.sample(xs, ys)
land = np.isfinite(g) & (g > 2.0)
xs, ys, g = xs[land], ys[land], g[land]
zs = g + 1.6
N = len(xs)


def one(i):
    px, py, pz = np.full(len(AZ), xs[i]), np.full(len(AZ), ys[i]), np.full(len(AZ), zs[i])
    # one observer, many azimuths: vectorise over azimuth by sampling each ray
    th = np.radians(AZ)  # grid ~ true here (convergence <= ~4 deg; irrelevant to reach statistics)
    X = px[:, None] + D[None, :] * np.sin(th)[:, None]
    Y = py[:, None] + D[None, :] * np.cos(th)[:, None]
    zt = t50.sample(X.ravel(), Y.ravel()).reshape(X.shape)
    ang = np.degrees(np.arctan2(zt - pz[:, None] - (D**2 / (2 * R_EFF))[None, :], D[None, :]))
    cum = np.stack([nanmax(ang[:, D <= r], axis=1) for r in REACH], axis=1)  # (n_az, n_reach)
    relief = float(np.nanmax(zt[:, D <= 20000]) - pz[0])
    return i, cum.astype(np.float32), relief


if __name__ == "__main__":
    cum = np.empty((N, len(AZ), len(REACH)), np.float32)
    relief = np.empty(N, np.float32)
    with get_context("fork").Pool(8) as pool:
        for i, c, r in pool.imap_unordered(one, range(N), chunksize=16):
            cum[i], relief[i] = c, r
    full = cum[:, :, -1]
    lon, lat = INV.transform(xs, ys)
    rows = []
    rclass = np.select([relief < 100, relief < 300], ["relief<100m", "relief100-300m"], "relief>=300m")
    region = np.where(ys > 560000, "north (N>560 km, ~Scotland/N England)", "south (N<=560 km)")
    for cond_name, cond in (("all pairs", np.ones_like(full, bool)), ("horizon<2deg", full < 2.0),
                            ("horizon 0-2deg", (full >= 0) & (full < 2.0))):
        for grp_name, grp in [("GB", np.ones(N, bool))] + \
                [(k, rclass == k) for k in ("relief<100m", "relief100-300m", "relief>=300m")] + \
                [(k, region == k) for k in np.unique(region)]:
            m = cond & grp[:, None]
            row = {"condition": cond_name, "group": grp_name, "n_points": int(grp.sum()),
                   "n_pairs": int(m.sum())}
            for tol in TOLS:
                ok = (full[:, :, None] - cum) <= tol  # (N, az, reach)
                need = REACH[np.argmax(ok, axis=2)][m] / 1000.0
                for p in (50, 90, 99, 99.9):
                    row[f"tol{tol}_p{p}_km"] = float(np.percentile(need, p)) if need.size else np.nan
                for r in (10, 30, 50, 100):
                    row[f"tol{tol}_frac_need_gt{r}km"] = float((need > r).mean()) if need.size else np.nan
            rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "gb_reach.csv", index=False, float_format="%.4f")
    pd.set_option("display.width", 250)
    print(df[["condition", "group", "n_points", "n_pairs", "tol0.1_p50_km", "tol0.1_p90_km", "tol0.1_p99_km",
              "tol0.1_p99.9_km", "tol0.1_frac_need_gt10km", "tol0.1_frac_need_gt30km",
              "tol0.1_frac_need_gt50km", "tol0.1_frac_need_gt100km"]].to_string(index=False))
    # per-point worst case (0.1 deg, horizon<2): where in GB is a long reach needed?
    ok = (full[:, :, None] - cum) <= 0.1
    need = np.where(full < 2.0, REACH[np.argmax(ok, axis=2)] / 1000.0, 0)
    pts = pd.DataFrame({"lat": np.round(lat, 4), "lon": np.round(lon, 4), "ground_m": np.round(g, 1),
                        "relief20km_m": np.round(relief, 0), "p90_need_km": np.percentile(need, 90, axis=1),
                        "max_need_km": need.max(axis=1)})
    pts.to_csv(OUT / "gb_points.csv", index=False)
    print(pts.sort_values("p90_need_km", ascending=False).head(15).to_string(index=False))
    print("points", N)
