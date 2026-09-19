"""Solar position correctness: HANDOFF.md #6, test group 6.

Reference values are altitude/azimuth of the Sun for Bristol (51.4720N,
2.6040W), fetched 2026-09-19 from the US Naval Observatory Astronomical
Applications Department's Altitude/Azimuth data service:
https://aa.usno.navy.mil/calculated/altaz?body=10&date=<date>&intv_mag=5&
lat=51.4720&lon=-2.6040&label=Bristol&tz=0&tz_sign=-1
(time zone fixed to UTC to avoid GMT/BST ambiguity; table values are rounded
to 0.1 degree by the service).
"""

from __future__ import annotations

import pandas as pd
import pvlib
import pytest

LAT, LON = 51.4720, -2.6040

# (UTC timestamp, expected apparent altitude deg, expected azimuth deg E of N)
USNO_REFERENCE = [
    ("2026-12-21 08:15", -0.1, 128.6),
    ("2026-12-21 08:45", 3.1, 134.6),
    ("2026-12-21 09:15", 6.1, 140.7),
    ("2026-06-21 04:00", 0.5, 50.3),
    ("2026-06-21 04:30", 3.9, 56.1),
    ("2026-06-21 05:00", 7.8, 61.7),
]


@pytest.mark.parametrize("ts,expected_alt,expected_az", USNO_REFERENCE)
def test_solar_position_matches_usno(ts, expected_alt, expected_az):
    when = pd.DatetimeIndex([pd.Timestamp(ts, tz="UTC")])
    sp = pvlib.solarposition.get_solarposition(when, LAT, LON)
    assert sp["apparent_elevation"].iloc[0] == pytest.approx(expected_alt, abs=0.2)
    assert sp["azimuth"].iloc[0] == pytest.approx(expected_az, abs=0.2)


def test_find_sunrise_matches_usno_rise_time():
    """USNO's rise time for 2026-12-21 (tz=0) is 08:13, and its own definition
    (upper limb, standard refraction) is the same -0.833 degree apparent-elevation
    convention sunspot uses, so this is a valid independent cross-check on time.
    """
    from sunspot.solar import find_sunrise

    sunrise = find_sunrise(LAT, LON, "2026-12-21", tz="UTC")
    expected = pd.Timestamp("2026-12-21 08:13", tz="UTC")
    assert abs((sunrise - expected).total_seconds()) <= 120
