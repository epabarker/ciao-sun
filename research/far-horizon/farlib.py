"""RESEARCH, throwaway. Shared helpers for the far-horizon measurements."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
from pyproj import CRS, Proj, Transformer

from sunspot.horizon import R_EFF

MAIN = Path("/Volumes/veracrypt-volume/github-repos/daylight-viewing")
T50_NPY = MAIN / "data/farfield/terr50/gb_terr50_dm.npy"
T50_CELL, T50_Y1 = 50.0, 1_300_000.0

FWD = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
INV = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
_BNG = Proj(CRS.from_epsg(27700))


def grid_convergence(lon: float, lat: float) -> float:
    """Meridian convergence (deg): grid azimuth = true azimuth - convergence."""
    return float(_BNG.get_factors(lon, lat).meridian_convergence)


def true_to_grid(az_true, lon, lat):
    return np.asarray(az_true) - grid_convergence(lon, lat)


class T50:
    """OS Terrain 50 GB mosaic (int16 decimetres), bilinear sampling, NaN off-grid/nodata.

    Values are cell-centre heights: cell (r, c) centre = (25 + 50c, Y1 - 25 - 50r).
    Sea cells hold real values (~0 or slightly negative), so nodata only occurs off-grid.
    """

    def __init__(self, path: Path = T50_NPY):
        self.a = np.load(path, mmap_mode="r")

    def sample(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype="float64")
        y = np.asarray(y, dtype="float64")
        cf = x / T50_CELL - 0.5
        rf = (T50_Y1 - y) / T50_CELL - 0.5
        c0 = np.floor(cf).astype(np.int64)
        r0 = np.floor(rf).astype(np.int64)
        fx = (cf - c0).astype("float32")
        fy = (rf - r0).astype("float32")
        nr, nc = self.a.shape
        ok = (r0 >= 0) & (r0 < nr - 1) & (c0 >= 0) & (c0 < nc - 1)
        out = np.full(x.shape, np.nan, dtype="float32")
        r, c = r0[ok], c0[ok]
        v00 = self.a[r, c].astype("float32")
        v01 = self.a[r, c + 1].astype("float32")
        v10 = self.a[r + 1, c].astype("float32")
        v11 = self.a[r + 1, c + 1].astype("float32")
        stack = np.stack([v00, v01, v10, v11])
        bad = (stack <= -32768).any(axis=0)
        fxo, fyo = fx[ok], fy[ok]
        v = (v00 * (1 - fxo) * (1 - fyo) + v01 * fxo * (1 - fyo)
             + v10 * (1 - fxo) * fyo + v11 * fxo * fyo) / 10.0
        v[bad] = np.nan
        out[ok] = v
        return out


def ray_angles(sampler, px, py, pz, az_grid_deg, d):
    """Obstruction angle (deg) at every sample distance d: shape (n_points, len(d))."""
    th = np.radians(az_grid_deg)
    xs = px[:, None] + d[None, :] * np.sin(th)
    ys = py[:, None] + d[None, :] * np.cos(th)
    z = sampler(xs.ravel(), ys.ravel()).reshape(xs.shape)
    rise = z - pz[:, None] - (d**2 / (2.0 * R_EFF))[None, :]
    return np.degrees(np.arctan2(rise, d[None, :]))


def nanmax(a, axis):
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN")
        return np.nanmax(a, axis=axis)
