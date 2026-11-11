"""The reference scorer (#38): a Morning query gives a ranked Answer.

Every test builds a small synthetic world, writes it through the tile codec
and asserts only on the Answer that `ciao_sun.reference.answer` returns.

Expected values are worked out by hand from the spec's rules and from these
facts about the sun at the origin (51.45 N, 2.60 W), which come from the
reference solar model (`docs/solar-model.md`; the rise, set and transit
minutes are the US Naval Observatory's):

2026-12-21 (GMT): Nominal sunrise 08:13, solar noon 12:08, Nominal sunset 16:04.

    time   true azimuth   apparent elevation
    08:13     128.25          -0.25
    08:15     128.64          -0.05
    08:16     128.84           0.05
    09:00     137.61           4.66
    09:14     140.50           6.05
    09:15     140.70           6.15
    09:16     140.91           6.25
    09:59     150.10           9.99
    12:00                     15.15   (the day's highest is 15.2)

2026-06-21 (BST): Nominal sunrise 04:53.

    07:00      72.67          16.36
    08:26      88.64          29.51
    08:29      89.22          29.97
    08:30      89.41          30.13
    08:33      90.00          30.59
    10:00     108.76          43.91
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from ciao_sun.reference import Answer, Interval, Query, Spot, answer
from ciao_sun.tile_codec import Tile

from .reference_worlds import (
    WALL_DEG,
    Stand,
    build,
    horizon,
    lat_at,
    lon_at,
    morning,
    street,
    street_tile,
)

BST = {"date": "2026-06-21", "offset": "+01:00"}


def at(clock: str, date: str = "2026-12-21", offset: str = "+00:00") -> str:
    return f"{date}T{clock}:00{offset}"


def _by_name(result: Answer) -> dict[str, Spot]:
    return {spot.name: spot for spot in result.spots}


# --- Window bounds -----------------------------------------------------------


def test_morning_window_starts_at_nominal_sunrise_when_it_is_later_than_wake_time(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    result = answer(morning(wake_time="07:00"), tiles)

    assert result.status == "ranked"
    assert result.nominal_sunrise == at("08:13")
    assert result.solar_noon == at("12:08")
    assert result.nominal_sunset == at("16:04")
    assert result.window is not None
    assert result.window.start == at("08:13")
    # Three hours after waking, not three hours after sunrise.
    assert result.window.end == at("10:00")


def test_morning_window_starts_at_wake_time_when_the_sun_is_already_up(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    result = answer(morning(wake_time="09:00"), tiles)

    assert result.window is not None
    assert result.window.start == at("09:00")
    assert result.window.end == at("12:00")
    assert (result.window.axis_start, result.window.axis_end) == (at("09:00"), at("12:00"))


def test_morning_window_starts_at_now_when_now_is_later_on_the_query_date(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    today = answer(morning(wake_time="09:00", now="2026-12-21T09:30:00Z"), tiles)
    the_night_before = answer(morning(wake_time="09:00", now="2026-12-20T22:00:00Z"), tiles)

    assert today.window is not None and the_night_before.window is not None
    assert (today.window.start, today.window.end) == (at("09:30"), at("12:00"))
    assert the_night_before.window.start == at("09:00")


# --- Taper -------------------------------------------------------------------
# Wake time 09:00 at midwinter: the sun is up, in view from a flat plain and
# between 4.7 and 15.2 degrees for the whole window, so every minute is a
# low-sun minute and its weight is all that varies. Starting the window at
# `now` = Wake time + m drops the minutes before m.


def _low_sun_minutes_from(tiles: list[Tile], minutes_after_wake: int) -> float:
    now = pd.Timestamp("2026-12-21T09:00:00Z") + pd.Timedelta(minutes=minutes_after_wake)
    [spot] = answer(morning(wake_time="09:00", now=now.isoformat()), tiles).spots
    assert spot.sun_minutes == 180 - minutes_after_wake  # Sun minutes are never weighted
    return spot.low_sun_minutes


@pytest.mark.parametrize(
    "minutes_after_wake,weight",
    [(0, 1.0), (59, 1.0), (60, 1.0), (120, 0.5)],
)
def test_taper_weight_is_1_until_60_min_after_wake_time_and_a_half_at_120_min(
    tmp_path: Path, minutes_after_wake: int, weight: float
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    with_the_minute = _low_sun_minutes_from(tiles, minutes_after_wake)
    without_it = _low_sun_minutes_from(tiles, minutes_after_wake + 1)

    assert with_the_minute - without_it == pytest.approx(weight)


def test_taper_weight_falls_linearly_to_0_at_180_min_after_wake_time(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    # The last four minutes weigh 4/120, 3/120, 2/120 and 1/120: a line that
    # reaches 0 at 180 min, where the window ends.
    assert _low_sun_minutes_from(tiles, 176) == 0.08  # 10/120
    assert _low_sun_minutes_from(tiles, 179) == 0.01  # 1/120
    # The whole window: 60 at full weight, then (120 + 119 + ... + 1)/120 = 60.5.
    assert _low_sun_minutes_from(tiles, 0) == 120.5
    # From 120 min: (60 + 59 + ... + 1)/120.
    assert _low_sun_minutes_from(tiles, 120) == 15.25


# --- Sun in view -------------------------------------------------------------


def test_sun_minutes_count_every_minute_of_the_morning_window_with_the_sun_in_view(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    [spot] = answer(morning(wake_time="07:00"), tiles).spots

    # On a flat plain the sun clears 0 degrees at 08:16 and stays up.
    assert spot.sun_intervals == (Interval(at("08:16"), at("10:00")),)
    assert spot.sun_minutes == 104
    assert spot.name == "Plain Street"
    assert spot.candidate_id == "ST5873/0"


def test_sun_is_in_view_above_a_horizon_profile_that_lies_below_0_degrees(tmp_path: Path) -> None:
    tiles = street(
        tmp_path,
        [Stand(-400, "Hilltop Road", horizon(-2.0)), Stand(400, "Plain Street")],
    )

    spots = _by_name(answer(morning(wake_time="07:00"), tiles))

    # From the hilltop the sun (at -0.25 degrees) is already in view when the
    # window opens at Nominal sunrise; on the plain it is not until 08:16.
    assert spots["Hilltop Road"].sun_intervals == (Interval(at("08:13"), at("10:00")),)
    assert spots["Hilltop Road"].sun_minutes == 107
    assert spots["Plain Street"].sun_intervals == (Interval(at("08:16"), at("10:00")),)
    # A horizon below 0 degrees is no more open than a flat one.
    assert spots["Hilltop Road"].sky_openness == 1.0


def test_sun_is_hidden_until_it_clears_a_ridge_on_its_true_bearing(tmp_path: Path) -> None:
    # Both ridges cover true bearings 100 to 140.5 degrees; the Horizon profile
    # falls linearly to 0 between the samples at 140.5 and 140.75.
    tiles = street(
        tmp_path,
        [
            Stand(-400, "Low Ridge Lane", horizon(ridges=((100.0, 140.5, 10.0),))),
            Stand(400, "High Ridge Lane", horizon(ridges=((100.0, 140.5, 40.0),))),
        ],
    )

    spots = _by_name(answer(morning(wake_time="07:00"), tiles))

    # 09:14: the sun bears 140.50, behind either ridge. 09:15: it bears 140.70
    # at 6.15 degrees, where the low ridge has fallen to 10 x 0.18 = 1.8
    # degrees but the high one is still at 40 x 0.18 = 7.4. 09:16: it bears
    # 140.91, past both.
    assert spots["Low Ridge Lane"].sun_intervals == (Interval(at("09:15"), at("10:00")),)
    assert spots["High Ridge Lane"].sun_intervals == (Interval(at("09:16"), at("10:00")),)


def test_low_sun_minutes_count_only_sun_in_view_at_0_to_30_degrees(tmp_path: Path) -> None:
    tiles = street(
        tmp_path,
        [Stand(-400, "Hilltop Road", horizon(-2.0)), Stand(400, "Plain Street")],
    )

    winter = _by_name(answer(morning(wake_time="07:00"), tiles))
    summer = _by_name(answer(morning(date="2026-06-21", wake_time="07:00"), tiles))

    # Below 0 degrees: in view from the hilltop from 08:13, but not low sun until 08:16.
    assert winter["Hilltop Road"].low_sun_intervals == (Interval(at("08:16"), at("10:00")),)
    # 08:16-10:00 is minutes 76-179 after waking: (104 + 103 + ... + 1)/120.
    assert winter["Hilltop Road"].low_sun_minutes == 45.5
    # Above 30 degrees: the summer sun is in view all window but passes 30 degrees at 08:30.
    plain = summer["Plain Street"]
    assert plain.sun_intervals == (Interval(at("07:00", **BST), at("10:00", **BST)),)
    assert plain.low_sun_intervals == (Interval(at("07:00", **BST), at("08:30", **BST)),)
    assert plain.sun_minutes == 180
    # 60 min at full weight, then minutes 60-89: (120 + 119 + ... + 91)/120 = 26.375.
    assert plain.low_sun_minutes == 86.38


# --- Sky openness ------------------------------------------------------------


def test_sky_openness_is_taken_over_the_sun_path_widened_by_10_degrees(
    tmp_path: Path,
) -> None:
    # Wake time 07:00 at midwinter: the sun path runs from 128.25 (08:13) to
    # 150.10 degrees (09:59), so the sector is 118.25 to 160.10 degrees and
    # holds the 167 samples from 118.5 to 160.0.
    walled_outside_the_sector = horizon(ridges=((0.0, 118.0, WALL_DEG), (160.5, 359.75, WALL_DEG)))
    # Walls on 118.5-123.0 (19 samples) and 155.0-160.0 (21 samples): off the
    # sun path, but inside the widened sector.
    walled_inside_the_margins = horizon(ridges=((0.0, 123.0, WALL_DEG), (155.0, 359.75, WALL_DEG)))
    tiles = street(
        tmp_path,
        [
            Stand(-400, "Outside Walk", walled_outside_the_sector),
            Stand(400, "Margin Walk", walled_inside_the_margins),
        ],
    )

    spots = _by_name(answer(morning(wake_time="07:00"), tiles))

    assert spots["Outside Walk"].sky_openness == 1.0
    # 127 open samples at 1, and 40 walled at cos^2(60) = 0.25: 137/167.
    assert spots["Margin Walk"].sky_openness == 0.820


def test_a_candidate_with_sky_openness_below_0_75_is_never_shown(tmp_path: Path) -> None:
    # Rings of obstruction all round: cos^2(29.5) = 0.758, cos^2(30.5) = 0.742.
    # The midsummer sun climbs over both rings inside the window (29.51
    # degrees at 08:26, 30.59 at 08:33), so both Candidates have Sun minutes.
    tiles = street(
        tmp_path,
        [Stand(-400, "Enclosed Yard", horizon(30.5)), Stand(400, "Open Court", horizon(29.5))],
    )

    result = answer(morning(date="2026-06-21", wake_time="07:00"), tiles)

    [spot] = result.spots
    assert spot.name == "Open Court"
    assert spot.sky_openness == 0.758
    assert spot.sun_intervals == (Interval(at("08:26", **BST), at("10:00", **BST)),)
    # Low sun at 08:26-08:29, minutes 86-89 after waking: (94 + 93 + 92 + 91)/120.
    assert spot.low_sun_minutes == 3.08


# --- Ranking -----------------------------------------------------------------


def test_spots_are_ranked_by_low_sun_minutes_however_far_the_walk(tmp_path: Path) -> None:
    behind_a_ridge = horizon(ridges=((100.0, 140.5, 10.0),))
    tiles = street(tmp_path, [Stand(160, "Ridge Row", behind_a_ridge), Stand(-800, "Plain Street")])

    result = answer(morning(wake_time="07:00"), tiles)

    assert [spot.name for spot in result.spots] == ["Plain Street", "Ridge Row"]
    assert [spot.walk_min for spot in result.spots] == [10.0, 2.0]


def test_spots_with_equal_low_sun_minutes_are_ranked_nearest_first(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(-800, "Far Field"), Stand(400, "Near Green")])

    result = answer(morning(wake_time="07:00"), tiles)

    assert [spot.name for spot in result.spots] == ["Near Green", "Far Field"]


def test_a_saturated_tie_is_ordered_by_whole_metres_then_candidate_id(tmp_path: Path) -> None:
    enclosed = [Stand(1000, "Enclosed Yard", horizon(WALL_DEG))] * 9
    stands = [
        *enclosed[:2],
        Stand(-300, "West Green", offset_cm=40),  # Candidate 2: 300.40 m
        *enclosed[2:],
        Stand(300, "East Green", offset_cm=30),  # Candidate 10: 300.30 m
    ]
    tiles = street(tmp_path, stands)

    result = answer(morning(wake_time="07:00"), tiles)

    # Equal low-sun minutes, and both walks are 300 whole metres, so the
    # candidateId decides: Candidate 2 before Candidate 10, though it is 10 cm
    # further and "ST5873/10" sorts first as text.
    assert [spot.candidate_id for spot in result.spots] == ["ST5873/2", "ST5873/10"]
    assert [spot.walk_metres for spot in result.spots] == [300, 300]
    assert [spot.low_sun_minutes for spot in result.spots] == [45.5, 45.5]


# --- De-dupe -----------------------------------------------------------------


def test_a_later_spot_with_the_same_spot_name_is_dropped(tmp_path: Path) -> None:
    tiles = street(
        tmp_path,
        [Stand(100, "Brandon Hill"), Stand(400, "Brandon Hill"), Stand(-400, "Plain Street")],
    )

    result = answer(morning(wake_time="07:00"), tiles)

    assert [spot.candidate_id for spot in result.spots] == ["ST5873/0", "ST5873/2"]


def test_a_later_spot_within_200_m_of_a_kept_spot_is_dropped(tmp_path: Path) -> None:
    tiles = street(
        tmp_path,
        [Stand(100, "First Street"), Stand(250, "Second Street"), Stand(350, "Third Street")],
    )

    result = answer(morning(wake_time="07:00"), tiles)

    # Second Street is 150 m from First Street. Third Street is 250 m from it,
    # and only 100 m from Second Street, which was not kept.
    assert [spot.name for spot in result.spots] == ["First Street", "Third Street"]


def test_only_the_first_five_kept_spots_are_shown(tmp_path: Path) -> None:
    tiles = street(
        tmp_path,
        [
            Stand(-750, "Street 0"),
            Stand(-500, "Street 1"),
            Stand(-250, "Street 2"),
            Stand(250, "Street 3"),
            Stand(500, "Street 4"),
            Stand(750, "Street 5"),
            Stand(1000, "Street 6"),
        ],
    )

    result = answer(morning(wake_time="07:00"), tiles)

    assert [spot.name for spot in result.spots] == [
        "Street 2",
        "Street 3",
        "Street 1",
        "Street 4",
        "Street 0",
    ]


# --- Leave-by ----------------------------------------------------------------


def test_morning_leave_by_is_the_start_of_the_first_sun_interval_minus_the_walk(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    [spot] = answer(morning(wake_time="07:00"), tiles).spots

    # Sun from 08:16, and 400 m is 5 min at 80 m/min.
    assert spot.walk_min == 5.0
    assert spot.leave_by == at("08:11")


def test_morning_leave_by_is_never_before_wake_time(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    [spot] = answer(morning(wake_time="09:00"), tiles).spots

    assert spot.sun_intervals[0].start == at("09:00")
    assert spot.leave_by == at("09:00")


def test_morning_leave_by_is_never_before_now(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    [spot] = answer(morning(wake_time="07:00", now="2026-12-21T08:14:00Z"), tiles).spots

    assert spot.sun_intervals[0].start == at("08:16")
    assert spot.leave_by == at("08:14")


# --- Duration target ---------------------------------------------------------


def test_duration_target_is_10_min_for_a_clear_sky_and_20_for_partly_cloudy(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    assert answer(morning(sky="clear"), tiles).duration_target_min == 10
    assert answer(morning(sky="partly"), tiles).duration_target_min == 20


def test_the_walk_counts_towards_the_duration_target(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])
    eleven_minutes_left = morning(wake_time="09:00", now="2026-12-21T11:49:00Z")

    [clear] = answer(eleven_minutes_left, tiles).spots
    [partly] = answer(replace(eleven_minutes_left, sky="partly"), tiles).spots

    # Leave at 11:49, arrive 11:54, and 6 Sun minutes remain: 5 + 6 = 11.
    assert clear.leave_by == at("11:49")
    assert clear.target_met is True
    assert partly.target_met is False


def test_sun_before_arrival_is_not_credited_towards_the_duration_target(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    [spot] = answer(morning(wake_time="09:00", now="2026-12-21T11:52:00Z"), tiles).spots

    # 8 Sun minutes in the window, but only 3 after arriving at 11:57: 5 + 3 < 10.
    assert spot.sun_minutes == 8
    assert spot.target_met is False


# --- Walk --------------------------------------------------------------------


def test_walk_is_measured_along_the_walk_graph_from_the_origin_snapped_to_the_nearest_edge(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(500, "East End", offset_cm=730), Stand(-300, "West End")])
    # 30 m north of the street, 100 m east of its node at 0.
    off_the_street = morning(origin_lat=lat_at(30), origin_lon=lon_at(100))

    spots = _by_name(answer(off_the_street, tiles))

    # 400 m along the street, plus the Candidate's 7.3 m offset from its node.
    assert spots["East End"].walk_metres == 407
    assert spots["West End"].walk_metres == 400
    assert spots["West End"].walk_min == 5.0


def test_a_candidate_beyond_max_walk_is_not_shown(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Near Green"), Stand(1400, "Far Field")])

    within_15 = answer(morning(max_walk_min=15), tiles)
    within_20 = answer(morning(max_walk_min=20), tiles)

    assert [spot.name for spot in within_15.spots] == ["Near Green"]
    # 1,400 m is 17.5 min.
    assert [spot.name for spot in within_20.spots] == ["Near Green", "Far Field"]


def test_max_walk_is_capped_at_20_min() -> None:
    with pytest.raises(ValueError, match="max walk"):
        morning(max_walk_min=21)


def test_a_walk_crosses_tiles_joined_on_their_shared_nodes(tmp_path: Path) -> None:
    # The edge from 400 m to 900 m crosses the tile boundary, so it is in both tiles.
    west = street_tile([Stand(400, "West Street")], "ST5873", extra_nodes_east_m=(0.0, 900.0))
    east = street_tile([Stand(1200, "East Street")], "ST5973", extra_nodes_east_m=(400.0, 900.0))

    result = answer(morning(max_walk_min=20), build(tmp_path, west, east))

    assert [(spot.candidate_id, spot.walk_metres) for spot in result.spots] == [
        ("ST5873/0", 400),
        ("ST5973/0", 1200),
    ]


# --- Contract ----------------------------------------------------------------


def test_query_and_answer_cross_the_seam_as_the_contract_json(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])
    query = Query.from_json(
        {
            "window": "morning",
            "date": "2026-12-21",
            "wakeTime": "07:00",
            "now": "2026-12-21T08:14:00Z",
            "origin": {"lat": 51.45, "lon": -2.60},
            "maxWalkMin": 15,
            "sky": "partly",
        }
    )

    assert answer(query, tiles).to_json() == {
        "status": "ranked",
        "window": {
            "start": at("08:14"),
            "end": at("10:00"),
            "axisStart": at("08:14"),
            "axisEnd": at("10:00"),
        },
        "nominalSunrise": at("08:13"),
        "nominalSunset": at("16:04"),
        "solarNoon": at("12:08"),
        "durationTargetMin": 20,
        "lamp": True,  # Nominal sunrise 08:13 is more than 1 h after Wake time 07:00
        "spots": [
            {
                "candidateId": "ST5873/0",
                "name": "Plain Street",
                "lat": 51.45,
                "lon": pytest.approx(lon_at(400), abs=1e-7),
                "walkMetres": 400,
                "walkMin": 5.0,
                "leaveBy": at("08:14"),
                "sunIntervals": [{"start": at("08:16"), "end": at("10:00")}],
                "lowSunIntervals": [{"start": at("08:16"), "end": at("10:00")}],
                "sunMinutes": 104,
                "lowSunMinutes": 45.5,
                "skyOpenness": 1.0,
                "targetMet": True,
            }
        ],
    }
