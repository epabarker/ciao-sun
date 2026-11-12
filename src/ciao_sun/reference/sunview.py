"""Sun in view and Sky openness: a sun track against Horizon profiles."""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from ciao_sun.solar import SunTrack
from ciao_sun.tile_codec import CODE_COUNT, PROFILE_SAMPLES, STORAGE_MIN_DEG, codes_to_degrees

LOW_SUN_MIN_DEG = 0.0
LOW_SUN_MAX_DEG = 30.0
OPENNESS_SECTOR_MARGIN_DEG = 10.0
OPENNESS_CUTOFF = 0.75

_SAMPLES_PER_DEG = PROFILE_SAMPLES / 360.0
_DEGREES_OF_CODE = codes_to_degrees(np.arange(CODE_COUNT))
# What one profile sample adds to the sector's Sky openness: cos^2(max(h, 0)).
_OPEN_SKY_OF_CODE = np.cos(np.radians(np.maximum(_DEGREES_OF_CODE, 0.0))) ** 2


def horizon_at_sun(
    profile_codes: npt.NDArray[np.uint8], track: SunTrack, start: int, end: int
) -> npt.NDArray[np.float64]:
    """The Horizon profile at the sun's true azimuth, in degrees, per Candidate
    (rows) and minute from `start` to `end`: interpolated linearly between the
    two neighbouring samples."""
    position = (track.azimuth[start:end] % 360.0) * _SAMPLES_PER_DEG
    below = np.floor(position).astype(np.int64)
    fraction = position - below
    before = _DEGREES_OF_CODE[profile_codes[:, below % PROFILE_SAMPLES]]
    after = _DEGREES_OF_CODE[profile_codes[:, (below + 1) % PROFILE_SAMPLES]]
    horizon: npt.NDArray[np.float64] = before * (1.0 - fraction) + after * fraction
    return horizon


def sun_in_view(
    profile_codes: npt.NDArray[np.uint8], track: SunTrack, start: int, end: int
) -> npt.NDArray[np.bool_]:
    """Whether the sun is in view, per Candidate (rows) and minute from `start` to `end`.

    In view means the apparent elevation of the disc centre exceeds the
    Horizon profile at the sun's true azimuth (`horizon_at_sun`). A profile
    below 0 degrees is used as it is.
    """
    horizon = horizon_at_sun(profile_codes, track, start, end)
    in_view: npt.NDArray[np.bool_] = track.apparent_elevation[start:end] > horizon
    return in_view


def last_sun(profile_codes: npt.NDArray[np.uint8], track: SunTrack) -> int | None:
    """One Candidate's Last sun: the last minute after solar noon with the sun in view.

    It is looked for over the whole afternoon, not only a window, so it can
    fall after Nominal sunset where the Horizon profile is below 0 degrees,
    but only while the sun stands at -2 degrees or higher: no Horizon profile
    is lower, so the sun is never in view below it. That keeps the search in
    the evening tiles' sector (#62). None when the sun is never in view.
    """
    start = int(np.argmax(track.apparent_elevation))
    still_up = track.apparent_elevation[start:] >= STORAGE_MIN_DEG
    end = start + (int(np.argmin(still_up)) if not still_up.all() else still_up.size)
    in_view = sun_in_view(profile_codes[np.newaxis, :], track, start, end)
    minutes = np.flatnonzero(in_view)
    return start + int(minutes[-1]) if minutes.size else None


def low_sun(track: SunTrack, start: int, end: int) -> npt.NDArray[np.bool_]:
    """Whether the sun's apparent elevation is 0-30 degrees (both included), per minute."""
    elevation = track.apparent_elevation[start:end]
    low: npt.NDArray[np.bool_] = (elevation >= LOW_SUN_MIN_DEG) & (elevation <= LOW_SUN_MAX_DEG)
    return low


def sky_openness(
    profile_codes: npt.NDArray[np.uint8], track: SunTrack, start: int, end: int
) -> npt.NDArray[np.float64]:
    """Sky openness per Candidate, over the sun path's sector.

    The sector runs from the least to the greatest true azimuth of the sun
    over the minutes `start` to `end`, widened by 10 degrees each side. It
    is the mean of cos^2(max(h, 0)) over the profile samples whose
    azimuth lies in the sector, ends included.
    """
    path = track.azimuth[start:end]
    first = math.ceil((float(path.min()) - OPENNESS_SECTOR_MARGIN_DEG) * _SAMPLES_PER_DEG)
    last = math.floor((float(path.max()) + OPENNESS_SECTOR_MARGIN_DEG) * _SAMPLES_PER_DEG)
    sector = np.arange(first, last + 1) % PROFILE_SAMPLES
    openness: npt.NDArray[np.float64] = _OPEN_SKY_OF_CODE[profile_codes[:, sector]].mean(axis=1)
    return openness


def runs(mask: npt.NDArray[np.bool_]) -> list[tuple[int, int]]:
    """The runs of True in `mask` as (first index, index after the last)."""
    padded = np.concatenate(([False], mask, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return [(int(a), int(b)) for a, b in zip(edges[::2], edges[1::2], strict=True)]
