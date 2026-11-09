import json, sys, time, warnings
from pathlib import Path
import numpy as np, pandas as pd, pvlib
from pyproj import Transformer
from sunspot.horizon import horizon_angle, ray_samples
from sunspot.raster import find_tiles, load_mosaic_cached, sample, assert_aligned
from sunspot.search import candidate_grid
from sunspot.solar import find_sunrise
warnings.filterwarnings("ignore", message="All-NaN")
OUTDIR = Path(sys.argv[1])
LAT, LON = 51.4720, -2.6040  # home from README / bench
RADIUS, SPACING, EYE, MAX_RAY, CHUNK = 1500.0, 10.0, 1.6, 3000.0, 4000
T0 = time.perf_counter()
fwd = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
inv = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
hx, hy = fwd.transform(LON, LAT)
pad = RADIUS + MAX_RAY
b = (hx - pad, hy - pad, hx + pad, hy + pad)
dsm = load_mosaic_cached(find_tiles(Path("data/dsm")), b, OUTDIR / "cache", "dsm")
dtm = load_mosaic_cached(find_tiles(Path("data/dtm")), b, OUTDIR / "cache", "dtm")
assert_aligned(dsm, dtm)
print("mosaic bounds", dsm.bounds, "requested", b, "dsm nan frac", float(np.isnan(dsm.data).mean()))
t_load = time.perf_counter() - T0
gx, gy, dist = candidate_grid(hx, hy, RADIUS, SPACING)
n_grid = len(gx)
g = sample(dtm, gx, gy); s = sample(dsm, gx, gy)
valid = np.isfinite(g)
n_nodtm = int((~valid).sum())
ndsm = s - g
covered = valid & ~(np.isfinite(ndsm) & (ndsm > 1.0))
n_dropped = int((valid & np.isfinite(ndsm) & (ndsm > 1.0)).sum())
n_dsm_nan = int((valid & ~np.isfinite(s)).sum())
gx, gy, dist, gz = gx[covered], gy[covered], dist[covered], g[covered] + EYE
N = len(gx)
print(f"grid {n_grid}, no DTM {n_nodtm}, dropped ndsm>1m {n_dropped}, dsm nan at point {n_dsm_nan}, kept {N}")
az = np.arange(40.0, 220.0 + 1e-9, 5.0)
ray_d = ray_samples(MAX_RAY)
prof = np.empty((N, len(az)), np.float32)
t1 = time.perf_counter()
for st in range(0, N, CHUNK):
    sl = slice(st, st + CHUNK)
    for j, a in enumerate(az):
        prof[sl, j] = horizon_angle(dsm, gx[sl], gy[sl], gz[sl], a, ray_d, curvature=True)
t_cast = time.perf_counter() - t1
print(f"cast {N}x{len(az)} rays in {t_cast:.1f}s; profile NaN frac {np.isnan(prof).mean():.4g}")
# off-grid reach check: furthest ray end inside mosaic?
xmin, ymin, xmax, ymax = dsm.bounds
np.savez_compressed(OUTDIR / "profiles.npz", x=gx, y=gy, z=gz, az=az, prof=prof)
pcts = [5, 10, 25, 50, 75, 90, 95]
res = {"n_grid": n_grid, "n_no_dtm": n_nodtm, "n_dropped_ndsm": n_dropped, "n_kept": N,
       "t_load_s": round(t_load, 1), "t_cast_s": round(t_cast, 1), "prof_nan_frac": float(np.isnan(prof).mean())}
sectors = {"east_60_120": (az >= 60) & (az <= 120), "wide_40_220": np.ones(len(az), bool)}
metrics_all = {}
for name, m in sectors.items():
    p = prof[:, m]
    mean_ang = np.nanmean(p, axis=1)
    svf = np.nanmean(np.cos(np.radians(np.clip(p, 0, None))) ** 2, axis=1)
    lt5 = np.nanmean(np.where(np.isnan(p), np.nan, p < 5), axis=1)
    lt10 = np.nanmean(np.where(np.isnan(p), np.nan, p < 10), axis=1)
    mets = {"mean_angle": mean_ang, "svf": svf, "frac_lt5": lt5, "frac_lt10": lt10}
    metrics_all[name] = mets
    res[name] = {k: dict(zip(map(str, pcts), np.round(np.nanpercentile(v, pcts), 3).tolist())) for k, v in mets.items()}
    res[name]["svf_hist"] = np.histogram(svf, bins=np.arange(0, 1.0001, 0.1))[0].tolist()
    res[name]["svf_iqr"] = float(np.nanpercentile(svf, 75) - np.nanpercentile(svf, 25))
    res[name]["svf_std"] = float(np.nanstd(svf))
# examples at p10/p50/p90 of wide SVF
svf = metrics_all["wide_40_220"]["svf"]; ma = metrics_all["wide_40_220"]["mean_angle"]
ex = {}
rng = np.random.default_rng(0)
for q in (10, 50, 90):
    tgt = np.nanpercentile(svf, q)
    idx = np.argsort(np.abs(svf - tgt))[:50]
    pick = rng.choice(idx, 3, replace=False)
    lon, lat = inv.transform(gx[pick], gy[pick])
    ex[f"p{q}"] = [dict(lat=round(float(la), 5), lon=round(float(lo), 5), svf=round(float(svf[i]), 3),
                        mean_angle=round(float(ma[i]), 1), east_svf=round(float(metrics_all["east_60_120"]["svf"][i]), 3),
                        dist_m=round(float(dist[i])))
                   for la, lo, i in zip(lat, lon, pick)]
res["examples"] = ex
# correlation east vs wide
res["corr_east_wide_svf"] = float(np.corrcoef(metrics_all["east_60_120"]["svf"], svf)[0, 1])
# solar windows
sol = {}
for d in ("2026-12-21", "2026-06-21"):
    sr = find_sunrise(LAT, LON, d)
    start = max(pd.Timestamp(f"{d} 07:00", tz="Europe/London"), sr)
    end = pd.Timestamp(f"{d} 10:00", tz="Europe/London")
    t = pd.date_range(start, end, freq="5min")
    sp = pvlib.solarposition.get_solarposition(t, LAT, LON)
    sol[d] = dict(sunrise=str(sr), start=str(start), end=str(end),
                  az_range=[round(float(sp.azimuth.min()), 1), round(float(sp.azimuth.max()), 1)],
                  el_range=[round(float(sp.apparent_elevation.min()), 1), round(float(sp.apparent_elevation.max()), 1)])
res["solar"] = sol
res["t_total_s"] = round(time.perf_counter() - T0, 1)
(OUTDIR / "results.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
