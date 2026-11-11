"""The two checks that fail a build, and the tolerances they pass at.

**Direct-ray profile check.** For a sample of each tile's Candidates, the
Horizon profile decoded from the written tile is compared with rays cast
directly from that Candidate: near-field rays over the obstruction surface, and
far-field rays over Terrain 50 from the Candidate itself, not from the 100 m
lattice the precompute uses. A Candidate fails when fewer than 99% of its 1,440
samples agree within the storage code's half step plus 0.05 deg.

- The half step is 0.05 deg up to 10 deg and 0.25 deg above (the storage code
  is within 0.2 min of a linear 0.1 deg code on first sun, #6).
- 0.05 deg covers the far-field lattice (p99 0.035 deg at 100 m, #6) and the
  far field's sparser sampling beyond 10 km (p99 0.014 deg).
- 99%, because those are p99 figures: where the Horizon profile steps at a
  far ridge, a Candidate up to 71 m from its lattice point legitimately sees
  the step a sample or two to one side.

The direct rays use the tile's one meridian convergence, as the precompute
does, so the near field agrees exactly. A profile cast along grid north instead
of true north is turned by about 0.5 deg in Bristol (two samples), and fails
wherever the Horizon profile has more than a handful of edges.

**Water guard.** There is no water mask (ADR 0003). Instead the build counts
the Candidates whose merged horizon is set, at any azimuth, by a cell inside an
OSM water area, and fails above zero. The count comes from the precompute
itself (`horizon_precompute.cast_tile`), so it covers every Candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from ciao_sun.candidates import CANDIDATE_SPACING_M
from ciao_sun.crs import WGS84_TO_BNG
from ciao_sun.horizon import (
    curvature_drop,
    grid_azimuth,
    horizon_angle,
    meridian_convergence,
    ray_samples,
)
from ciao_sun.horizon_precompute import EYE_HEIGHT_M, NEAR_REACH_M, PROFILE_AZIMUTHS_DEG
from ciao_sun.raster import RasterGrid, sample, sample_bilinear
from ciao_sun.tile_codec import (
    FINE_TOP_DEG,
    PROFILE_SAMPLES,
    STORAGE_MAX_DEG,
    STORAGE_MIN_DEG,
    Tile,
    codes_to_degrees,
)

_FAR_STEP_M = 50.0


class BuildCheckError(Exception):
    """A build check failed; the build must not ship."""


@dataclass(frozen=True)
class Tolerances:
    """What the build checks allow. The manifest records the values a build passed at."""

    # Direct-ray check: Candidates sampled per tile, spread evenly through it.
    candidates_per_tile: int = 16
    # Allowed difference from a direct ray, on top of the storage code's half step.
    profile_tolerance_deg: float = 0.05
    # The share of a Candidate's 1,440 samples that must be within it.
    profile_fraction_within: float = 0.99
    fine_half_step_deg: float = 0.05
    coarse_half_step_deg: float = 0.25
    # Water guard: Candidates whose horizon a water cell may set.
    water_candidates_allowed: int = 0

    def as_manifest(self) -> dict[str, dict[str, Any]]:
        return {
            "profile": {
                "candidatesPerTile": self.candidates_per_tile,
                "toleranceDeg": self.profile_tolerance_deg,
                "storageHalfStepDeg": {
                    "upTo10Deg": self.fine_half_step_deg,
                    "above10Deg": self.coarse_half_step_deg,
                },
                "fractionWithin": self.profile_fraction_within,
            },
            "waterGuard": {"candidatesAllowed": self.water_candidates_allowed},
        }


@dataclass(frozen=True)
class ProfileCheck:
    """One tile's direct-ray check: how many Candidates were cast, and each failure in words."""

    candidates_checked: int
    failures: tuple[str, ...]


def candidate_positions(tile: Tile) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """A tile's Candidates in National Grid metres, back on their 10 m lattice."""
    x, y = WGS84_TO_BNG.transform(tile.candidates.lon_e7 / 1e7, tile.candidates.lat_e7 / 1e7)
    return (
        np.round(np.asarray(x, dtype=np.float64) / CANDIDATE_SPACING_M) * CANDIDATE_SPACING_M,
        np.round(np.asarray(y, dtype=np.float64) / CANDIDATE_SPACING_M) * CANDIDATE_SPACING_M,
    )


def _direct_far(
    terrain50: RasterGrid,
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    eye: npt.NDArray[np.float64],
    true_azimuth: float,
    convergence: float,
    far_reach_m: float,
) -> npt.NDArray[np.float64]:
    d = np.arange(NEAR_REACH_M, far_reach_m, _FAR_STEP_M)
    theta = np.radians(grid_azimuth(true_azimuth, convergence))
    xs = x[:, None] + d[None, :] * np.sin(theta)
    ys = y[:, None] + d[None, :] * np.cos(theta)
    zs = sample_bilinear(terrain50, xs.ravel(), ys.ravel()).reshape(xs.shape)
    angle = np.degrees(np.arctan2(zs - eye[:, None] - curvature_drop(d)[None, :], d[None, :]))
    return np.asarray(np.where(np.isnan(angle), -np.inf, angle).max(axis=1), dtype=np.float64)


def check_tile_profiles(
    tile: Tile,
    surface: RasterGrid,
    dtm: RasterGrid,
    terrain50: RasterGrid,
    *,
    far_reach_m: float,
    tolerances: Tolerances,
) -> ProfileCheck:
    """Compare a decoded tile's Horizon profiles with direct ray casting at a sample of Candidates.

    `surface`, `dtm` and `terrain50` are what the tile was cast from.
    """
    count = len(tile.candidates.lat_e7)
    if count == 0:
        return ProfileCheck(0, ())
    all_x, all_y = candidate_positions(tile)
    # The tile's one convergence, worked out here and not taken from the precompute.
    convergence = meridian_convergence(float(all_x.mean()), float(all_y.mean()))
    chosen = np.unique(
        np.linspace(0, count - 1, min(count, tolerances.candidates_per_tile)).round().astype(int)
    )
    x, y = all_x[chosen], all_y[chosen]
    eye = sample(dtm, x, y).astype(np.float64) + EYE_HEIGHT_M

    ray_d = ray_samples(NEAR_REACH_M)
    direct = np.empty((len(chosen), PROFILE_SAMPLES), dtype=np.float64)
    for i, azimuth in enumerate(PROFILE_AZIMUTHS_DEG):
        near = horizon_angle(surface, x, y, eye, float(azimuth), ray_d, convergence_deg=convergence)
        far = _direct_far(terrain50, x, y, eye, float(azimuth), convergence, far_reach_m)
        direct[:, i] = np.fmax(near, far)
    # NaN: no ground under the Candidate, or no surface along a whole ray.
    direct = np.clip(direct, STORAGE_MIN_DEG, STORAGE_MAX_DEG)

    stored = codes_to_degrees(tile.candidates.profile_codes[chosen])
    half_step = np.where(
        np.fmax(stored, direct) > FINE_TOP_DEG,
        tolerances.coarse_half_step_deg,
        tolerances.fine_half_step_deg,
    )
    difference = np.abs(stored - direct)
    with np.errstate(invalid="ignore"):
        # 1e-9: float noise on a difference that is exactly the half step.
        within = difference <= half_step + tolerances.profile_tolerance_deg + 1e-9

    failures = []
    for row, candidate in enumerate(chosen.tolist()):
        fraction = float(within[row].mean())
        if fraction >= tolerances.profile_fraction_within:
            continue
        off = np.where(within[row], -1.0, np.nan_to_num(difference[row], nan=np.inf))
        worst = int(off.argmax())
        failures.append(
            f"{tile.grid_ref} Candidate {candidate}: {int((~within[row]).sum())} of "
            f"{PROFILE_SAMPLES} profile samples disagree with direct ray casting "
            f"(worst at true azimuth {PROFILE_AZIMUTHS_DEG[worst]:g} deg: tile "
            f"{stored[row, worst]:.2f} deg, direct ray {direct[row, worst]:.2f} deg)"
        )
    return ProfileCheck(len(chosen), tuple(failures))
