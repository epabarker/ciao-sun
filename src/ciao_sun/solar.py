"""The reference solar model: NREL SPA plus one continuous refraction model.

`docs/solar-model.md` is the specification; the JS port must agree with this
module within 0.01 degrees. Terms follow `GLOSSARY.md`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pvlib

# Geometric elevation of the disc centre at Nominal sunrise and sunset, degrees.
NOMINAL_RISE_SET_ELEVATION_DEG = -0.833

# Fixed SPA inputs (docs/solar-model.md, "Geometric position").
DELTA_T_SECONDS = 67.0
OBSERVER_ALTITUDE_M = 0.0

# Refraction parameters (docs/solar-model.md, "Refraction").
REFRACTION_SCALE_ARCMIN = 1.02
REFRACTION_A_DEG2 = 10.3
REFRACTION_B_DEG = 5.11
# Where the formula's refraction peaks; below it the refraction is held constant.
REFRACTION_FLOOR_DEG = math.sqrt(REFRACTION_A_DEG2) - REFRACTION_B_DEG


@dataclass(frozen=True)
class SunTrack:
    """One local day of sun positions at 1 min steps, with the day's three events."""

    times: pd.DatetimeIndex
    azimuth: np.ndarray  # true azimuth, degrees clockwise from true north
    elevation: np.ndarray  # geometric elevation of the disc centre, degrees
    apparent_elevation: np.ndarray  # elevation + refraction, degrees
    nominal_sunrise: pd.Timestamp | None  # None when the centre never crosses up that day
    nominal_sunset: pd.Timestamp | None  # None when the centre never crosses down that day
    solar_noon: pd.Timestamp


def refraction_deg(elevation_deg: np.ndarray) -> np.ndarray:
    """Refraction to add to a geometric elevation, in degrees.

    Continuous and smooth at every elevation: there is no switch-on level.
    """
    h = np.maximum(np.asarray(elevation_deg, dtype=float), REFRACTION_FLOOR_DEG)
    argument_deg = h + REFRACTION_A_DEG2 / (h + REFRACTION_B_DEG)
    arcmin: np.ndarray = REFRACTION_SCALE_ARCMIN / np.tan(np.radians(argument_deg))
    return arcmin / 60.0


def sun_track(lat: float, lon: float, date: str, tz: str = "Europe/London") -> SunTrack:
    """The sun track for the local day `date` (YYYY-MM-DD) at a place."""
    times = pd.date_range(f"{date} 00:00", f"{date} 23:59", freq="1min", tz=tz)
    position = pvlib.solarposition.spa_python(
        times, lat, lon, altitude=OBSERVER_ALTITUDE_M, delta_t=DELTA_T_SECONDS, how="numpy"
    )
    azimuth = position["azimuth"].to_numpy()
    elevation = position["elevation"].to_numpy()

    above = elevation - NOMINAL_RISE_SET_ELEVATION_DEG
    rises = _crossing_minutes(above)
    sets = _crossing_minutes(-above)
    # sin(azimuth) falls through zero only at the upper transit, in either hemisphere.
    transits = _crossing_minutes(-np.sin(np.radians(azimuth)))
    if not transits:
        raise ValueError(f"No solar noon on {date} at {lat},{lon}.")

    return SunTrack(
        times=times,
        azimuth=azimuth,
        elevation=elevation,
        apparent_elevation=elevation + refraction_deg(elevation),
        nominal_sunrise=times[rises[0]] if rises else None,
        nominal_sunset=times[sets[-1]] if sets else None,
        solar_noon=times[transits[0]],
    )


def _crossing_minutes(value: np.ndarray) -> list[int]:
    """Indexes of the samples nearest each upward zero crossing of `value`.

    The crossing is placed by linear interpolation between the two samples
    that bracket it, then rounded half up to a whole sample.
    """
    before, after = value[:-1], value[1:]
    nearest = []
    for i in np.flatnonzero((before < 0.0) & (after >= 0.0)):
        fraction = -before[i] / (after[i] - before[i])
        nearest.append(int(i) + math.floor(fraction + 0.5))
    return nearest
