"""A window's answer needs only its own sector of each Horizon profile (#62).

The morning and evening tiles of a build hold only the samples their window
can read (`ciao_sun.sectors`). Reading any other sample of a decoded tile
fails, so each answer below, read from sector tiles, proves the scorer never
looked outside the sector, and its equality with the full-circle answer that
nothing it reads was lost.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ciao_sun.reference import answer
from ciao_sun.sectors import window_sectors
from ciao_sun.tile_codec import Tile

from .reference_worlds import (
    ORIGIN_LAT,
    ORIGIN_LON,
    Stand,
    build,
    evening,
    horizon,
    morning,
    street_tile,
)

STANDS = [
    Stand(-400, "Roof Row", horizon(ridges=((225.0, 359.75, 40.0),))),
    Stand(-200, "East Wall", horizon(ridges=((80.0, 140.0, 12.0),))),
    Stand(200, "Hilltop Road", horizon(-1.2)),
    Stand(400, "Plain Street"),
]


def _tiles(directory: Path, window: str | None) -> list[Tile]:
    tile = street_tile(STANDS)
    if window is not None:
        tile = replace(tile, sector=window_sectors(ORIGIN_LAT, ORIGIN_LAT, ORIGIN_LON)[window])
    return build(directory / (window or "whole"), tile)


QUERIES = [
    morning(wake_time="07:00"),
    morning(wake_time="10:30"),
    morning(wake_time="05:00", date="2026-06-21"),
    morning(wake_time="11:00", date="2026-06-21"),
    morning(wake_time="06:00", date="2026-03-20", sky="partly"),
    evening(wake_time="07:00"),
    evening(wake_time="05:00", date="2026-06-21"),
    evening(wake_time="12:00", date="2026-09-23"),
]


@pytest.mark.parametrize("query", QUERIES, ids=lambda q: f"{q.window}-{q.date}-{q.wake_time}")
def test_an_answer_read_from_its_windows_sector_is_the_full_circle_answer(tmp_path, query):
    whole = answer(query, _tiles(tmp_path, None))
    sector = answer(query, _tiles(tmp_path, query.window))

    assert sector.to_json() == whole.to_json()


def test_the_morning_window_ends_at_solar_noon_when_wake_time_plus_3_h_is_later(tmp_path):
    result = answer(morning(wake_time="10:30"), _tiles(tmp_path, None))

    assert result.window is not None
    assert result.solar_noon == "2026-12-21T12:08:00+00:00"
    assert result.window.end == "2026-12-21T12:08:00+00:00"  # not 13:30
    assert result.window.axis_end == result.window.end


def test_a_morning_that_starts_after_solar_noon_has_no_daylight_left(tmp_path):
    result = answer(morning(wake_time="12:30"), _tiles(tmp_path, None))

    assert result.status == "lamp-only"
