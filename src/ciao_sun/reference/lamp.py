"""The lamp message, and the lamp-only Answer for a Morning window that holds no minutes."""

from __future__ import annotations

import pandas as pd

from ciao_sun.reference.contract import Answer, Query
from ciao_sun.reference.windows import clock, minute_of, now_minute, wake_minute
from ciao_sun.solar import SunTrack, sun_track

LAMP_AFTER_WAKE_MIN = 60  # the lamp is suggested when Nominal sunrise is later than this


def lamp(query: Query, track: SunTrack) -> bool:
    """Whether Nominal sunrise is more than 1 h after Wake time, both as whole minutes."""
    if track.nominal_sunrise is None:
        return True
    sunrise = minute_of(track, track.nominal_sunrise)
    return sunrise > wake_minute(query, track) + LAMP_AFTER_WAKE_MIN


def lamp_only(query: Query, track: SunTrack) -> Answer:
    """The Answer when the Morning window is empty: no list and no window.

    The window is empty when it ends by Nominal sunrise, or when `now` is at
    or past its end. `lamp` follows its own rule either way, so it is False
    for a window that is merely over on a morning that had early sun.
    """
    return Answer(
        status="lamp-only",
        lamp=lamp(query, track),
        next_outdoor_light=next_outdoor_light(query, track),
    )


def next_outdoor_light(query: Query, track: SunTrack) -> str | None:
    """The first minute, from the later of Wake time and now, with the sun nominally up.

    That is Nominal sunrise when it is still to come; the minute itself when
    it falls from Nominal sunrise up to, not including, Nominal sunset; and
    otherwise the next day's Nominal sunrise. None if the sun does not rise
    then either.
    """
    wake, now = wake_minute(query, track), now_minute(query, track)
    earliest = wake if now is None else max(wake, now)
    if track.nominal_sunrise is not None:
        sunrise = minute_of(track, track.nominal_sunrise)
        if earliest <= sunrise:
            return clock(track, sunrise)
        if track.nominal_sunset is None or earliest < minute_of(track, track.nominal_sunset):
            return clock(track, earliest)
    next_date = (pd.Timestamp(query.date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow = sun_track(query.origin_lat, query.origin_lon, next_date, tz=str(track.times.tz))
    if tomorrow.nominal_sunrise is None:
        return None
    return clock(tomorrow, minute_of(tomorrow, tomorrow.nominal_sunrise))
