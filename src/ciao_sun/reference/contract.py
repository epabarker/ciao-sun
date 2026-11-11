"""The Query -> Answer contract (spec #27, "The Query -> Answer contract").

Fields are snake_case here and camelCase in JSON; `Query.from_json` and
`Answer.to_json` are the only places that translate. Every time in an Answer
is an ISO 8601 string with the query time zone's offset, on a whole minute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

WindowName = Literal["morning", "evening"]
Sky = Literal["clear", "partly", "overcast"]
Status = Literal["ranked", "fallback", "lamp-only", "no-evening-window", "not-covered"]

MAX_WALK_CAP_MIN = 20


@dataclass(frozen=True)
class Query:
    window: WindowName
    date: str  # local date, YYYY-MM-DD, Europe/London
    wake_time: str  # local "HH:MM"
    origin_lat: float
    origin_lon: float
    max_walk_min: float  # at most MAX_WALK_CAP_MIN
    sky: Sky
    now: str | None = None  # ISO instant; clips the window start when it falls on `date`

    def __post_init__(self) -> None:
        if not 0 <= self.max_walk_min <= MAX_WALK_CAP_MIN:
            raise ValueError(f"max walk must be 0-{MAX_WALK_CAP_MIN} min, got {self.max_walk_min}")

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Query:
        return cls(
            window=data["window"],
            date=data["date"],
            wake_time=data["wakeTime"],
            origin_lat=data["origin"]["lat"],
            origin_lon=data["origin"]["lon"],
            max_walk_min=data["maxWalkMin"],
            sky=data["sky"],
            now=data.get("now"),
        )

    def to_json(self) -> dict[str, Any]:
        """The Query as a fixture holds it; `from_json` reads it back."""
        out: dict[str, Any] = {
            "window": self.window,
            "date": self.date,
            "wakeTime": self.wake_time,
            "origin": {"lat": self.origin_lat, "lon": self.origin_lon},
            "maxWalkMin": self.max_walk_min,
            "sky": self.sky,
        }
        if self.now is not None:
            out["now"] = self.now
        return out


@dataclass(frozen=True)
class Interval:
    """A run of minutes: `start` is its first minute, `end` the minute after its last."""

    start: str
    end: str

    def to_json(self) -> dict[str, str]:
        return {"start": self.start, "end": self.end}


@dataclass(frozen=True)
class Window:
    """The Morning window or Evening window, and the timeline axis to draw it on.

    The window holds the minutes from `start` up to, not including, `end`.
    """

    start: str
    end: str
    axis_start: str
    axis_end: str

    def to_json(self) -> dict[str, str]:
        return {
            "start": self.start,
            "end": self.end,
            "axisStart": self.axis_start,
            "axisEnd": self.axis_end,
        }


@dataclass(frozen=True)
class Spot:
    candidate_id: str  # "<tile grid ref>/<Candidate index in that tile>"
    name: str  # Spot name
    lat: float
    lon: float
    walk_metres: int  # whole metres; the ranking's tie-break
    walk_min: float  # walk_metres at the walking speed
    leave_by: str
    sun_intervals: tuple[Interval, ...]  # sun in view, within the window
    low_sun_intervals: tuple[Interval, ...]  # the part of those at 0-30 degrees
    sun_minutes: int
    low_sun_minutes: float  # to 0.01 min; taper-weighted in the morning
    sky_openness: float  # to 0.001
    target_met: bool
    last_sun: str | None = None  # evening
    stay_min: float | None = None  # fallback "stay N min"

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "candidateId": self.candidate_id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "walkMetres": self.walk_metres,
            "walkMin": self.walk_min,
            "leaveBy": self.leave_by,
            "sunIntervals": [i.to_json() for i in self.sun_intervals],
            "lowSunIntervals": [i.to_json() for i in self.low_sun_intervals],
            "sunMinutes": self.sun_minutes,
            "lowSunMinutes": self.low_sun_minutes,
            "skyOpenness": self.sky_openness,
            "targetMet": self.target_met,
        }
        if self.last_sun is not None:
            out["lastSun"] = self.last_sun
        if self.stay_min is not None:
            out["stayMin"] = self.stay_min
        return out


@dataclass(frozen=True)
class Answer:
    status: Status
    spots: tuple[Spot, ...] = ()  # in display order
    window: Window | None = None
    nominal_sunrise: str | None = None
    nominal_sunset: str | None = None
    solar_noon: str | None = None
    duration_target_min: int | None = None
    lamp: bool | None = None  # morning: Nominal sunrise > Wake time + 1 h
    next_outdoor_light: str | None = None  # lamp-only
    nearest_sun_beyond_limit: Spot | None = None  # fallback when the sky isn't overcast

    def to_json(self) -> dict[str, Any]:
        """The JSON a fixture holds and `ciao-sun reference` prints. Unset fields are omitted."""
        out: dict[str, Any] = {"status": self.status}
        if self.window is not None:
            out["window"] = self.window.to_json()
        optional = {
            "nominalSunrise": self.nominal_sunrise,
            "nominalSunset": self.nominal_sunset,
            "solarNoon": self.solar_noon,
            "durationTargetMin": self.duration_target_min,
            "lamp": self.lamp,
            "nextOutdoorLight": self.next_outdoor_light,
        }
        out.update({key: value for key, value in optional.items() if value is not None})
        out["spots"] = [spot.to_json() for spot in self.spots]
        if self.nearest_sun_beyond_limit is not None:
            out["nearestSunBeyondLimit"] = self.nearest_sun_beyond_limit.to_json()
        return out
