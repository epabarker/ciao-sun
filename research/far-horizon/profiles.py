"""RESEARCH, throwaway. Near- and far-field Horizon profiles for open-ground Candidates near home.

Per Candidate and true azimuth (45-165 deg at 0.5 deg) it stores:
  near    : max angle 1-3000 m on the EA 1 m DSM, exactly as the prototype (ray_samples(3000)).
  t50[b]  : max angle in each distance band beyond 3 km on OS Terrain 50 (bilinear), to 200 km.
  dsm[b], dtm[b] : same bands, but 3-25 km on EA LIDAR (1 m local tiles, else 2 m far tiles)
            where BOTH DSM and DTM exist ("paired" coverage), else Terrain 50.
  dsmall[b] : 3-25 km on any EA LIDAR DSM tile we have (incl. ones without a DTM), else Terrain 50.
Azimuths are true (pvlib) azimuths, converted to grid azimuth with the BNG convergence at home.

    uv run python -I profiles.py <out.npz> [spacing_m]
"""

import sys
import time
from multiprocessing import get_context
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from farlib import FWD, MAIN, T50, grid_convergence, nanmax, ray_angles  # noqa: E402

from sunspot.horizon import horizon_angle, ray_samples  # noqa: E402
from sunspot.raster import find_tiles, load_mosaic, sample  # noqa: E402
from sunspot.search import candidate_grid  # noqa: E402

OUT = Path(sys.argv[1])
SPACING = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
LAT, LON = 51.4720, -2.6040
TICKET = (51.472184, -2.603139)  # street Candidate from the answer-screen prototype
RADIUS, EYE, NEAR = 1800.0, 1.6, 3000.0
AZ = np.arange(45.0, 165.0 + 1e-9, 0.5)
BANDS = np.array([3, 5, 7, 10, 15, 20, 25, 30, 50, 75, 100, 150, 200]) * 1000.0
LIDAR_MAX = 25000.0
D_FAR = np.concatenate([np.arange(3000, 10000, 25.0), np.arange(10000, 30000, 50.0),
                        np.arange(30000, 200000, 200.0)])
D_LID = D_FAR[D_FAR < LIDAR_MAX]
BAND_IDX = np.digitize(D_FAR, BANDS) - 1  # band b covers [BANDS[b], BANDS[b+1])
NB = len(BANDS) - 1

hx, hy = FWD.transform(LON, LAT)
CONV = grid_convergence(LON, LAT)
t50 = T50()
dsm1 = load_mosaic(find_tiles(MAIN / "data/dsm"))
dtm1 = load_mosaic(find_tiles(MAIN / "data/dtm"))
dsm2 = load_mosaic(find_tiles(MAIN / "data/farfield/ea2m/tif/dsm"))
dtm2 = load_mosaic(find_tiles(MAIN / "data/farfield/ea2m/tif/dtm"))


def lidar_sampler(kind):
    def f(x, y):
        a1 = sample(dsm1, x, y)
        b1 = sample(dtm1, x, y)
        a2 = sample(dsm2, x, y)
        b2 = sample(dtm2, x, y)
        paired1 = np.isfinite(a1) & np.isfinite(b1)
        paired2 = np.isfinite(a2) & np.isfinite(b2) & ~paired1
        out = t50.sample(x, y)
        if kind == "dsmall":
            any2 = np.isfinite(a2) & ~np.isfinite(a1)
            out[np.isfinite(a1)] = a1[np.isfinite(a1)]
            out[any2] = a2[any2]
            return out
        src1, src2 = (a1, a2) if kind == "dsm" else (b1, b2)
        out[paired1] = src1[paired1]
        out[paired2] = src2[paired2]
        return out
    return f


SAMPLERS = {k: lidar_sampler(k) for k in ("dsm", "dtm", "dsmall")}

# Candidates: open ground (DSM - DTM <= 1 m), as in the prototype, plus the ticket Candidate.
gx, gy, _ = candidate_grid(hx, hy, RADIUS, SPACING)
g, s = sample(dtm1, gx, gy), sample(dsm1, gx, gy)
keep = np.isfinite(g) & np.isfinite(s) & ((s - g) <= 1.0)
tx, ty = FWD.transform(TICKET[1], TICKET[0])
gx = np.concatenate([[tx], gx[keep]])
gy = np.concatenate([[ty], gy[keep]])
gz = sample(dtm1, gx, gy) + EYE
N = len(gx)
RAY = ray_samples(NEAR)


def band_max(ang, d_idx):
    out = np.full((ang.shape[0], NB), np.nan, np.float32)
    for b in range(NB):
        m = d_idx == b
        if m.any():
            out[:, b] = nanmax(ang[:, m], axis=1)
    return out


def one_az(j):
    az_g = AZ[j] - CONV
    res = {"near": np.empty(N, np.float32), "t50": np.empty((N, NB), np.float32)}
    for k in SAMPLERS:
        res[k] = np.empty((N, NB), np.float32)
    for st in range(0, N, 1500):
        sl = slice(st, st + 1500)
        px, py, pz = gx[sl], gy[sl], gz[sl]
        res["near"][sl] = horizon_angle(dsm1, px, py, pz, az_g, RAY, curvature=True)
        ang = ray_angles(t50.sample, px, py, pz, az_g, D_FAR)
        bm = band_max(ang, BAND_IDX)
        res["t50"][sl] = bm
        for k, f in SAMPLERS.items():
            al = ray_angles(f, px, py, pz, az_g, D_LID)
            bl = band_max(al, BAND_IDX[: len(D_LID)])
            nl = int(np.searchsorted(BANDS, LIDAR_MAX))  # bands fully inside 3-25 km
            res[k][sl] = np.concatenate([bl[:, :nl], bm[:, nl:]], axis=1)
    return j, res


if __name__ == "__main__":
    t0 = time.perf_counter()
    print("candidates", N, "azimuths", len(AZ), "convergence", round(CONV, 3))
    out = {"near": np.empty((N, len(AZ)), np.float32)}
    for k in ("t50", *SAMPLERS):
        out[k] = np.empty((N, len(AZ), NB), np.float32)
    with get_context("fork").Pool(8) as pool:
        for n, (j, r) in enumerate(pool.imap_unordered(one_az, range(len(AZ)))):
            for k, v in r.items():
                out[k][:, j] = v
            if n % 40 == 0:
                print(n, f"{time.perf_counter() - t0:.0f}s", flush=True)
    np.savez_compressed(OUT, x=gx, y=gy, z=gz, az=AZ, bands=BANDS, conv=CONV, **out)
    print("wrote", OUT, f"{time.perf_counter() - t0:.0f}s")
