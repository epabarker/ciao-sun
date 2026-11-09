"""PROTOTYPE -- throwaway cost benchmark for the wayfinder ticket
"On-demand run vs precomputed Horizon profiles: what do they cost?"
(epabarker/daylight-viewing#6). Lives on branch prototype/horizon-cost; never merged.

Neither prototype branch (logic / UI) fits this question, so this is a cost
benchmark: rough numbers are the asset. It imports sunspot, never modifies it.

Measures, for Bristol (home 51.4720,-2.6040, radius 1500 m, spacing 10 m):
  A. on-demand scoring cost per ray (candidate x sun-track step), for the
     default track and for wake-anchored 2-3 h tracks the research points to;
  B. precompute cost per ray (candidate x azimuth) for Horizon profiles;
  C. fidelity: clear/blocked disagreement between exact on-demand scoring and
     a quantised, azimuth-interpolated precomputed profile;
  D. storage: raw and compressed size per km^2 for spacing / az step / quantisation.

Run:  uv run python prototype/horizon_cost_bench.py <cache_dir>
"""

from __future__ import annotations

import json
import lzma
import sys
import time
import warnings
import zlib
from pathlib import Path

import numpy as np
from pyproj import Transformer

from sunspot.horizon import horizon_angle, ray_samples
from sunspot.raster import find_tiles, load_mosaic_cached, sample
from sunspot.search import candidate_grid, longest_clear_run
from sunspot.solar import SunTrack, sunrise_hour_track

warnings.filterwarnings("ignore", message="All-NaN (slice|axis) encountered")

LAT, LON = 51.4720, -2.6040
RADIUS, SPACING, EYE, MAX_RAY = 1500.0, 10.0, 1.6, 3000.0
CHUNK = 4000
AZ_LO, AZ_HI = 40.0, 200.0  # widest band computed; narrower bands are slices of it
ANG_LO, ANG_HI = -2.0, 64.0  # clamp: below -2 always clears, above max sun el always blocks
CACHE = Path(sys.argv[1] if len(sys.argv) > 1 else "data/cache")
OUT: dict[str, object] = {}


def log(k: str, v: object) -> None:
    OUT[k] = v
    print(f"{k}: {v}", flush=True)


# ---------------------------------------------------------------- load
hx, hy = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True).transform(LON, LAT)
pad = RADIUS + MAX_RAY
bounds = (hx - pad, hy - pad, hx + pad, hy + pad)
t0 = time.perf_counter()
dsm = load_mosaic_cached(find_tiles(Path("data/dsm")), bounds, CACHE, "dsm")
dtm = load_mosaic_cached(find_tiles(Path("data/dtm")), bounds, CACHE, "dtm")
log("load_mosaics_s (from npz cache)", round(time.perf_counter() - t0, 2))

gx, gy, dist = candidate_grid(hx, hy, RADIUS, SPACING)
ground = sample(dtm, gx, gy)
ok = np.isfinite(ground)
gx, gy, gz = gx[ok], gy[ok], ground[ok] + EYE
N = len(gx)
area_km2 = np.pi * (RADIUS / 1000) ** 2
log("candidates", N)
log("area_km2", round(area_km2, 2))
ray_d = ray_samples(MAX_RAY)
log("samples_per_ray", len(ray_d))


def profile_block(px, py, pz, azimuths) -> np.ndarray:
    """(n, n_az) horizon angles, chunked as score_candidates does."""
    out = np.empty((len(px), len(azimuths)), dtype=np.float32)
    for s in range(0, len(px), CHUNK):
        sl = slice(s, s + CHUNK)
        for j, az in enumerate(azimuths):
            out[sl, j] = horizon_angle(dsm, px[sl], py[sl], pz[sl], az, ray_d)
    return out


def exact_clear(px, py, pz, track: SunTrack) -> np.ndarray:
    ang = profile_block(px, py, pz, track.azimuth)
    return ang < track.apparent_elevation[None, :]


# ---------------------------------------------------------------- A. on-demand
tracks = {
    "default_60min_5min": dict(step_minutes=5.0, window_minutes=60.0),
    "wake_2h_2min": dict(step_minutes=2.0, window_minutes=120.0),
}
for name, kw in tracks.items():
    tr = sunrise_hour_track(LAT, LON, "2026-12-21", step_minutes=kw["step_minutes"],
                            window_minutes=kw["window_minutes"])
    t0 = time.perf_counter()
    exact_clear(gx, gy, gz, tr)
    dt = time.perf_counter() - t0
    rays = N * len(tr.azimuth)
    log(f"ondemand_{name}", dict(steps=len(tr.azimuth), rays=rays, seconds=round(dt, 2),
                                  us_per_ray=round(dt / rays * 1e6, 2)))

# ---------------------------------------------------------------- B. precompute
az_fine = np.arange(AZ_LO, AZ_HI + 1e-9, 0.5)
# flatness check on subsets
for n in (4000, 20000):
    t0 = time.perf_counter()
    profile_block(gx[:n], gy[:n], gz[:n], az_fine[:20])
    dt = time.perf_counter() - t0
    log(f"precompute_flatness_n{n}", round(dt / (n * 20) * 1e6, 2))
t0 = time.perf_counter()
prof = profile_block(gx, gy, gz, az_fine)  # (N, 321) float32, 0.5 deg step
dt = time.perf_counter() - t0
log("precompute_full_0.5deg", dict(azimuths=len(az_fine), rays=N * len(az_fine),
                                   seconds=round(dt, 1),
                                   us_per_ray=round(dt / (N * len(az_fine)) * 1e6, 2)))
log("profile_angle_range", [float(np.nanmin(prof)), float(np.nanmax(prof))])
log("profile_nan_frac", float(np.isnan(prof).mean()))


def resample(step: float) -> tuple[np.ndarray, np.ndarray]:
    k = int(round(step / 0.5))
    return az_fine[::k], prof[:, ::k]


def quantise(a: np.ndarray, q: float | None) -> np.ndarray:
    """Return dequantised angles (what a client would reconstruct)."""
    a = np.nan_to_num(a, nan=90.0)  # off-grid ray: treated as blocked, as callers do
    a = np.clip(a, ANG_LO, ANG_HI)
    if q is None:
        return a
    return np.round((a - ANG_LO) / q) * q + ANG_LO


def codes(a: np.ndarray, q: float) -> np.ndarray:
    a = np.clip(np.nan_to_num(a, nan=ANG_HI), ANG_LO, ANG_HI)
    c = np.round((a - ANG_LO) / q)
    return c.astype(np.uint8 if c.max() < 256 else np.uint16)


# ---------------------------------------------------------------- C. fidelity
rng = np.random.default_rng(0)
sub = rng.choice(N, size=15000, replace=False)
fid: dict[str, object] = {}
for date in ("2026-12-21", "2026-03-20", "2026-06-21"):
    tr = sunrise_hour_track(LAT, LON, date, step_minutes=1.0, window_minutes=180.0)
    inband = (tr.azimuth >= AZ_LO) & (tr.azimuth <= AZ_HI)
    exact = exact_clear(gx[sub], gy[sub], gz[sub], tr)
    ex_len, _, _ = longest_clear_run(exact)
    for step in (0.5, 1.0, 2.0):
        az_s, p_s = resample(step)
        for q in (None, 0.1, 0.25, 0.5):
            pq = quantise(p_s[sub], q)
            interp = np.stack([np.interp(tr.azimuth, az_s, row) for row in pq])
            approx = interp < tr.apparent_elevation[None, :]
            ap_len, _, _ = longest_clear_run(approx)
            diff = np.abs(ap_len.astype(int) - ex_len.astype(int))
            fid[f"{date} az{step} q{q}"] = dict(
                verdict_disagree_pct=round(100 * float((approx != exact)[:, inband].mean()), 3),
                window_mean_abs_diff_min=round(float(diff.mean()), 2),
                window_diff_gt5min_pct=round(100 * float((diff > 5).mean()), 2),
            )
    fid[f"{date} sun_az_range"] = [round(float(tr.azimuth.min()), 1), round(float(tr.azimuth.max()), 1)]
    fid[f"{date} ever_clear_pct"] = round(100 * float((ex_len > 0).mean()), 1)
log("fidelity", fid)

# ---------------------------------------------------------------- D. storage
# spacing 20 m = every other grid row/col of the 10 m grid
on20 = (np.isclose((gx - hx) % 20, 0) | np.isclose((gx - hx) % 20, 20)) & \
       (np.isclose((gy - hy) % 20, 0) | np.isclose((gy - hy) % 20, 20))
# order candidates row-major (north->south, west->east) so neighbours sit together
order = np.lexsort((gx, -gy))
size: dict[str, object] = {}
for spacing, mask in ((10, np.ones(N, bool)), (20, on20)):
    idx = order[mask[order]]
    for step in (0.5, 1.0, 2.0):
        az_s, p_s = resample(step)
        for q in (0.1, 0.25, 0.5):
            c = codes(p_s[idx], q)
            raw = c.tobytes()
            delta = np.diff(c.astype(np.int16), axis=1, prepend=0).astype(
                np.int8 if c.dtype == np.uint8 else np.int16).tobytes()
            z = len(zlib.compress(raw, 9))
            zd = len(zlib.compress(delta, 9))
            xz = len(lzma.compress(delta, preset=6))
            n_az = c.shape[1]
            per_deg_raw = len(raw) / (n_az * step)  # bytes per degree of band, this area
            size[f"s{spacing} az{step} q{q}"] = dict(
                dtype=str(c.dtype), n_az=n_az,
                raw_MB=round(len(raw) / 1e6, 2), zlib_MB=round(z / 1e6, 2),
                zlib_delta_MB=round(zd / 1e6, 2), xz_delta_MB=round(xz / 1e6, 2),
                xz_delta_MB_per_km2=round(xz / 1e6 / area_km2, 3),
                raw_MB_per_km2_per_deg=round(per_deg_raw / 1e6 / area_km2, 4),
                xz_ratio=round(len(raw) / xz, 1),
            )
log("storage (band 40-200)", size)

Path("prototype/horizon_cost_results.json").write_text(json.dumps(OUT, indent=1))
