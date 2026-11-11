"""The reference scorer (#40): the fallback, lamp, lamp-only and not-covered Answers.

Every test builds a small synthetic world, writes it through the tile codec
and asserts only on the Answer that `ciao_sun.reference.answer` returns. The
sun facts are those at the top of `test_reference_morning.py`: at the origin
on 2026-12-21 (GMT) Nominal sunrise is 08:13 and Nominal sunset 16:04, and
from a flat plain the sun is in view from 08:16.
"""

from __future__ import annotations

from pathlib import Path

from ciao_sun.coverage import Coverage
from ciao_sun.reference import Answer, Spot, answer

from .reference_worlds import WALL_DEG, Stand, horizon, lon_at, morning, street


def at(clock: str, date: str = "2026-12-21", offset: str = "+00:00") -> str:
    return f"{date}T{clock}:00{offset}"


def _by_name(result: Answer) -> dict[str, Spot]:
    return {spot.name: spot for spot in result.spots}


# A ring of walls the midwinter sun (15.2 degrees at its highest) never clears,
# low enough to pass openness: cos^2(20) = 0.883.
NO_SUN = horizon(20.0)


# --- Overcast fallback -------------------------------------------------------


def test_an_overcast_sky_lists_the_nearest_open_spots_by_walk_whatever_their_sun(
    tmp_path: Path,
) -> None:
    tiles = street(
        tmp_path,
        [
            Stand(-800, "Sunny Field"),
            Stand(400, "Shaded Green", NO_SUN),
            Stand(160, "Enclosed Yard", horizon(WALL_DEG)),
        ],
    )

    result = answer(morning(wake_time="07:00", sky="overcast"), tiles)

    assert result.status == "fallback"
    assert [spot.name for spot in result.spots] == ["Shaded Green", "Sunny Field"]
    assert [spot.walk_min for spot in result.spots] == [5.0, 10.0]
    assert result.nearest_sun_beyond_limit is None


def test_a_fallback_spot_says_to_stay_for_the_duration_target_less_the_walk(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    result = answer(morning(wake_time="07:00", sky="overcast"), tiles)

    assert result.duration_target_min == 30
    [spot] = result.spots
    # The walk counts towards the target: 400 m is 5 min, so stay 25.
    assert spot.walk_min == 5.0
    assert spot.stay_min == 25


def test_a_fractional_walk_leaves_a_stay_rounded_up_to_the_whole_minute(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(-600, "Far Street")])

    result = answer(morning(wake_time="07:00", sky="overcast"), tiles)

    # 600 m is 7.5 min; 22.5 min more is rounded up, so walk + stay is never short.
    [spot] = result.spots
    assert spot.walk_min == 7.5
    assert spot.stay_min == 23


def test_a_walk_as_long_as_the_target_leaves_a_stay_of_zero(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(900, "Long Walk", NO_SUN)])

    result = answer(morning(wake_time="07:00", sky="clear"), tiles)

    # A clear sky's target is 10 min; the 11.25 min walk alone meets it.
    assert result.status == "fallback"
    [spot] = result.spots
    assert spot.walk_min == 11.25
    assert spot.stay_min == 0


def test_a_fallback_spot_is_left_for_at_the_start_of_the_window(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    before_sunrise = answer(morning(wake_time="07:00", sky="overcast"), tiles)
    after_sunrise = answer(morning(wake_time="09:00", sky="overcast"), tiles)
    under_way = answer(
        morning(wake_time="09:00", sky="overcast", now="2026-12-21T09:30:00Z"), tiles
    )

    # The later of Wake time and Nominal sunrise, or now: not sun minus the walk.
    assert [spot.leave_by for spot in before_sunrise.spots] == [at("08:13")]
    assert [spot.leave_by for spot in after_sunrise.spots] == [at("09:00")]
    assert [spot.leave_by for spot in under_way.spots] == [at("09:30")]


def test_fallback_spots_are_de_duped_and_tied_walks_are_ordered_by_candidate_id(
    tmp_path: Path,
) -> None:
    tiles = street(
        tmp_path,
        [
            Stand(500, "East Green"),
            Stand(-500, "West Green"),
            Stand(100, "Brandon Hill"),
            Stand(-900, "Brandon Hill"),  # the same Spot name as a kept spot
            Stand(250, "Second Street"),  # 150 m from Brandon Hill
        ],
    )

    result = answer(morning(wake_time="07:00", sky="overcast"), tiles)

    # East Green and West Green are both 500 m away: Candidate 0 before Candidate 1.
    assert [spot.candidate_id for spot in result.spots] == ["ST5873/2", "ST5873/0", "ST5873/1"]


# --- No-sun fallback ---------------------------------------------------------


def test_a_clear_sky_with_no_sun_in_reach_falls_back_to_the_nearest_open_spots(
    tmp_path: Path,
) -> None:
    tiles = street(
        tmp_path,
        [Stand(-600, "Far Shade", NO_SUN), Stand(400, "Near Shade", NO_SUN)],
    )

    result = answer(morning(wake_time="07:00", sky="clear"), tiles)

    assert result.status == "fallback"
    assert [spot.name for spot in result.spots] == ["Near Shade", "Far Shade"]
    assert [spot.sun_minutes for spot in result.spots] == [0, 0]
    # Target 10: 400 m is 5 min, so stay 5; 600 m is 7.5 min, so stay 3 (2.5 rounded up).
    assert [spot.stay_min for spot in result.spots] == [5, 3]
    assert [spot.leave_by for spot in result.spots] == [at("08:13"), at("08:13")]
    # No spot with sun anywhere within the 20 min cap.
    assert result.nearest_sun_beyond_limit is None
    assert "nearestSunBeyondLimit" not in result.to_json()


def test_a_no_sun_fallback_names_the_nearest_spot_with_sun_beyond_max_walk(
    tmp_path: Path,
) -> None:
    tiles = street(
        tmp_path,
        [
            Stand(400, "Near Shade", NO_SUN),
            Stand(-900, "Shade Beyond", NO_SUN),
            Stand(1400, "Further Field"),
            Stand(-1000, "Sunny Field"),
        ],
    )

    result = answer(morning(wake_time="07:00", sky="partly", max_walk_min=10), tiles)

    assert result.status == "fallback"
    assert [spot.name for spot in result.spots] == ["Near Shade"]
    beyond = result.nearest_sun_beyond_limit
    assert beyond is not None
    assert beyond.name == "Sunny Field"
    assert beyond.walk_min == 12.5
    assert beyond.sun_minutes == 104
    # A spot with sun: left for so as to arrive as the sun appears at 08:16,
    # the 12.5 min walk rounded up to 13, and no "stay N min".
    assert beyond.leave_by == at("08:03")
    assert beyond.stay_min is None
    assert result.to_json()["nearestSunBeyondLimit"]["candidateId"] == "ST5873/3"


def test_the_spot_with_sun_beyond_max_walk_is_no_further_than_the_20_min_cap(
    tmp_path: Path,
) -> None:
    # 1,600 m is 20 min; 1,601 m is past the cap.
    inside = street(tmp_path / "in", [Stand(400, "Near Shade", NO_SUN), Stand(1600, "Sunny Field")])
    outside = street(
        tmp_path / "out", [Stand(400, "Near Shade", NO_SUN), Stand(1601, "Sunny Field")]
    )
    query = morning(wake_time="07:00", max_walk_min=10)

    at_the_cap, past_the_cap = answer(query, inside), answer(query, outside)

    assert at_the_cap.nearest_sun_beyond_limit is not None
    assert at_the_cap.nearest_sun_beyond_limit.walk_min == 20.0
    assert past_the_cap.status == "fallback"
    assert past_the_cap.nearest_sun_beyond_limit is None


def test_an_overcast_fallback_never_names_a_spot_beyond_max_walk(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Near Shade", NO_SUN), Stand(1000, "Sunny Field")])

    result = answer(morning(wake_time="07:00", sky="overcast", max_walk_min=10), tiles)

    assert [spot.name for spot in result.spots] == ["Near Shade"]
    assert result.nearest_sun_beyond_limit is None


# --- Lamp --------------------------------------------------------------------


def test_lamp_is_set_when_nominal_sunrise_is_more_than_an_hour_after_wake_time(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    # Nominal sunrise is 08:13.
    assert answer(morning(wake_time="07:12"), tiles).lamp is True
    assert answer(morning(wake_time="07:13"), tiles).lamp is False
    assert answer(morning(wake_time="09:00"), tiles).lamp is False
    # Midsummer: Nominal sunrise at 04:53 is exactly 1 h after a 03:53 Wake time.
    assert answer(morning(date="2026-06-21", wake_time="03:53"), tiles).lamp is False


def test_lamp_is_set_on_a_fallback_answer_too(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    dark = answer(morning(wake_time="07:00", sky="overcast"), tiles)
    light = answer(morning(wake_time="08:00", sky="overcast"), tiles)

    assert (dark.status, dark.lamp) == ("fallback", True)
    assert (light.status, light.lamp) == ("fallback", False)
    assert dark.to_json()["lamp"] is True
    assert light.to_json()["lamp"] is False


# --- Lamp-only ---------------------------------------------------------------


def test_a_morning_window_that_ends_by_nominal_sunrise_gives_only_the_lamp_and_the_next_light(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    # Wake time 05:13: the window would end at 08:13, as the sun rises.
    result = answer(morning(wake_time="05:13"), tiles)

    assert result.to_json() == {
        "status": "lamp-only",
        "lamp": True,
        "nextOutdoorLight": at("08:13"),
        "spots": [],
    }
    # One minute later there is a minute of daylight in the window.
    assert answer(morning(wake_time="05:14"), tiles).status != "lamp-only"


def test_a_morning_window_already_over_at_now_is_lamp_only_with_outdoor_light_now(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    # Wake time 07:00: the window ended at 10:00, and the sun is up until 16:04.
    winter = answer(morning(wake_time="07:00", now="2026-12-21T10:00:00Z"), tiles)
    summer = answer(
        morning(date="2026-06-21", wake_time="07:00", now="2026-06-21T12:30:00+01:00"), tiles
    )

    assert (winter.status, winter.spots, winter.window) == ("lamp-only", (), None)
    assert winter.next_outdoor_light == at("10:00")
    # The lamp follows its own rule: sunrise at 08:13 was more than 1 h after 07:00.
    assert winter.lamp is True
    assert (summer.status, summer.lamp) == ("lamp-only", False)
    assert summer.next_outdoor_light == at("12:30", date="2026-06-21", offset="+01:00")


def test_next_outdoor_light_after_nominal_sunset_is_tomorrows_nominal_sunrise(
    tmp_path: Path,
) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    at_sunset = answer(morning(wake_time="07:00", now="2026-12-21T16:04:00Z"), tiles)
    before_sunset = answer(morning(wake_time="07:00", now="2026-12-21T16:03:00Z"), tiles)

    # Nominal sunrise on 2026-12-22 is 08:14.
    assert at_sunset.status == "lamp-only"
    assert at_sunset.next_outdoor_light == at("08:14", date="2026-12-22")
    assert before_sunset.next_outdoor_light == at("16:03")


# --- Not covered -------------------------------------------------------------

# A box about 1.4 km east-west by 2.2 km north-south around the origin (51.45 N, 2.60 W).
COVERAGE = Coverage.from_geojson(
    {
        "type": "Polygon",
        "coordinates": [
            [[-2.61, 51.44], [-2.59, 51.44], [-2.59, 51.46], [-2.61, 51.46], [-2.61, 51.44]]
        ],
    }
)


def test_an_origin_outside_the_coverage_is_not_covered_and_gets_no_spots(tmp_path: Path) -> None:
    # The street runs on past the coverage's east edge, with a sunny Candidate
    # 100 m from the origin.
    tiles = street(tmp_path, [Stand(800, "Plain Street")])
    outside = morning(origin_lon=lon_at(900))

    result = answer(outside, tiles, coverage=COVERAGE)

    assert result.to_json() == {"status": "not-covered", "spots": []}
    # Without a coverage the same query is answered from the tiles alone.
    assert answer(outside, tiles).status == "ranked"


def test_an_origin_inside_the_coverage_is_answered(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])

    result = answer(morning(), tiles, coverage=COVERAGE)

    assert result.status == "ranked"
    assert [spot.name for spot in result.spots] == ["Plain Street"]


def test_an_origin_in_any_part_of_a_multipolygon_coverage_is_covered(tmp_path: Path) -> None:
    tiles = street(tmp_path, [Stand(400, "Plain Street")])
    far_part = [[[-2.50, 51.44], [-2.48, 51.44], [-2.48, 51.46], [-2.50, 51.46], [-2.50, 51.44]]]
    two_parts = Coverage.from_geojson(
        {"type": "MultiPolygon", "coordinates": [far_part, COVERAGE.geometry["coordinates"]]}
    )
    only_the_far_part = Coverage.from_geojson({"type": "Polygon", "coordinates": far_part})

    assert answer(morning(), tiles, coverage=two_parts).status == "ranked"
    assert answer(morning(), tiles, coverage=only_the_far_part).status == "not-covered"
