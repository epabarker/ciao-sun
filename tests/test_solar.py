"""The reference solar model, through `ciao_sun.solar.sun_track`.

Reference values come from the US Naval Observatory Astronomical Applications
Department, an implementation independent of NREL SPA:

- Altitude/azimuth of the Sun for 51.4720N, 2.6040W, fetched 2026-09-19 from
  https://aa.usno.navy.mil/calculated/altaz (tz=0; rounded to 0.1 degree by
  the service).
- Rise, set and upper transit for Bristol (51.45N, 2.60W), fetched 2026-11-11
  from https://aa.usno.navy.mil/api/rstt/oneday?date=<date>&coords=51.45,-2.60&tz=0
  (rounded to the minute by the service).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pvlib
import pytest

from ciao_sun.solar import refraction_deg, sun_track

LAT, LON = 51.4720, -2.6040
BRISTOL = (51.45, -2.60)

SOLSTICES_AND_EQUINOXES = ["2026-03-20", "2026-06-21", "2026-09-23", "2026-12-21"]


@pytest.mark.parametrize("date", SOLSTICES_AND_EQUINOXES)
def test_apparent_elevation_is_continuous_through_the_horizon(date):
    """Refraction grows as the sun sinks, so it can only compress the track:
    no minute-to-minute step in apparent elevation may exceed the geometric
    step. pvlib's stepped refraction breaks this by over half a degree at
    -0.833 degrees.
    """
    track = sun_track(*BRISTOL, date, tz="UTC")

    assert len(track.times) == 1440
    assert track.times.freq == pd.Timedelta(minutes=1)
    # The day's track really does pass through both levels the criterion names.
    assert track.elevation.min() < -0.833 < 0.0 < track.elevation.max()

    geometric_step = np.abs(np.diff(track.elevation))
    apparent_step = np.abs(np.diff(track.apparent_elevation))
    assert np.all(apparent_step <= geometric_step + 1e-12)


# (date, rise, upper transit, set), UTC, from the USNO one-day service.
USNO_BRISTOL_ALMANAC = [
    ("2026-03-20", "06:13", "12:18", "18:23"),
    ("2026-06-21", "03:53", "12:12", "20:31"),
    ("2026-09-23", "05:58", "12:03", "18:07"),
    ("2026-12-21", "08:13", "12:08", "16:04"),
]


@pytest.mark.parametrize("date,rise,transit,sunset", USNO_BRISTOL_ALMANAC)
def test_nominal_sunrise_sunset_and_solar_noon_match_the_almanac_to_the_minute(
    date, rise, transit, sunset
):
    track = sun_track(*BRISTOL, date, tz="UTC")

    assert track.nominal_sunrise == pd.Timestamp(f"{date} {rise}", tz="UTC")
    assert track.solar_noon == pd.Timestamp(f"{date} {transit}", tz="UTC")
    assert track.nominal_sunset == pd.Timestamp(f"{date} {sunset}", tz="UTC")


def test_the_track_covers_the_local_day_in_the_requested_time_zone():
    track = sun_track(*BRISTOL, "2026-06-21", tz="Europe/London")

    assert track.times[0] == pd.Timestamp("2026-06-21 00:00", tz="Europe/London")
    assert track.times[-1] == pd.Timestamp("2026-06-21 23:59", tz="Europe/London")
    # 03:53 UTC, in British Summer Time.
    assert track.nominal_sunrise == pd.Timestamp("2026-06-21 04:53", tz="Europe/London")


# (UTC timestamp, expected apparent altitude deg, expected azimuth deg E of N)
USNO_ALTAZ = [
    ("2026-12-21 08:15", -0.1, 128.6),
    ("2026-12-21 08:45", 3.1, 134.6),
    ("2026-12-21 09:15", 6.1, 140.7),
    ("2026-06-21 04:00", 0.5, 50.3),
    ("2026-06-21 04:30", 3.9, 56.1),
    ("2026-06-21 05:00", 7.8, 61.7),
]


@pytest.mark.parametrize("ts,expected_alt,expected_az", USNO_ALTAZ)
def test_true_azimuth_and_apparent_elevation_match_usno(ts, expected_alt, expected_az):
    when = pd.Timestamp(ts, tz="UTC")
    track = sun_track(LAT, LON, when.strftime("%Y-%m-%d"), tz="UTC")
    i = track.times.get_loc(when)

    assert track.apparent_elevation[i] == pytest.approx(expected_alt, abs=0.1)
    assert track.azimuth[i] == pytest.approx(expected_az, abs=0.1)


def test_refraction_at_the_standard_horizon_is_about_34_arcminutes():
    """Almanacs take 34' of refraction for a sun whose centre appears on the
    horizon, which is how -0.833 degrees arises (34' + 16' semi-diameter)."""
    assert refraction_deg(np.array([-34.0 / 60.0]))[0] * 60.0 == pytest.approx(34.0, abs=0.5)


def test_refraction_has_no_switch_on_level_and_fades_towards_the_zenith():
    elevation = np.arange(-90.0, 90.0, 0.001)
    refraction = refraction_deg(elevation)

    # Smooth everywhere: 0.001 degrees of elevation never moves it by more.
    assert np.abs(np.diff(refraction)).max() < 0.001
    # More refraction the lower the sun, never less.
    assert np.all(np.diff(refraction) <= 0.0)
    assert abs(refraction[-1]) < 0.001


def test_refraction_matches_pvlib_spa_where_pvlib_applies_it():
    """Above its -0.833 degree switch, pvlib's SPA refraction at 1010 hPa and
    10 degrees C is the same formula, so the two must agree there."""
    times = pd.date_range("2026-12-21 08:15", "2026-12-21 16:00", freq="1min", tz="UTC")
    spa = pvlib.solarposition.spa_python(times, *BRISTOL, pressure=101000.0, temperature=10.0)
    track = sun_track(*BRISTOL, "2026-12-21", tz="UTC")
    ours = track.apparent_elevation[track.times.get_indexer(times)]

    assert np.abs(ours - spa["apparent_elevation"].to_numpy()).max() < 1e-9
