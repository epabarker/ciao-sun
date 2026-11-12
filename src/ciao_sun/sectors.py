"""Which Horizon profile samples each window's tiles hold (#62).

A Morning query only ever reads the profile where the sun is between sunrise
and solar noon, and an Evening query (Last sun included) only where it is
between solar noon and sunset, so each window's tiles hold only that sector.
Over a year, at the coverage's southern and northern latitudes:

- the morning sector runs from the sun's least azimuth before solar noon to
  its greatest at solar noon;
- the evening sector runs from its least azimuth at solar noon to its
  greatest after it;

both counting only minutes when the sun stands at -2 deg or higher (the
storage code's floor: below it the sun is never in view), and both widened by
the 10 deg Sky openness reads either side of the sun's path, plus a sample for
the interpolation past the sun and a sample for the year-to-year wobble.
"""

from __future__ import annotations

import functools
import math
from datetime import date, timedelta

import numpy as np

from ciao_sun.reference.sunview import OPENNESS_SECTOR_MARGIN_DEG
from ciao_sun.solar import sun_track
from ciao_sun.tile_codec import PROFILE_SAMPLES, STORAGE_MIN_DEG, Sector

# The windows, each with its own tiles: `<build>/tiles/<window>/<grid ref>.bin`.
WINDOWS = ("morning", "evening")

_SAMPLES_PER_DEG = PROFILE_SAMPLES / 360.0
# One sample for the interpolation past the sun's azimuth, one for the
# difference between this year's sun and any other year's.
_SPARE_SAMPLES = 2
# Any year will do; the sun's azimuth extremes repeat to well within a sample.
_YEAR = 2026


def _azimuth_extremes(lat: float, lon: float) -> tuple[float, float, float, float]:
    """(least morning, greatest at noon, least at noon, greatest evening) azimuths over a year."""
    morning_min, noon_max, noon_min, evening_max = math.inf, -math.inf, math.inf, -math.inf
    day = date(_YEAR, 1, 1)
    while day.year == _YEAR:
        track = sun_track(lat, lon, day.isoformat())
        up = track.apparent_elevation >= STORAGE_MIN_DEG
        noon = int(np.argmax(track.apparent_elevation))
        before, after = up.copy(), up.copy()
        before[noon:] = False
        after[:noon] = False
        morning_min = min(morning_min, float(track.azimuth[before].min()))
        evening_max = max(evening_max, float(track.azimuth[after].max()))
        noon_max = max(noon_max, float(track.azimuth[noon]))
        noon_min = min(noon_min, float(track.azimuth[noon]))
        day += timedelta(days=1)
    return morning_min, noon_max, noon_min, evening_max


def _sector(start_deg: float, end_deg: float) -> Sector:
    first = math.floor((start_deg - OPENNESS_SECTOR_MARGIN_DEG) * _SAMPLES_PER_DEG) - _SPARE_SAMPLES
    last = math.ceil((end_deg + OPENNESS_SECTOR_MARGIN_DEG) * _SAMPLES_PER_DEG) + _SPARE_SAMPLES
    return Sector(first % PROFILE_SAMPLES, min(last - first + 1, PROFILE_SAMPLES))


@functools.lru_cache(maxsize=8)
def window_sectors(south_lat: float, north_lat: float, lon: float) -> dict[str, Sector]:
    """The morning and evening sectors for a coverage between these latitudes."""
    extremes = [_azimuth_extremes(lat, lon) for lat in (south_lat, north_lat)]
    morning_min = min(e[0] for e in extremes)
    noon_max = max(e[1] for e in extremes)
    noon_min = min(e[2] for e in extremes)
    evening_max = max(e[3] for e in extremes)
    return {
        "morning": _sector(morning_min, noon_max),
        "evening": _sector(noon_min, evening_max),
    }
