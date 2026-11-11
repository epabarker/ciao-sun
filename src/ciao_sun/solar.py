"""Sunrise detection and sun-track generation via pvlib.

Sunrise here is defined as the first minute of the day where the sun's apparent
(refraction-corrected) elevation exceeds -0.833 degrees -- the standard flat-
horizon definition used by almanacs. This is *not* the actual local sunrise at
an obstructed site, which will generally be later. Ciao Sun answers "where can I
see the sun during the hour after nominal sunrise", not "when does the sun
appear at this exact spot".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pvlib

SUNRISE_APPARENT_ELEVATION_DEG = -0.833


@dataclass(frozen=True)
class SunTrack:
    times: pd.DatetimeIndex
    azimuth: np.ndarray
    apparent_elevation: np.ndarray
    sunrise: pd.Timestamp


def find_sunrise(lat: float, lon: float, date: str, tz: str = "Europe/London") -> pd.Timestamp:
    """The first minute of `date` where apparent elevation exceeds -0.833 degrees."""
    day = pd.date_range(f"{date} 00:00", f"{date} 23:59", freq="1min", tz=tz)
    sp = pvlib.solarposition.get_solarposition(day, lat, lon)
    above = sp.index[sp["apparent_elevation"] > SUNRISE_APPARENT_ELEVATION_DEG]
    if len(above) == 0:
        raise ValueError(f"The sun never rises on {date} at {lat},{lon}.")
    return above[0]


def sunrise_hour_track(
    lat: float,
    lon: float,
    date: str,
    tz: str = "Europe/London",
    step_minutes: float = 5.0,
    window_minutes: float = 60.0,
) -> SunTrack:
    """Azimuth and apparent elevation across the window after nominal sunrise."""
    sunrise = find_sunrise(lat, lon, date, tz)
    window = pd.date_range(
        sunrise,
        sunrise + pd.Timedelta(minutes=window_minutes),
        freq=pd.Timedelta(minutes=step_minutes),
        tz=tz,
    )
    sp = pvlib.solarposition.get_solarposition(window, lat, lon)
    return SunTrack(
        times=window,
        azimuth=sp["azimuth"].to_numpy(),
        apparent_elevation=sp["apparent_elevation"].to_numpy(),
        sunrise=sunrise,
    )


def horizon_profile_track(
    lat: float, lon: float, date: str, tz: str = "Europe/London"
) -> pd.DataFrame:
    """Full-day solar position at 1-minute resolution, for the --profile-only plot."""
    day = pd.date_range(f"{date} 00:00", f"{date} 23:59", freq="1min", tz=tz)
    return pvlib.solarposition.get_solarposition(day, lat, lon)
