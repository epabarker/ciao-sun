"""PROTOTYPE, throwaway. Scores Candidates on each canopy surface and compares them.

Ticket: epabarker/daylight-viewing#23. Reads <outdir>/profiles.npz from build_profiles.py.
Applies the decided Stage 1 rules (Morning window #7/#10, Evening window #20, sun counts
once its apparent centre clears the profile at any sign #14, openness cut-off 0.75 along
the window's sun path +-10 deg, rank by low-sun minutes then nearest, 200 m de-dupe).

    uv run python <worktree>/prototype/leaf-on-canopy/analyse.py <outdir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib

OUT = Path(sys.argv[1])
P = np.load(OUT / "profiles.npz")
AZ = P["az"]
AZ0, AZS = float(AZ[0]), float(AZ[1] - AZ[0])
X, Y, WALK = P["x"], P["y"], P["walk_m"] / 83.0
LAT, LON = 51.4720, -2.6040
WAKE = 7 * 60
MAX_WALK = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
CUTOFF, DEDUPE, TARGET = 0.75, 200.0, 10.0
DATES = ["2026-11-10", "2026-12-21", "2027-02-05", "2027-03-20", "2027-05-15", "2027-06-21", "2027-09-22", "2027-10-15"]
SURF = ["asis", "bare_on", "bare_all", "leafy"]
# +1: the alternative surface has fewer trees (as-is is pessimistic); -1: more (as-is optimistic)
SIGN = {"bare_on": 1, "bare_all": 1, "leafy": -1}
PROF = {s: P[s] for s in SURF}
reach = WALK <= MAX_WALK


def lookup(prof, az):
    j = (np.asarray(az) - AZ0) / AZS
    j0 = np.clip(np.floor(j).astype(int), 0, len(AZ) - 2)
    f = (j - j0).astype(np.float32)
    return prof[:, j0] * (1 - f) + prof[:, j0 + 1] * f


def track(ds):
    t = pd.date_range(f"{ds} 00:00", f"{ds} 23:59", freq="1min", tz="Europe/London")
    sp = pvlib.solarposition.get_solarposition(t, LAT, LON)
    return sp["azimuth"].to_numpy(), sp["apparent_elevation"].to_numpy(), sp["elevation"].to_numpy()


def openness(prof, az_lo, az_hi):
    a = np.arange(np.floor(az_lo - 10), np.ceil(az_hi + 10) + 1, 1.0)
    h = np.maximum(0, lookup(prof, a))
    return (np.cos(np.radians(h)) ** 2).mean(axis=1)


def score(ds, window):
    az, el, geo = track(ds)
    up = np.nonzero(geo > -0.833)[0]
    sunrise, sunset, noon = int(up[0]), int(up[-1]) + 1, int(np.argmax(geo))
    if window == "morning":
        start, end = max(WAKE, sunrise), WAKE + 180
        m = np.arange(start, end)
        rel = m - WAKE
        w = np.where(rel <= 60, 1.0, np.clip(1 - (rel - 60) / 120, 0, 1))
    else:
        start, end = max(noon, WAKE + 360), sunset
        m = np.arange(start, end)
        w = np.ones(len(m))
    sel = el[m] > -1
    out = {"start": start, "end": end, "sunrise": sunrise, "sunset": sunset}
    for s in SURF:
        h = lookup(PROF[s], az[m])
        vis = el[m][None, :] > h
        low = vis & (el[m][None, :] <= 30)
        any_ = vis.any(axis=1)
        first = np.where(any_, m[np.argmax(vis, axis=1)], -1).astype(float)
        last = np.where(any_, m[len(m) - 1 - np.argmax(vis[:, ::-1], axis=1)] + 1, -1).astype(float)
        first[~any_] = np.nan
        last[~any_] = np.nan
        out[s] = {
            "vis": any_,
            "sun": vis.sum(axis=1).astype(float),
            "low": (low * w[None, :]).sum(axis=1),
            "first": first,
            "last": last,
            "svf": openness(PROF[s], az[m][sel].min(), az[m][sel].max()),
        }
    return out


def rank(r, k=5):
    ok = reach & (r["svf"] >= CUTOFF) & r["vis"]
    idx = np.nonzero(ok)[0]
    idx = idx[np.lexsort((WALK[idx], -np.round(r["low"][idx])))]
    chosen = []
    for i in idx:
        if all(np.hypot(X[i] - X[j], Y[i] - Y[j]) > DEDUPE for j in chosen):
            chosen.append(i)
        if len(chosen) >= k:
            break
    return np.array(chosen, int)


def leave_by(r, idx, window):
    if window == "morning":
        return np.maximum(WAKE, r["first"][idx] - WALK[idx])
    return r["last"][idx] - np.maximum(TARGET, WALK[idx])


def stats(v):
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return {"n": 0}
    return {"n": int(len(v)), "mean": round(float(v.mean()), 2), "p90": round(float(np.percentile(v, 90)), 1),
            "max": round(float(v.max()), 1), "share_ge1": round(float(np.mean(v >= 1)), 3),
            "share_ge5": round(float(np.mean(v >= 5)), 3)}


rows, detail = [], {}
for ds in DATES:
    for window in ["morning", "evening"]:
        sc = score(ds, window)
        if sc["start"] >= sc["end"]:
            continue
        a = sc["asis"]
        top_a = rank(a)
        for s in ["bare_on", "bare_all", "leafy"]:
            b = sc[s]
            sg = SIGN[s]
            both = reach & a["vis"] & b["vis"] & (a["svf"] >= CUTOFF)
            if window == "morning":
                shift = sg * (a["first"] - b["first"])  # minutes the as-is answer is off, in the expected direction
            else:
                shift = sg * (b["last"] - a["last"])
            gained = int(np.sum(reach & (a["svf"] < CUTOFF) & (b["svf"] >= CUTOFF)))
            lost = int(np.sum(reach & (a["svf"] >= CUTOFF) & (b["svf"] < CUTOFF)))
            newly_sunny = int(np.sum(reach & (a["svf"] >= CUTOFF) & ~a["vis"] & b["vis"]))
            top_b = rank(b)
            lb_a = leave_by(a, top_a, window)
            lb_b_same = leave_by(b, top_a, window)
            lb_shift = sg * ((lb_a - lb_b_same) if window == "morning" else (lb_b_same - lb_a))
            best_b = b["low"][top_b[0]] if len(top_b) else np.nan
            share = float(b["low"][top_a[0]] / best_b) if len(top_a) and best_b > 0 else np.nan
            overlap = len(set(top_a.tolist()) & {i for i in top_b.tolist()})
            near5 = sum(any(np.hypot(X[i] - X[j], Y[i] - Y[j]) <= DEDUPE for j in top_b) for i in top_a)
            rows.append({
                "date": ds, "window": window, "surface": s,
                "win": f"{sc['start'] // 60:02d}:{sc['start'] % 60:02d}-{sc['end'] // 60:02d}:{sc['end'] % 60:02d}",
                "shift_all": stats(shift[both]),
                "low_gain_all": stats(sg * (b["low"] - a["low"])[both]),
                "svf_gain_mean": round(float(sg * (b["svf"] - a["svf"])[reach].mean()), 3),
                "open_gained": gained, "open_lost": lost, "open_reach_asis": int(np.sum(reach & (a["svf"] >= CUTOFF))),
                "newly_sunny": newly_sunny,
                "top5_leave_shift": [None if not np.isfinite(v) else round(float(v), 1) for v in lb_shift],
                "top5_low_asis": [round(float(a["low"][i]), 1) for i in top_a],
                "top1_share_of_best": None if not np.isfinite(share) else round(share, 3),
                "top5_same_spot": overlap, "top5_within_200m": int(near5),
                "top5_walk": [round(float(WALK[i]), 1) for i in top_a],
            })
        detail[f"{ds}_{window}"] = {k: sc[k] for k in ["start", "end", "sunrise", "sunset"]}

(OUT / f"results_walk{int(MAX_WALK)}.json").write_text(json.dumps(rows, indent=1))


def fmt(st, key="mean"):
    return "–" if st.get("n", 0) == 0 else f"{st['mean']:.1f} / {st['p90']:.0f} / {st['max']:.0f}"


lines = [f"Max walk {MAX_WALK:.0f} min, Wake 07:00, {int(reach.sum())} reachable Candidates.",
         "", "| date | window | surface | first/last-sun shift, open spots (mean / p90 / max min) | share ≥5 min "
         "| low-sun gain mean | openness: gained / lost / open | top-5 leave-by shift (min) | #1 share of best | top-5 same / ≤200 m |",
         "|---|---|---|---|---|---|---|---|---|---|"]
for r in rows:
    lines.append(f"| {r['date']} | {r['window']} {r['win']} | {r['surface']} | {fmt(r['shift_all'])} | "
                 f"{r['shift_all'].get('share_ge5', 0):.1%} | {r['low_gain_all'].get('mean', 0):.1f} | "
                 f"{r['open_gained']} / {r['open_lost']} / {r['open_reach_asis']} | {r['top5_leave_shift']} | "
                 f"{r['top1_share_of_best']} | {r['top5_same_spot']} / {r['top5_within_200m']} |")
(OUT / f"results_walk{int(MAX_WALK)}.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
