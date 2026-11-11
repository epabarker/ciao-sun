"""The cloud category (#45): the span it is averaged over, and the category a forecast gives.

The canned forecasts and their expected categories are in
`fixtures/cloud/cases.json`, shared with the JS forecast adapter's tests so
both languages are held to the same values. Each case's note works its
expected value out by hand. Spans come from these facts about the sun at the
origin (51.45 N, 2.60 W), from the reference solar model:

    2026-12-21 (GMT): Nominal sunrise 08:13, Nominal sunset 16:04
    2026-06-21 (BST): solar noon 13:12, Nominal sunset 21:31
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from ciao_sun.reference import Query
from ciao_sun.reference.cloud import (
    cloud_category,
    cloud_span,
    forecast_coordinate,
    mean_cloud_cover,
)

CASES: dict[str, Any] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "cloud" / "cases.json").read_text()
)


def _query(window: str, date: str, wake: str) -> Query:
    return Query(
        window=window,  # type: ignore[arg-type]
        date=date,
        wake_time=wake,
        origin_lat=51.45,
        origin_lon=-2.60,
        max_walk_min=15,
        sky="clear",
    )


def _span(case: dict[str, Any]) -> tuple[pd.Timestamp, pd.Timestamp]:
    return pd.Timestamp(case["span"]["start"]), pd.Timestamp(case["span"]["end"])


# --- The span ----------------------------------------------------------------


def test_morning_cloud_span_is_the_morning_window() -> None:
    start, end = cloud_span(_query("morning", "2026-12-21", "07:00")) or (None, None)
    assert start == pd.Timestamp("2026-12-21T08:13:00+00:00")
    assert end == pd.Timestamp("2026-12-21T10:00:00+00:00")


def test_evening_cloud_span_is_the_last_3_h_of_the_evening_window() -> None:
    start, end = cloud_span(_query("evening", "2026-06-21", "07:00")) or (None, None)
    assert start == pd.Timestamp("2026-06-21T18:31:00+01:00")
    assert end == pd.Timestamp("2026-06-21T21:31:00+01:00")


def test_evening_cloud_span_is_all_of_an_evening_window_shorter_than_3_h() -> None:
    start, end = cloud_span(_query("evening", "2026-12-21", "08:00")) or (None, None)
    assert start == pd.Timestamp("2026-12-21T14:00:00+00:00")
    assert end == pd.Timestamp("2026-12-21T16:04:00+00:00")


def test_no_cloud_span_without_a_window() -> None:
    # Wake 11:00 puts the Evening window's start at 17:00, after Nominal sunset.
    assert cloud_span(_query("evening", "2026-12-21", "11:00")) is None
    # Wake 04:00: the Morning window ends at 07:00, before Nominal sunrise.
    assert cloud_span(_query("morning", "2026-12-21", "04:00")) is None


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["name"])
def test_each_shared_case_span_is_its_querys_window(case: dict[str, Any]) -> None:
    assert cloud_span(Query.from_json(case["query"])) == _span(case)


# --- The category ------------------------------------------------------------


@pytest.mark.parametrize(
    ("c", "sky"),
    [
        (0, "clear"),
        (24.99, "clear"),
        (25, "partly"),
        (79.99, "partly"),
        (80, "overcast"),
        (100, "overcast"),
    ],
)
def test_cloud_category_thresholds(c: float, sky: str) -> None:
    assert cloud_category(c) == sky


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["name"])
def test_each_shared_case_gives_its_mean_and_category(case: dict[str, Any]) -> None:
    mean = mean_cloud_cover(case["response"], *_span(case))
    if case["category"] is None:
        assert mean is None
    else:
        assert mean == pytest.approx(case["meanCloudCover"], abs=1e-9)
        assert cloud_category(mean) == case["category"]


def test_a_malformed_forecast_covers_nothing() -> None:
    start, end = pd.Timestamp("2026-12-21T08:13Z"), pd.Timestamp("2026-12-21T10:00Z")
    assert mean_cloud_cover({}, start, end) is None
    assert mean_cloud_cover({"hourly": {"time": [1, 2], "cloud_cover": [1]}}, start, end) is None


# --- The request coordinate --------------------------------------------------


@pytest.mark.parametrize("pair", CASES["coordinates"], ids=lambda p: str(p["origin"]))
def test_forecast_coordinate_is_rounded_to_0_05_degrees(pair: dict[str, Any]) -> None:
    lat, lon = forecast_coordinate(pair["origin"]["lat"], pair["origin"]["lon"])
    assert (lat, lon) == (pair["request"]["lat"], pair["request"]["lon"])
