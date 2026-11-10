"""PROTOTYPE -- throwaway. Re-scale of the cost benchmark for the wayfinder ticket
"On-demand run vs precomputed Horizon profiles: what do they cost?"
(epabarker/daylight-viewing#6) after three scope changes:

  1. band is now the Morning window's sun path, ~60-160 deg for Bristol (07:00 wake);
  2. profiles need a far field: EA 1 m DSM to 3 km, then OS Terrain 50 to 50 km
     (Bristol) / 100 km (GB);
  3. profiles are stored at 0.1 deg precision.

Measures, same Bristol circle as horizon_cost_bench.py (home 51.4720,-2.6040,
radius 1500 m, spacing 10 m):
  E. far-field ray cost (3-50 km and 3-100 km on Terrain 50) per Candidate x azimuth,
     at two sample densities, and the error of the cheaper density;
  F. whether the far field can be computed on a coarse grid (100/250/500 m) and
     combined as max(near, far), with and without an observer-height correction;
  G. fidelity of the stored combined profile (1 deg az step; 0.1 deg linear vs a
     piecewise uint8 code) against exact per-step scoring;
  H. storage of the combined profile, band 60-160 at 1 deg.

Azimuths are used as grid azimuths throughout (the known true/grid bug is not
fixed here; it changes no cost and fidelity compares like with like).

Run:  uv run python prototype/horizon_cost_farfield.py <cache_dir>
"""

from __future__ import annotations

import json
import lzma
import sys
import time
import warnings
from pathlib import Path

import numpy as np
from pyproj import Transformer

from sunspot.horizon import R_EFF, horizon_angle, ray_samples
from sunspot.raster import find_tiles, load_mosaic_cached, sample
from sunspot.search import candidate_grid, longest_clear_run
from sunspot.solar import sunrise_hour_track

warnings.filterwarnings("ignore", message="All-NaN (slice|axis) encountered")

LAT, LON = 51.4720, -2.6040
RADIUS, SPACING, EYE, NEAR = 1500.0, 10.0, 1.6, 3000.0
AZ = np.arange(60.0, 160.0 + 1e-9, 1.0)  # 101 azimuths
CHUNK = 2000
CACHE = Path(sys.argv[1] if len(sys.argv) > 1 else "data/cache")
T50_NPY = Path("data/farfield/terr50/gb_terr50_dm.npy")
T50_CELL, T50_Y1 = 50.0, 1_300_000.0
OUT: dict[str, object] = {}
rng = np.random.default_rng(0)


def log(k: str, v: object) -> None:
    OUT[k] = v
    print(f"{k}: {v}", flush=True)


# ---------------------------------------------------------------- Terrain 50 crop
class T50Crop:
    """OS Terrain 50 (int16 dm) cropped into RAM around home; bilinear, NaN off-grid."""

    def __init__(self, cx: float, cy: float, half: float):
        full = np.load(T50_NPY, mmap_mode="r")
        c0 = int((cx - half) // T50_CELL)
        c1 = int((cx + half) // T50_CELL) + 2
        r0 = int((T50_Y1 - (cy + half)) // T50_CELL)
        r1 = int((T50_Y1 - (cy - half)) // T50_CELL) + 2
        self.a = np.ascontiguousarray(full[r0:r1, c0:c1]).astype(np.float32) / 10.0
        self.c0, self.r0 = c0, r0

    @property
    def nbytes_int16(self) -> int:
        return self.a.size * 2

    def sample(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        cf = x / T50_CELL - 0.5 - self.c0
        rf = (T50_Y1 - y) / T50_CELL - 0.5 - self.r0
        c = np.floor(cf).astype(np.int64)
        r = np.floor(rf).astype(np.int64)
        fx = (cf - c).astype(np.float32)
        fy = (rf - r).astype(np.float32)
        nr, nc = self.a.shape
        ok = (r >= 0) & (r < nr - 1) & (c >= 0) & (c < nc - 1)
        r = np.where(ok, r, 0)
        c = np.where(ok, c, 0)
        a = self.a
        v = (a[r, c] * (1 - fx) * (1 - fy) + a[r, c + 1] * fx * (1 - fy)
             + a[r + 1, c] * (1 - fx) * fy + a[r + 1, c + 1] * fx * fy)
        v[~ok] = np.nan
        return v


def far_dists(reach: float, dense: bool) -> np.ndarray:
    if dense:  # what the far-horizon research used
        parts = [np.arange(3000, 10000, 25.0), np.arange(10000, 30000, 50.0),
                 np.arange(30000, reach, 200.0)]
    else:  # one sample per Terrain 50 cell to 10 km, then 100 m / 250 m
        parts = [np.arange(3000, 10000, 50.0), np.arange(10000, 30000, 100.0),
                 np.arange(30000, reach, 250.0)]
    d = np.concatenate(parts)
    return d[d < reach]


def far_angle(t50: T50Crop, px, py, pz, az, d, return_dist=False):
    """Max obstruction angle (deg) beyond 3 km; optionally the distance of that max."""
    th = np.radians(az)
    xs = px[:, None] + d[None, :] * np.sin(th)
    ys = py[:, None] + d[None, :] * np.cos(th)
    z = t50.sample(xs.ravel(), ys.ravel()).reshape(xs.shape)
    ang = np.degrees(np.arctan2(z - pz[:, None] - (d**2 / (2 * R_EFF))[None, :], d[None, :]))
    ang = np.where(np.isfinite(ang), ang, -90.0)
    if not return_dist:
        return ang.max(axis=1)
    k = ang.argmax(axis=1)
    return ang[np.arange(len(k)), k], d[k]


def block(fn, px, py, pz, azs, **kw) -> np.ndarray:
    out = np.empty((len(px), len(azs)), np.float32)
    for s in range(0, len(px), CHUNK):
        sl = slice(s, s + CHUNK)
        for j, az in enumerate(azs):
            out[sl, j] = fn(px[sl], py[sl], pz[sl], az, **kw)
    return out


def timed(f, *a, **kw):
    t0 = time.perf_counter()
    r = f(*a, **kw)
    return r, time.perf_counter() - t0


# ---------------------------------------------------------------- load
hx, hy = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True).transform(LON, LAT)
pad = RADIUS + NEAR
bounds = (hx - pad, hy - pad, hx + pad, hy + pad)
dsm = load_mosaic_cached(find_tiles(Path("data/dsm")), bounds, CACHE, "dsm")
dtm = load_mosaic_cached(find_tiles(Path("data/dtm")), bounds, CACHE, "dtm")
(t50_50, dt50) = timed(T50Crop, hx, hy, RADIUS + 50_000)
t50_100 = T50Crop(hx, hy, RADIUS + 100_000)
log("t50_crop", {"50km_MB_int16": round(t50_50.nbytes_int16 / 1e6, 1),
                 "100km_MB_int16": round(t50_100.nbytes_int16 / 1e6, 1),
                 "gb_MB_int16": round(np.load(T50_NPY, mmap_mode="r").nbytes / 1e6, 1),
                 "load_50km_s": round(dt50, 2)})

gx, gy, _ = candidate_grid(hx, hy, RADIUS, SPACING)
ground = sample(dtm, gx, gy)
ok = np.isfinite(ground)
gx, gy, gz = gx[ok], gy[ok], ground[ok] + EYE
N = len(gx)
area_km2 = np.pi * (RADIUS / 1000) ** 2
log("candidates", N)
RAY = ray_samples(NEAR)


def near_fn(px, py, pz, az):
    a = horizon_angle(dsm, px, py, pz, az, RAY)
    return np.nan_to_num(a, nan=90.0)


# ---------------------------------------------------------------- E. far-field ray cost
sub = rng.choice(N, size=5000, replace=False)
sx, sy, sz = gx[sub], gy[sub], gz[sub]
az_t = AZ[::5]  # 21 azimuths for timing
_, t_near = timed(block, near_fn, sx, sy, sz, az_t)
log("near_us_per_ray", round(t_near / (len(sub) * len(az_t)) * 1e6, 2))
far_cost = {}
far_ref = {}
for reach, t50 in ((50_000.0, t50_50), (100_000.0, t50_100)):
    for dense in (True, False):
        d = far_dists(reach, dense)
        res, dt = timed(block, lambda px, py, pz, az: far_angle(t50, px, py, pz, az, d),
                        sx, sy, sz, az_t)
        key = f"{int(reach / 1000)}km_{'dense' if dense else 'coarse'}"
        far_ref[key] = res
        far_cost[key] = dict(samples=len(d), us_per_ray=round(dt / res.size * 1e6, 2))
for r in (50, 100):
    e = np.abs(far_ref[f"{r}km_coarse"] - far_ref[f"{r}km_dense"])
    far_cost[f"{r}km coarse-vs-dense abs err p99 / max deg"] = [
        round(float(np.percentile(e, 99)), 3), round(float(e.max()), 3)]
e = far_ref["100km_dense"] - far_ref["50km_dense"]
far_cost["100km-vs-50km raises far horizon, share of pairs >0.01deg (Bristol)"] = round(
    100 * float((e > 0.01).mean()), 3)
log("far_cost", far_cost)
D_FAR = far_dists(50_000.0, dense=False)  # used below


def far_fn(px, py, pz, az):
    return far_angle(t50_50, px, py, pz, az, D_FAR)


# ---------------------------------------------------------------- F. coarse far-field grid
# truth: per-Candidate far field on the 5k subsample, all 101 azimuths
near_sub = block(near_fn, sx, sy, sz, AZ)
far_sub = block(far_fn, sx, sy, sz, AZ)
comb_true = np.maximum(near_sub, far_sub)
far_dom = far_sub >= near_sub
log("share of pairs where far field sets the profile (5k sub, 60-160)",
    round(100 * float(far_dom.mean()), 2))
coarse = {}
for cs in (100.0, 250.0, 500.0):
    # coarse lattice points covering the circle; each Candidate takes its nearest lattice point
    cx_ = np.arange(hx - RADIUS - cs, hx + RADIUS + cs + 1e-6, cs)
    cy_ = np.arange(hy - RADIUS - cs, hy + RADIUS + cs + 1e-6, cs)
    CX, CY = np.meshgrid(cx_, cy_)
    CX, CY = CX.ravel(), CY.ravel()
    cg = sample(dtm, CX, CY)
    keep = np.isfinite(cg)
    CX, CY, CZ = CX[keep], CY[keep], cg[keep] + EYE
    t0 = time.perf_counter()
    fa = np.empty((len(CX), len(AZ)), np.float32)
    fd = np.empty_like(fa)
    for j, az in enumerate(AZ):
        fa[:, j], fd[:, j] = far_angle(t50_50, CX, CY, CZ, az, D_FAR, return_dist=True)
    t_c = time.perf_counter() - t0
    ix = np.round((sx - cx_[0]) / cs).astype(int)
    iy = np.round((sy - cy_[0]) / cs).astype(int)
    lut = {(int(round((x - cx_[0]) / cs)), int(round((y - cy_[0]) / cs))): i
           for i, (x, y) in enumerate(zip(CX, CY))}
    nn = np.array([lut.get((a, b), -1) for a, b in zip(ix, iy)])
    good = nn >= 0
    res = dict(lattice_points=int(len(CX)), compute_s=round(t_c, 2), unmatched=int((~good).sum()))
    for corr in (False, True):
        f_est = fa[nn].copy()
        if corr:  # lower/raise by observer-height difference at the ridge distance
            dz = (sz - CZ[nn])[:, None]
            f_est = f_est - np.degrees(dz / fd[nn])
        c_est = np.maximum(near_sub, f_est)
        err = (c_est - comb_true)[good]
        errf = err[far_dom[good]]
        res["height-corrected" if corr else "nearest"] = dict(
            all_pairs_gt0p1_pct=round(100 * float((np.abs(err) > 0.1).mean()), 3),
            far_set_pairs_gt0p1_pct=round(100 * float((np.abs(errf) > 0.1).mean()), 3),
            far_set_p99_abs_deg=round(float(np.percentile(np.abs(errf), 99)), 3),
            far_set_mean_err_deg=round(float(errf.mean()), 4),
        )
    coarse[f"{int(cs)}m"] = res
log("coarse_far_grid", coarse)

# ---------------------------------------------------------------- full combined profile (all N)
CS = 250.0
cx_ = np.arange(hx - RADIUS - CS, hx + RADIUS + CS + 1e-6, CS)
cy_ = np.arange(hy - RADIUS - CS, hy + RADIUS + CS + 1e-6, CS)
CX, CY = (a.ravel() for a in np.meshgrid(cx_, cy_))
cg = sample(dtm, CX, CY)
# lattice points off the DTM borrow the circle's median ground: they only serve edge Candidates
cg = np.where(np.isfinite(cg), cg, np.nanmedian(gz) - EYE)
CZ = cg + EYE
fa = np.empty((len(CX), len(AZ)), np.float32)
fd = np.empty_like(fa)
for j, az in enumerate(AZ):
    fa[:, j], fd[:, j] = far_angle(t50_50, CX, CY, CZ, az, D_FAR, return_dist=True)
ixa = np.round((gx - cx_[0]) / CS).astype(int)
iya = np.round((gy - cy_[0]) / CS).astype(int)
nn_all = iya * len(cx_) + ixa
near_all, t_near_all = timed(block, near_fn, gx, gy, gz, AZ)
far_all = fa[nn_all] - np.degrees((gz - CZ[nn_all])[:, None] / fd[nn_all])
prof = np.maximum(near_all, far_all)
log("precompute_bristol_60-160_1deg", dict(
    near_s=round(t_near_all, 1), far_250m_grid_s="see coarse_far_grid['250m'].compute_s",
    near_us_per_ray=round(t_near_all / near_all.size * 1e6, 2)))
log("combined_profile_range", [round(float(prof.min()), 2), round(float(prof.max()), 2)])


# ---------------------------------------------------------------- codes
def code_linear(a, q=0.1, lo=-2.0, hi=64.0):
    c = np.round((np.clip(a, lo, hi) - lo) / q)
    return c.astype(np.uint16), lambda c: c.astype(np.float32) * q + lo


# piecewise uint8: 0.1 deg on [-2, 10), 0.5 deg on [10, 63.5]; 120 + 108 = 228 codes
PW_SPLIT, PW_FINE, PW_COARSE, PW_LO, PW_HI = 10.0, 0.1, 0.5, -2.0, 63.5
PW_N_FINE = int(round((PW_SPLIT - PW_LO) / PW_FINE))


def code_piecewise(a):
    a = np.clip(a, PW_LO, PW_HI)
    fine = np.round((a - PW_LO) / PW_FINE)
    coarse_ = PW_N_FINE + np.round((a - PW_SPLIT) / PW_COARSE)
    c = np.where(a < PW_SPLIT - PW_FINE / 2, fine, np.maximum(coarse_, PW_N_FINE))
    assert c.max() < 256

    def dec(c):
        c = c.astype(np.float32)
        return np.where(c < PW_N_FINE, c * PW_FINE + PW_LO, PW_SPLIT + (c - PW_N_FINE) * PW_COARSE)
    return c.astype(np.uint8), dec


def code_linear_u8(a):  # the old 0.5 deg uint8 code, for reference
    c = np.round((np.clip(a, -2.0, 63.5) + 2.0) / 0.5)
    return c.astype(np.uint8), lambda c: c.astype(np.float32) * 0.5 - 2.0


CODES = {"linear_0.1_u16": lambda a: code_linear(a), "piecewise_u8": code_piecewise,
         "linear_0.5_u8": code_linear_u8}
for name, f in CODES.items():
    c, dec = f(prof[:2000])
    log(f"roundtrip max err {name} (angles < 10 deg)",
        round(float(np.abs(dec(c) - np.clip(prof[:2000], -2, 63.5))[prof[:2000] < 10].max()), 3))

# ---------------------------------------------------------------- G. fidelity
fsub = rng.choice(N, size=5000, replace=False)
fx_, fy_, fz_ = gx[fsub], gy[fsub], gz[fsub]
fid = {}
for date in ("2026-12-21", "2026-11-10", "2026-03-20", "2026-06-21"):
    tr = sunrise_hour_track(LAT, LON, date, step_minutes=1.0, window_minutes=180.0)
    inband = (tr.azimuth >= AZ[0]) & (tr.azimuth <= AZ[-1])
    az_tr, el_tr = tr.azimuth[inband], tr.apparent_elevation[inband]
    # exact: per-step near ray + per-Candidate far ray at the sun's own azimuth
    t0 = time.perf_counter()
    ex_near = block(near_fn, fx_, fy_, fz_, az_tr)
    ex_far = block(far_fn, fx_, fy_, fz_, az_tr)
    t_ex = time.perf_counter() - t0
    exact = np.maximum(ex_near, ex_far) < el_tr[None, :]
    ex_len, ex_start, _ = longest_clear_run(exact)
    ex_first = np.where(exact.any(1), exact.argmax(1), -1)
    d = {"steps_in_band": int(inband.sum()), "exact_s_per_5k": round(t_ex, 1),
         "ever_clear_pct": round(100 * float(exact.any(1).mean()), 1)}
    for name, f in CODES.items():
        c, dec = f(prof[fsub])
        pq = dec(c)
        interp = np.stack([np.interp(az_tr, AZ, row) for row in pq])
        approx = interp < el_tr[None, :]
        ap_len, _, _ = longest_clear_run(approx)
        ap_first = np.where(approx.any(1), approx.argmax(1), -1)
        diff = np.abs(ap_len.astype(int) - ex_len.astype(int))
        both = (ex_first >= 0) & (ap_first >= 0)
        fs = np.abs(ap_first - ex_first)[both]
        d[name] = dict(
            verdict_disagree_pct=round(100 * float((approx != exact).mean()), 3),
            window_mean_abs_diff_min=round(float(diff.mean()), 2),
            window_diff_gt5min_pct=round(100 * float((diff > 5).mean()), 2),
            first_sun_mean_abs_diff_min=round(float(fs.mean()), 2),
            first_sun_diff_gt2min_pct=round(100 * float((fs > 2).mean()), 2),
        )
    fid[date] = d
log("fidelity (combined profile, 1 deg, 60-160)", fid)

# ---------------------------------------------------------------- H. storage
order = np.lexsort((gx, -gy))
store = {}
for name, f in CODES.items():
    c, _ = f(prof[order])
    raw = c.tobytes()
    dt_ = np.int8 if c.dtype == np.uint8 else np.int16
    delta = np.diff(c.astype(np.int16), axis=1, prepend=0).astype(dt_).tobytes()
    xz = len(lzma.compress(delta, preset=6))
    store[name] = dict(raw_MB=round(len(raw) / 1e6, 2), xz_delta_MB=round(xz / 1e6, 2),
                       xz_MB_per_km2=round(xz / 1e6 / area_km2, 3),
                       england_GB=round(xz / 1e6 / area_km2 * 130_300 / 1e3, 1))
log("storage (combined, 10 m, 60-160 @ 1 deg)", store)

# ---------------------------------------------------------------- G2/H2. azimuth step sweep
# Fidelity at 0.25 / 0.5 / 1 deg steps (piecewise_u8), linear vs conservative (max of the two
# bracketing samples) interpolation; storage per km2 on the inner 500 m disc.
def combined_at(px, py, pz, azs):
    near = block(near_fn, px, py, pz, azs)
    fa_ = np.empty((len(CX), len(azs)), np.float32)
    fd_ = np.empty_like(fa_)
    for j, az in enumerate(azs):
        fa_[:, j], fd_[:, j] = far_angle(t50_50, CX, CY, CZ, az, D_FAR, return_dist=True)
    nn = (np.round((py - cy_[0]) / CS).astype(int) * len(cx_)
          + np.round((px - cx_[0]) / CS).astype(int))
    far = fa_[nn] - np.degrees((pz - CZ[nn])[:, None] / fd_[nn])
    return np.maximum(near, far)


def interp_max(x, xp, fp):
    k = np.clip(np.searchsorted(xp, x) - 1, 0, len(xp) - 2)
    return np.maximum(fp[k], fp[k + 1])


AZ_Q = np.arange(60.0, 160.0 + 1e-9, 0.25)
prof_q = combined_at(fx_, fy_, fz_, AZ_Q)
sweep = {}
for date in ("2026-12-21", "2026-11-10", "2026-03-20", "2026-06-21"):
    tr = sunrise_hour_track(LAT, LON, date, step_minutes=1.0, window_minutes=180.0)
    inband = (tr.azimuth >= AZ[0]) & (tr.azimuth <= AZ[-1])
    az_tr, el_tr = tr.azimuth[inband], tr.apparent_elevation[inband]
    exact = (np.maximum(block(near_fn, fx_, fy_, fz_, az_tr), block(far_fn, fx_, fy_, fz_, az_tr))
             < el_tr[None, :])
    ex_len, _, _ = longest_clear_run(exact)
    ex_first = np.where(exact.any(1), exact.argmax(1), -1)
    for step in (0.25, 0.5, 1.0):
        k = int(round(step / 0.25))
        az_s = AZ_Q[::k]
        c, dec = code_piecewise(prof_q[:, ::k])
        pq = dec(c)
        for mode in ("linear", "max"):
            if mode == "linear":
                h = np.stack([np.interp(az_tr, az_s, row) for row in pq])
            else:
                h = np.stack([interp_max(az_tr, az_s, row) for row in pq])
            approx = h < el_tr[None, :]
            ap_len, _, _ = longest_clear_run(approx)
            ap_first = np.where(approx.any(1), approx.argmax(1), -1)
            both = (ex_first >= 0) & (ap_first >= 0)
            sd = (ap_first - ex_first)[both]
            sweep[f"{date} az{step} {mode}"] = dict(
                verdict_disagree_pct=round(100 * float((approx != exact).mean()), 3),
                window_mean_abs_diff_min=round(float(np.abs(ap_len.astype(int) - ex_len.astype(int)).mean()), 2),
                first_sun_mean_abs_min=round(float(np.abs(sd).mean()), 2),
                first_sun_early_gt2min_pct=round(100 * float((sd < -2).mean()), 2),
                first_sun_late_gt2min_pct=round(100 * float((sd > 2).mean()), 2),
                ever_clear_mismatch_pct=round(100 * float((exact.any(1) != approx.any(1)).mean()), 2),
            )
log("az step sweep (piecewise_u8)", sweep)

inner = np.hypot(gx - hx, gy - hy) <= 500.0
ix_ = np.flatnonzero(inner)
ix_ = ix_[np.lexsort((gx[ix_], -gy[ix_]))]
prof_in = combined_at(gx[ix_], gy[ix_], gz[ix_], AZ_Q)
in_km2 = np.pi * 0.5**2
st2 = {}
for step in (0.25, 0.5, 1.0):
    c, _ = code_piecewise(prof_in[:, ::int(round(step / 0.25))])
    delta = np.diff(c.astype(np.int16), axis=1, prepend=0).astype(np.int8).tobytes()
    xz = len(lzma.compress(delta, preset=6))
    st2[f"az{step}"] = dict(xz_MB_per_km2=round(xz / 1e6 / in_km2, 3),
                            england_GB=round(xz / 1e6 / in_km2 * 130_300 / 1e3, 1))
log("storage by az step (piecewise_u8, inner 500 m disc, 10 m)", st2)

Path("prototype/horizon_cost_farfield_results.json").write_text(json.dumps(OUT, indent=1))
