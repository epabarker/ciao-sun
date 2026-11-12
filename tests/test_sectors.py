"""Each window's sector of Horizon profile samples, from the coverage's latitudes (#62)."""

from __future__ import annotations

import numpy as np
import pytest

from ciao_sun.sectors import window_sectors
from ciao_sun.solar import sun_track
from ciao_sun.tile_codec import PROFILE_SAMPLES

BRISTOL = (51.40, 51.55, -2.59)  # south, north, longitude


def _degrees(sector) -> tuple[float, float]:
    return sector.first * 0.25, ((sector.first + sector.samples - 1) % PROFILE_SAMPLES) * 0.25


def test_bristols_morning_runs_from_before_the_earliest_sunrise_to_past_solar_noon():
    sectors = window_sectors(*BRISTOL)

    start, end = _degrees(sectors["morning"])
    assert start == pytest.approx(36, abs=1.5)
    assert end == pytest.approx(190, abs=1.5)


def test_bristols_evening_runs_from_before_solar_noon_to_past_the_latest_sunset():
    sectors = window_sectors(*BRISTOL)

    start, end = _degrees(sectors["evening"])
    assert start == pytest.approx(170, abs=1.5)
    assert end == pytest.approx(324, abs=1.5)


def test_a_coverage_further_north_widens_both_sectors():
    bristol, edinburgh = window_sectors(*BRISTOL), window_sectors(55.9, 56.0, -3.2)

    for window in ("morning", "evening"):
        assert edinburgh[window].samples > bristol[window].samples


@pytest.mark.parametrize("date", ["2026-06-21", "2026-12-21", "2026-03-20", "2027-06-21"])
@pytest.mark.parametrize("lat", [51.40, 51.55])
def test_every_sun_azimuth_a_window_can_read_lies_in_its_sector_with_room_to_spare(date, lat):
    # The scorer reads the sample below the sun and the one after it, and Sky
    # openness reads 10 deg either side of the sun's path.
    sectors = window_sectors(*BRISTOL)
    track = sun_track(lat, BRISTOL[2], date)
    up = track.apparent_elevation >= -2.0
    noon = int(np.argmax(track.apparent_elevation))
    minutes = np.arange(len(track.azimuth))
    for window, part in (("morning", up & (minutes < noon)), ("evening", up & (minutes >= noon))):
        held = set(sectors[window].indexes().tolist())
        for az in track.azimuth[part]:
            for edge in (az - 10.0, az + 10.0):
                below = int(np.floor(edge * 4)) % PROFILE_SAMPLES
                assert {below, (below + 1) % PROFILE_SAMPLES} <= held, (window, az)
