"""Correctness of the longest-unbroken-clear-window logic in search.py.

This isn't one of HANDOFF.md's original eight groups (it postdates them), but
the same principle applies: the answer isn't eyeballable, so it needs a
synthetic ground truth.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sunspot.search import (
    SearchResult,
    clear_window_minutes,
    longest_clear_run,
    passing_mask_duration,
)


def test_longest_clear_run_various_patterns():
    # All rows padded to the same width (6) with trailing False, which cannot
    # extend or create a run, so it doesn't change any row's expected answer.
    mask = np.array(
        [
            [False, False, False, False, False, False],  # never clear
            [True, True, True, True, False, False],  # clear then stops
            [True, False, True, True, False, False],  # longest run is positions 2-3
            [True, True, False, True, True, True],  # two runs; second (len 3) is longest
            [True, False, False, False, True, False],  # two isolated single steps
        ]
    )
    max_len, start, end = longest_clear_run(mask)

    assert list(max_len) == [0, 4, 2, 3, 1]
    assert list(start) == [-1, 0, 2, 3, 0]
    assert list(end) == [-1, 3, 3, 5, 0]


def test_longest_clear_run_ties_pick_the_first():
    # two runs of equal length 2: steps [0,1] and [4,5]. argmax returns the
    # first occurrence of the max value, so the first run wins.
    mask = np.array([[True, True, False, False, True, True]])
    max_len, start, end = longest_clear_run(mask)
    assert max_len[0] == 2
    assert (start[0], end[0]) == (0, 1)


def _make_result(clear_mask: np.ndarray, step_minutes: float = 5.0) -> SearchResult:
    n, m = clear_mask.shape
    times = pd.date_range("2026-09-20 06:54", periods=m, freq=pd.Timedelta(minutes=step_minutes))
    return SearchResult(
        x=np.zeros(n),
        y=np.zeros(n),
        distance_m=np.zeros(n),
        fraction_clear=clear_mask.mean(axis=1),
        worst_horizon_angle=np.zeros(n),
        clear_mask=clear_mask,
        times=times,
    )


def test_clear_window_minutes_matches_step_spacing():
    # 3 consecutive clear steps at 5-minute spacing span 10 minutes wall-clock
    # (first to last clear sample), not 15 -- duration is a span, not a count.
    mask = np.array([[False, True, True, True, False]])
    result = _make_result(mask, step_minutes=5.0)
    duration, start, end = clear_window_minutes(result)
    assert duration[0] == 10.0
    assert result.times[start[0]].strftime("%H:%M") == "06:59"
    assert result.times[end[0]].strftime("%H:%M") == "07:09"


def test_clear_window_minutes_zero_for_isolated_step_and_no_clear_steps():
    mask = np.array(
        [
            [False, True, False],  # single isolated clear step: zero-width window
            [False, False, False],  # never clear
        ]
    )
    result = _make_result(mask, step_minutes=5.0)
    duration, start, end = clear_window_minutes(result)
    assert list(duration) == [0.0, 0.0]
    assert list(start) == [1, -1]
    assert list(end) == [1, -1]


def test_passing_mask_duration_threshold():
    duration = np.array([0.0, 4.99, 5.0, 20.0])
    mask = passing_mask_duration(duration, min_clear_minutes=5.0)
    assert list(mask) == [False, False, True, True]
