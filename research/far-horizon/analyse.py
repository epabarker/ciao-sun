"""RESEARCH, throwaway. Reach statistics and Sun-minute impact from profiles.py output.

    uv run python -I analyse.py <profiles.npz> <outdir>
Writes reach.csv, clutter.csv, ticket_candidate.csv, sun_by_day.csv, sun_dates.csv and prints
the summary tables quoted in far-horizon.md.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib

sys.path.insert(0, str(Path(__file__).parent))
from farlib import FWD, nanmax  # noqa: E402

from sunspot.solar import find_sunrise  # noqa: E402

P = np.load(sys.argv[1])
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
LAT, LON = 51.4720, -2.6040
AZ, BANDS = P["az"], P["bands"]
near, t50, dsm, dtm, dsmall = (P[k] for k in ("near", "t50", "dsm", "dtm", "dsmall"))
N = near.shape[0]
hx, hy = FWD.transform(LON, LAT)
dist_home = np.hypot(P["x"] - hx, P["y"] - hy)
pd.set_option("display.width", 200)


def far_upto(bands_arr, r_m):
    sel = [b for b in range(len(BANDS) - 1) if BANDS[b + 1] <= r_m + 1e-6]
    if not sel:
        return np.full(bands_arr.shape[:2], -90.0, np.float32)
    return nanmax(bands_arr[:, :, sel], axis=2)


# ---------------------------------------------------------------- 1. reach statistics
rows = []
R_LIST = [3, 5, 7, 10, 15, 20, 25, 30, 50, 75, 100, 150, 200]
for src_name, src in (("terrain50", t50), ("lidar_dsm_then_t50", dsmall)):
    truth = np.fmax(near, far_upto(src, 200e3))
    for cond_name, cond in (("all", truth > -90), ("near<2 (open view)", near < 2.0),
                            ("near<1", near < 1.0),
                            ("near<1 & az 90-135", (near < 1.0) & ((AZ >= 90) & (AZ <= 135))[None, :])):
        for r in R_LIST:
            est = near if r == 3 else np.fmax(near, far_upto(src, r * 1e3))
            err = (truth - est)[cond]
            rows.append({"far_source": src_name, "condition": cond_name, "reach_km": r,
                         "n_pairs": int(err.size), "frac_err_gt_0.05": float((err > 0.05).mean()),
                         "frac_err_gt_0.1": float((err > 0.1).mean()),
                         "frac_err_gt_0.25": float((err > 0.25).mean()),
                         "p99_err": float(np.percentile(err, 99)), "max_err": float(err.max())})
reach = pd.DataFrame(rows)
reach.to_csv(OUT / "reach.csv", index=False, float_format="%.4f")
print(reach[reach.far_source == "lidar_dsm_then_t50"].to_string(index=False))

# Which band sets the far horizon, per azimuth sector (median over Candidates)
far_all = far_upto(dsmall, 200e3)
arg = np.nanargmax(np.where(np.isnan(dsmall), -99, dsmall), axis=2)
sect = []
for a0 in range(45, 165, 10):
    m = (AZ >= a0) & (AZ < a0 + 10)
    lifts = np.fmax(far_all[:, m] - np.fmax(near[:, m], 0), 0)
    sect.append({"az": f"{a0}-{a0 + 10}", "near_median": np.median(near[:, m]),
                 "far_median": np.median(far_all[:, m]), "far_p90": np.percentile(far_all[:, m], 90),
                 "modal_band_km": f"{BANDS[np.bincount(arg[:, m].ravel()).argmax()] / 1e3:.0f}+",
                 "frac_far_gt_max(near,0)": float((far_all[:, m] > np.fmax(near[:, m], 0)).mean()),
                 "median_lift_where_lifted": float(np.median(lifts[lifts > 0])) if (lifts > 0).any() else 0})
sect = pd.DataFrame(sect)
sect.to_csv(OUT / "far_by_sector.csv", index=False, float_format="%.3f")
print(sect.to_string(index=False))

# ---------------------------------------------------------------- 2. clutter: DSM vs DTM vs T50, 3-25 km
cl = []
for b in range(6):
    d1, d2 = dsm[:, :, b] - t50[:, :, b], dtm[:, :, b] - t50[:, :, b]
    m = (d1 != 0) | (d2 != 0)  # paired LIDAR coverage on this band
    if m.sum() < 100:
        continue
    cl.append({"band_km": f"{BANDS[b] / 1e3:.0f}-{BANDS[b + 1] / 1e3:.0f}", "n_pairs": int(m.sum()),
               "dsm_minus_t50_median": np.median(d1[m]), "dsm_minus_t50_p90": np.percentile(d1[m], 90),
               "dtm_minus_t50_median": np.median(d2[m]), "dtm_minus_t50_p90": np.percentile(d2[m], 90),
               "dsm_minus_dtm_median": np.median((dsm - dtm)[:, :, b][m]),
               "dsm_minus_dtm_p90": np.percentile((dsm - dtm)[:, :, b][m], 90)})
cl = pd.DataFrame(cl)
cl.to_csv(OUT / "clutter.csv", index=False, float_format="%.3f")
print(cl.to_string(index=False))
# Effect of clutter on the final horizon (beyond 3 km, both far sources out to 200 km)
fin_t = np.fmax(near, far_upto(t50, 200e3))
fin_d = np.fmax(near, far_upto(dsmall, 200e3))
for cond_name, cond in (("all", np.ones_like(fin_d, bool)), ("near<2", near < 2.0)):
    dd = (fin_d - fin_t)[cond]
    print(f"final horizon, LIDAR DSM 3-25 km minus Terrain 50, {cond_name}: median {np.median(dd):.3f} "
          f"p90 {np.percentile(dd, 90):.3f} p99 {np.percentile(dd, 99):.3f}  frac>0.1 {(dd > 0.1).mean():.3f}")

# ---------------------------------------------------------------- 3. ticket Candidate profile
tk = pd.DataFrame({"az_true": AZ, "near_3km": near[0], "terrain50_3_200km": far_upto(t50, 200e3)[0],
                   "lidar_dsm_3_25km_then_t50": far_upto(dsmall, 200e3)[0]})
for b in range(len(BANDS) - 1):
    tk[f"dsm_band_{BANDS[b] / 1e3:.0f}_{BANDS[b + 1] / 1e3:.0f}km"] = dsmall[0, :, b]
tk.to_csv(OUT / "ticket_candidate.csv", index=False, float_format="%.3f")
print(tk[(tk.az_true >= 112) & (tk.az_true <= 126)].iloc[:, :4].to_string(index=False))


# ---------------------------------------------------------------- 4. Sun minutes / first sun
def q05(p):  # the answer-screen fixture's byte quantisation: round((angle + 10) * 2) / 2 - 10
    return np.round((p + 10.0) * 2.0) / 2.0 - 10.0


far10 = np.concatenate([dsmall[:, :, :3], t50[:, :, 3:]], axis=2)  # LIDAR DSM 3-10 km, T50 beyond
TRUTH = "dsm25_t50_200km"
VARIANTS = {
    "near3": near,                                   # prototype geometry, unquantised
    "near3_q05": q05(near),                          # prototype as shipped (0.5 deg bytes)
    "t50_10km": np.fmax(near, far_upto(t50, 10e3)),
    "t50_20km": np.fmax(near, far_upto(t50, 20e3)),
    "t50_30km": np.fmax(near, far_upto(t50, 30e3)),
    "t50_50km": np.fmax(near, far_upto(t50, 50e3)),
    "dsm10_t50_50km": np.fmax(near, far_upto(far10, 50e3)),  # recommended split
    TRUTH: np.fmax(near, far_upto(dsmall, 200e3)),
}
# src/ and the fixture pass true (pvlib) azimuth to a grid-azimuth ray caster. Emulate that on the
# truth profile: the value used for true azimuth a is the one actually cast at true azimuth a + conv.
_T = VARIANTS[TRUTH]
VARIANTS["truth_no_convergence_fix"] = np.array([np.interp(AZ + float(P["conv"]), AZ, r) for r in _T],
                                                 dtype=np.float32)
WAKE = 7 * 60
walk_min = 1.3 * dist_home / 83.0


def horizon_at(prof, az):
    j = (az - AZ[0]) / (AZ[1] - AZ[0])
    out = np.full((prof.shape[0], len(az)), 90.0, np.float32)
    ok = (j >= 0) & (j <= len(AZ) - 1)
    j0 = np.clip(np.floor(j[ok]).astype(int), 0, len(AZ) - 2)
    f = (j[ok] - j0).astype(np.float32)
    out[:, ok] = prof[:, j0] * (1 - f) + prof[:, j0 + 1] * f
    return out


def pick(order, k=5, dedupe=200.0):
    chosen = []
    for c in order:
        if all(np.hypot(P["x"][c] - P["x"][o], P["y"][c] - P["y"][o]) > dedupe for o in chosen):
            chosen.append(c)
        if len(chosen) >= k:
            break
    return chosen


days = pd.date_range("2026-11-10", periods=365, freq="D")
recs = []
for d in days:
    ds = d.strftime("%Y-%m-%d")
    sr = find_sunrise(LAT, LON, ds)
    sr_min = sr.hour * 60 + sr.minute
    start, end = max(WAKE, sr_min), WAKE + 180
    t = pd.date_range(f"{ds} 00:00", periods=24 * 60, freq="1min", tz="Europe/London")[start:end]
    sp = pvlib.solarposition.get_solarposition(t, LAT, LON)
    az, el = sp.azimuth.to_numpy(), sp.apparent_elevation.to_numpy()
    mins = np.arange(start, end)
    w = np.where(mins - WAKE <= 60, 1.0, np.maximum(0, 1 - (mins - WAKE - 60) / 120))
    for rule in ("gate", "phys"):
        res = {}
        for vname, prof in VARIANTS.items():
            H = horizon_at(prof, az)
            vis = (el[None, :] > H) & ((el[None, :] > 0) if rule == "gate" else True)
            sun_min = vis.sum(1)
            wsun = (vis * w[None, :]).sum(1)
            first = np.where(vis.any(1), mins[np.argmax(vis, 1)], np.nan)
            order = np.lexsort((walk_min, -np.round(wsun)))
            order = order[sun_min[order] > 0]
            res[vname] = (first, sun_min, wsun, pick(order))
        fT, sT, wT, topT = res[TRUTH]
        for vname, (f, s, wv, top) in res.items():
            both = np.isfinite(f) & np.isfinite(fT)
            r = {"date": ds, "sunrise": sr_min, "start": start, "rule": rule, "variant": vname,
                 "ticket_first": f[0], "ticket_sun_min": int(s[0]), "n_with_sun": int((s > 0).sum()),
                 "frac_first_wrong": float((f[both] != fT[both]).mean()) if both.any() else np.nan,
                 "n_false_sun": int((np.isfinite(f) & ~np.isfinite(fT)).sum())}
            if top and topT:
                tt = np.array(top)
                ok = np.isfinite(fT[tt])
                # what the variant tells you about its own top 5, minus the truth for those spots
                r["top5_first_early_mean"] = float(np.mean(fT[tt][ok] - f[tt][ok])) if ok.any() else np.nan
                r["top5_first_early_max"] = float(np.max(fT[tt][ok] - f[tt][ok])) if ok.any() else np.nan
                r["top5_sun_min_overstated_mean"] = float(np.mean(s[tt] - sT[tt]))
                r["top1_same_as_truth"] = bool(top[0] == topT[0])
                r["top5_overlap_truth"] = len(set(top) & set(topT))
                # regret: true weighted sun of the truth's #1 minus that of the variant's #1
                r["regret_wsun_top1"] = float(wT[topT[0]] - wT[top[0]])
                r["regret_frac_top1"] = float((wT[topT[0]] - wT[top[0]]) / wT[topT[0]]) if wT[topT[0]] else 0.0
            recs.append(r)
sun = pd.DataFrame(recs)
sun.to_csv(OUT / "sun_by_day.csv", index=False, float_format="%.3f")


def hm(m):
    return "" if not np.isfinite(m) else f"{int(m) // 60:02d}:{int(m) % 60:02d}"


key = sun[sun.date.isin(["2026-11-10", "2026-12-21", "2027-02-01", "2027-03-20", "2027-06-21"])].copy()
for c in ("sunrise", "ticket_first"):
    key[c] = key[c].map(hm)
key.to_csv(OUT / "sun_dates.csv", index=False, float_format="%.3f")
print(key.drop(columns=["start"]).to_string(index=False))

sun["window_starts_at_sunrise"] = sun.sunrise > WAKE
summ = sun.groupby(["window_starts_at_sunrise", "rule", "variant"], sort=False).agg(
    days=("date", "count"),
    frac_first_wrong=("frac_first_wrong", "mean"),
    top5_first_early_mean=("top5_first_early_mean", "mean"),
    top5_first_early_max=("top5_first_early_max", "max"),
    top5_sun_min_overstated=("top5_sun_min_overstated_mean", "mean"),
    top1_differs_days=("top1_same_as_truth", lambda s: int((~s.astype(bool)).sum())),
    top5_overlap_mean=("top5_overlap_truth", "mean"),
    regret_wsun_mean=("regret_wsun_top1", "mean"),
    regret_wsun_max=("regret_wsun_top1", "max"),
    regret_frac_mean=("regret_frac_top1", "mean"))
summ.to_csv(OUT / "sun_season_summary.csv", float_format="%.3f")
print(summ.to_string())
print("candidates", N)
