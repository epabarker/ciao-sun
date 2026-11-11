"""The reference scorer (#39): an Evening query gives a ranked Answer.

Every test builds a small synthetic world, writes it through the tile codec
and asserts only on the Answer that `ciao_sun.reference.answer` returns.

Expected values are worked out by hand from the spec's rules and from these
facts about the sun at the origin (51.45 N, 2.60 W), which come from the
reference solar model (`docs/solar-model.md`):

2026-12-21 (GMT): Nominal sunrise 08:13, solar noon 12:08, Nominal sunset 16:04.

    time   true azimuth   apparent elevation
    12:08     179.89          15.17   (the day's highest)
    13:00     192.18          14.32
    15:28     224.64           3.51
    15:29     224.84           3.40
    15:49     228.83           1.28
    15:50     229.02           1.18
    16:01     231.18           0.05
    16:02     231.37          -0.06
    16:03     231.56          -0.16
    16:12     233.30          -1.13
    16:13     233.50          -1.25

2026-06-21 (BST): solar noon 13:12, Nominal sunset 21:31.

    13:12     179.89          62.00
    17:55     270.70          30.04
    17:56     270.89          29.88
    21:28     310.42           0.09
    21:29     310.62          -0.01
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ciao_sun.reference import Answer, Interval, Query, Spot, answer

from .reference_worlds import Stand, evening, horizon, lon_at, morning, street

BST = {"date": "2026-06-21", "offset": "+01:00"}


def at(clock: str, date: str = "2026-12-21", offset: str = "+00:00") -> str:
    return f"{date}T{clock}:00{offset}"


def _by_name(result: Answer) -> dict[str, Spot]:
    return {spot.name: spot for spot in result.spots}


# --- Window bounds -----------------------------------------------------------


def test_evening_window_runs_from_6_h_after_wake_time_to_nominal_sunset(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    result = answer(evening(wake_time="07:00"), tiles)

    assert result.status == "ranked"
    assert result.solar_noon == at("12:08")
    assert result.nominal_sunset == at("16:04")
    assert result.window is not None
    assert (result.window.start, result.window.end) == (at("13:00"), at("16:04"))


def test_evening_window_starts_at_solar_noon_when_it_is_later_than_6_h_after_wake_time(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    result = answer(evening(wake_time="05:00"), tiles)

    assert result.window is not None
    assert (result.window.start, result.window.end) == (at("12:08"), at("16:04"))


def test_evening_window_starts_at_now_when_now_is_later_on_the_query_date(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    today = answer(evening(wake_time="07:00", now="2026-12-21T15:00:00Z"), tiles)
    the_day_before = answer(evening(wake_time="07:00", now="2026-12-20T15:00:00Z"), tiles)

    assert today.window is not None and the_day_before.window is not None
    assert (today.window.start, today.window.end) == (at("15:00"), at("16:04"))
    assert the_day_before.window.start == at("13:00")


def test_evening_axis_covers_the_last_3_h_before_nominal_sunset(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    long_window = answer(evening(wake_time="05:00"), tiles)
    short_window = answer(evening(wake_time="07:00", now="2026-12-21T15:00:00Z"), tiles)

    for result in (long_window, short_window):
        assert result.window is not None
        assert (result.window.axis_start, result.window.axis_end) == (at("13:04"), at("16:04"))


@pytest.mark.parametrize("wake_time", ["10:04", "10:30"])
def test_there_is_no_evening_window_when_6_h_after_wake_time_is_not_before_nominal_sunset(
    tmp_path: Path, wake_time: str
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    result = answer(evening(wake_time=wake_time), tiles)

    assert result.status == "no-evening-window"
    assert result.spots == ()
    assert result.window is None
    assert result.to_json() == {
        "status": "no-evening-window",
        "nominalSunrise": at("08:13"),
        "nominalSunset": at("16:04"),
        "solarNoon": at("12:08"),
        "spots": [],
    }


def test_there_is_no_evening_window_once_now_has_reached_nominal_sunset(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    result = answer(evening(wake_time="07:00", now="2026-12-21T16:04:00Z"), tiles)

    assert result.status == "no-evening-window"


# --- Last sun ----------------------------------------------------------------

# A roof on true bearings 225 degrees and beyond. The Horizon profile is 0 up
# to the sample at 224.75 and rises linearly to 40 at 225.0.
ROOF = horizon(ridges=((225.0, 359.75, 40.0),))


def test_evening_sun_minutes_end_at_last_sun_when_the_sun_sets_behind_a_roof(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(-400, "Roof Row", ROOF), Stand(400, "Plain Street")])

    spots = _by_name(answer(evening(wake_time="07:00"), tiles))

    # 15:28: the sun bears 224.64, short of the roof. 15:29: it bears 224.84 at
    # 3.4 degrees, where the roof has risen to 40 x 0.36 = 14.4.
    roof = spots["Roof Row"]
    assert roof.last_sun == at("15:28")
    assert roof.sun_intervals == (Interval(at("13:00"), at("15:29")),)
    assert roof.sun_minutes == 149
    # On the plain the sun is last above 0 degrees at 16:01.
    plain = spots["Plain Street"]
    assert plain.last_sun == at("16:01")
    assert plain.sun_intervals == (Interval(at("13:00"), at("16:02")),)
    assert plain.sun_minutes == 182


def test_twilight_after_nominal_sunset_earns_no_sun_minutes(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Hilltop Road", horizon(-1.2))])

    [spot] = answer(evening(wake_time="07:00"), tiles).spots

    # From the hilltop the sun stays in view until 16:12, below 0 degrees from
    # 16:02. The window, and with it the Sun minutes, ends at Nominal sunset.
    assert spot.last_sun == at("16:12")
    assert spot.sun_intervals == (Interval(at("13:00"), at("16:04")),)
    assert spot.sun_minutes == 184
    assert spot.low_sun_intervals == (Interval(at("13:00"), at("16:02")),)
    assert spot.low_sun_minutes == 182.0


def test_a_morning_spot_reports_no_last_sun(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    [spot] = answer(morning(wake_time="07:00"), tiles).spots

    assert spot.last_sun is None
    assert "lastSun" not in spot.to_json()


# --- Unweighted minutes ------------------------------------------------------


@pytest.mark.parametrize(
    "now,minutes_left",
    [("13:00", 182.0), ("13:01", 181.0), ("15:00", 62.0), ("16:00", 2.0), ("16:01", 1.0)],
)
def test_every_evening_low_sun_minute_counts_as_one_however_late(
    tmp_path: Path, now: str, minutes_left: float
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    [spot] = answer(evening(wake_time="07:00", now=f"2026-12-21T{now}:00Z"), tiles).spots

    # The midwinter sun is below 30 degrees all afternoon and in view from the
    # plain until 16:01, so each minute from `now` to 16:01 is a low-sun minute.
    assert spot.low_sun_minutes == minutes_left
    assert spot.sun_minutes == minutes_left


def test_evening_low_sun_minutes_count_only_sun_in_view_at_0_to_30_degrees(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    [spot] = answer(evening(date="2026-06-21", wake_time="07:00"), tiles).spots

    # Solar noon (13:12 BST) is later than Wake time + 6 h. The sun is in view
    # until 21:28 and at or below 30 degrees from 17:56.
    assert spot.sun_intervals == (Interval(at("13:12", **BST), at("21:29", **BST)),)
    assert spot.low_sun_intervals == (Interval(at("17:56", **BST), at("21:29", **BST)),)
    assert spot.sun_minutes == 497
    assert spot.low_sun_minutes == 213.0


# --- Ranking -----------------------------------------------------------------


def test_evening_spots_are_ranked_by_low_sun_minutes_before_last_sun(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(160, "Roof Row", ROOF), Stand(-800, "Plain Street")])

    result = answer(evening(wake_time="07:00"), tiles)

    assert [spot.name for spot in result.spots] == ["Plain Street", "Roof Row"]
    assert [spot.low_sun_minutes for spot in result.spots] == [182.0, 149.0]
    assert [spot.walk_min for spot in result.spots] == [10.0, 2.0]


def test_evening_spots_with_equal_low_sun_minutes_are_ranked_nearest_first(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(-800, "Far Field"), Stand(400, "Near Green")])

    result = answer(evening(wake_time="07:00"), tiles)

    assert [spot.name for spot in result.spots] == ["Near Green", "Far Field"]


# --- Leave-by ----------------------------------------------------------------


def test_evening_leave_by_is_the_latest_departure_that_meets_the_duration_target(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    [clear] = answer(evening(sky="clear"), tiles).spots
    [partly] = answer(evening(sky="partly"), tiles).spots

    # The walk is 5 min and Last sun is 16:01. Clear: 5 more Sun minutes are
    # needed, 15:57 to 16:01, so arrive at 15:57. Partly cloudy: 15 more,
    # 15:47 to 16:01.
    assert clear.leave_by == at("15:52")
    assert clear.target_met is True
    assert partly.leave_by == at("15:42")
    assert partly.target_met is True


def test_evening_leave_by_counts_sun_minutes_only_up_to_last_sun(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Roof Row", ROOF)])

    [spot] = answer(evening(sky="clear"), tiles).spots

    # Last sun is 15:28 behind the roof: arrive at 15:24 for 5 Sun minutes.
    assert spot.leave_by == at("15:19")
    assert spot.target_met is True


def test_evening_leave_by_rounds_a_part_minute_of_walk_up(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street", offset_cm=730)])

    [spot] = answer(evening(sky="clear"), tiles).spots

    # 407 m is 5.0875 min: 5 Sun minutes are still needed (4.9125 rounded up),
    # so arrive at 15:57, and the walk takes 6 whole minutes.
    assert spot.walk_metres == 407
    assert spot.leave_by == at("15:51")
    assert spot.target_met is True


def test_evening_leave_by_arrives_for_the_last_sun_minute_when_the_walk_alone_meets_the_target(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(1000, "Far Field")])

    [spot] = answer(evening(sky="clear"), tiles).spots

    # 12.5 min of walk is over the 10 min target. Leaving ever later would
    # still "meet" it, so the latest departure is the one that arrives at
    # Last sun, 16:01, after 13 whole minutes of walk.
    assert spot.leave_by == at("15:48")
    assert spot.target_met is True


def test_evening_leave_by_follows_the_morning_rule_when_no_departure_meets_the_target(
    tmp_path: Path,
) -> None:
    # A wall on true bearings 180 to 228.75 degrees, higher than the midwinter
    # sun ever climbs. The Horizon profile falls linearly to 0 at 229.0.
    behind_a_wall = horizon(ridges=((180.0, 228.75, 20.0),))
    tiles = street(tmp_path, [Stand(400, "Gap Lane", behind_a_wall)])

    [clear] = answer(evening(sky="clear"), tiles).spots
    [partly] = answer(evening(sky="partly"), tiles).spots

    # 15:49: the sun bears 228.83 at 1.28 degrees, where the wall is still at
    # 20 x 0.68 = 13.6. From 15:50 it is past the wall, until Last sun at 16:01.
    assert partly.sun_intervals == (Interval(at("15:50"), at("16:02")),)
    assert partly.sun_minutes == 12
    # Partly cloudy needs 15 Sun minutes after a 5 min walk and there are 12:
    # the target is not met, and leave-by is timed to arrive as the sun appears.
    assert partly.target_met is False
    assert partly.leave_by == at("15:45")
    # Clear needs 5: arrive at 15:57.
    assert clear.target_met is True
    assert clear.leave_by == at("15:52")


@pytest.mark.parametrize(
    "now,leave_by,target_met",
    [("15:30", "15:52", True), ("15:52", "15:52", True), ("15:53", "15:53", False)],
)
def test_evening_leave_by_is_never_before_now(
    tmp_path: Path, now: str, leave_by: str, target_met: bool
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    [spot] = answer(evening(sky="clear", now=f"2026-12-21T{now}:00Z"), tiles).spots

    # The latest departure that meets the target is 15:52. Leaving at 15:53
    # arrives at 15:58 with 4 Sun minutes left: 5 + 4 < 10, so the target is
    # not met and the morning rule applies, which never leaves before now.
    assert spot.leave_by == at(leave_by)
    assert spot.target_met is target_met


# --- Contract ----------------------------------------------------------------


def test_an_evening_query_and_answer_cross_the_seam_as_the_contract_json(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Roof Row", ROOF)])
    query = Query.from_json(
        {
            "window": "evening",
            "date": "2026-12-21",
            "wakeTime": "07:00",
            "origin": {"lat": 51.45, "lon": -2.60},
            "maxWalkMin": 15,
            "sky": "partly",
        }
    )

    # The roof fills the sector's 67 samples from 225.0 to 241.5 degrees, of
    # the 238 from 182.25: (171 + 67 x cos^2(40)) / 238 = 0.884.
    assert answer(query, tiles).to_json() == {
        "status": "ranked",
        "window": {
            "start": at("13:00"),
            "end": at("16:04"),
            "axisStart": at("13:04"),
            "axisEnd": at("16:04"),
        },
        "nominalSunrise": at("08:13"),
        "nominalSunset": at("16:04"),
        "solarNoon": at("12:08"),
        "durationTargetMin": 20,
        "spots": [
            {
                "candidateId": "ST5873/0",
                "name": "Roof Row",
                "lat": 51.45,
                "lon": pytest.approx(lon_at(400), abs=1e-7),
                "walkMetres": 400,
                "walkMin": 5.0,
                "leaveBy": at("15:09"),
                "sunIntervals": [{"start": at("13:00"), "end": at("15:29")}],
                "lowSunIntervals": [{"start": at("13:00"), "end": at("15:29")}],
                "sunMinutes": 149,
                "lowSunMinutes": 149.0,
                "skyOpenness": 0.884,
                "targetMet": True,
                "lastSun": at("15:28"),
            }
        ],
    }
