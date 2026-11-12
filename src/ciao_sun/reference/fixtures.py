"""Golden fixtures: a query set run through the reference over one build directory.

`docs/fixtures.md` specifies the fixture JSON, the query set file, the layout
under a build's `fixtures/` and the parity tolerances the JS scorer is held to.
In short:

    <build>/fixtures/index.json     every fixture: id, status, the tiles it touches
    <build>/fixtures/<id>.json      {"query", "tiles", "answer", "sunTrack", "nearBoundary"}

`fixture` is the one function behind both `ciao-sun reference` and the files
`write_fixtures` puts in a build directory, so the two cannot differ. It reads
only the tiles the query touches and always passes the manifest's coverage
polygon, so an origin outside it is `not-covered`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, get_args

import numpy as np

from ciao_sun.coverage import Coverage
from ciao_sun.crs import WGS84_TO_BNG
from ciao_sun.manifest import read_manifest, tile_file
from ciao_sun.reference.contract import MAX_WALK_CAP_MIN, Query, Status
from ciao_sun.reference.scorer import answer
from ciao_sun.reference.sunview import LOW_SUN_MAX_DEG, LOW_SUN_MIN_DEG, horizon_at_sun
from ciao_sun.reference.windows import TIME_ZONE
from ciao_sun.reference.world import WALK_SPEED_M_PER_MIN, join_tiles, walk_metres
from ciao_sun.report import silent
from ciao_sun.solar import SunTrack, sun_track
from ciao_sun.tile_codec import STORAGE_MIN_DEG, Tile, read_tile
from ciao_sun.tiles import KM, grid_ref_origin

FIXTURES_DIR = "fixtures"
INDEX_NAME = "index.json"

# A minute is near-boundary when the sun is within this of the threshold it is tested against.
NEAR_BOUNDARY_DEG = 0.01
# Decimal places of the sun track's degrees: far inside the 0.01 degree solar parity.
TRACK_DECIMALS = 4
# A query touches the tiles within the furthest walk any Answer reaches.
TILE_REACH_M = MAX_WALK_CAP_MIN * WALK_SPEED_M_PER_MIN

_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_CHUNK = 2000  # Candidates per pass over the day, to bound memory on a real build


class QuerySetError(ValueError):
    """The query set file is not usable."""


@dataclass(frozen=True)
class SetQuery:
    """One line of a query set: a Query under the id its fixture file is named by."""

    id: str
    query: Query
    expect: Status | None = None  # the status the query is in the set to exercise


def parse_query_set(document: object) -> tuple[SetQuery, ...]:
    """The queries of a query set document, in order. Raises QuerySetError."""
    if not isinstance(document, dict) or not isinstance(document.get("queries"), list):
        raise QuerySetError('A query set is an object with a "queries" list.')
    queries: list[SetQuery] = []
    for position, line in enumerate(document["queries"]):
        where = f"queries[{position}]"
        if not isinstance(line, dict) or not isinstance(line.get("id"), str):
            raise QuerySetError(f'{where}: needs an "id".')
        where = f"{where} ({line['id']})"
        if not _ID.fullmatch(line["id"]) or line["id"] == Path(INDEX_NAME).stem:
            raise QuerySetError(f"{where}: an id is lower-case words joined by hyphens.")
        if any(line["id"] == earlier.id for earlier in queries):
            raise QuerySetError(f"{where}: the id is used twice.")
        expect = line.get("expect")
        if expect is not None and expect not in get_args(Status):
            raise QuerySetError(f"{where}: {expect!r} is not an Answer status.")
        try:
            query = Query.from_json(line["query"])
        except (KeyError, TypeError, ValueError) as exc:
            raise QuerySetError(f"{where}: not a Query: {exc!r}") from exc
        queries.append(SetQuery(id=line["id"], query=query, expect=expect))
    return tuple(queries)


def read_query_set(path: Path) -> tuple[SetQuery, ...]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QuerySetError(f"Cannot read query set {path}: {exc}") from exc
    try:
        return parse_query_set(document)
    except QuerySetError as exc:
        raise QuerySetError(f"{path}: {exc}") from exc


def bristol_query_set() -> tuple[SetQuery, ...]:
    """The committed Bristol query set, `reference/bristol_queries.json`: `build`'s default."""
    text = resources.files("ciao_sun.reference").joinpath("bristol_queries.json").read_text("utf-8")
    return parse_query_set(json.loads(text))


def tiles_touched(query: Query, tile_index: Sequence[str]) -> list[str]:
    """The grid refs of `tile_index` whose 1 km square is within 1,600 m of the origin.

    1,600 m is the 20 min walk cap at the walking speed: no Answer names a spot
    further than that. Distances are on the National Grid.
    """
    x, y = WGS84_TO_BNG.transform(query.origin_lon, query.origin_lat)
    touched = []
    for grid_ref in sorted(tile_index):
        west, south = grid_ref_origin(grid_ref)
        dx = max(west - x, 0.0, x - (west + KM))
        dy = max(south - y, 0.0, y - (south + KM))
        if dx * dx + dy * dy <= TILE_REACH_M * TILE_REACH_M:
            touched.append(grid_ref)
    return touched


def fixture(query: Query, build_dir: Path) -> dict[str, Any]:
    """The fixture for one Query over a build directory (`docs/fixtures.md`)."""
    manifest = read_manifest(build_dir)
    coverage = Coverage.from_geojson(manifest["coverage"])
    covered = coverage.contains(query.origin_lat, query.origin_lon)
    grid_refs = tiles_touched(query, list(manifest["tiles"])) if covered else []
    tiles = [read_tile(tile_file(build_dir, query.window, grid_ref)) for grid_ref in grid_refs]

    result = answer(query, tiles, coverage)
    track = sun_track(query.origin_lat, query.origin_lon, query.date, tz=TIME_ZONE)
    ranked_over_tiles = result.window is not None
    return {
        "query": query.to_json(),
        # An Answer without a window is decided by the sun alone.
        "tiles": grid_refs if ranked_over_tiles else [],
        "answer": result.to_json(),
        "sunTrack": {
            "start": track.times[0].isoformat(),
            "stepMin": 1,
            "azimuth": np.round(track.azimuth, TRACK_DECIMALS).tolist(),
            "apparentElevation": np.round(track.apparent_elevation, TRACK_DECIMALS).tolist(),
        },
        "nearBoundary": {
            "toleranceDeg": NEAR_BOUNDARY_DEG,
            "candidates": _near_horizon(query, tiles, track) if ranked_over_tiles else {},
            "lowSunBand": _near_low_sun_band(track),
        },
    }


def _near_horizon(query: Query, tiles: Sequence[Tile], track: SunTrack) -> dict[str, list[int]]:
    """Per Candidate within the walk cap, the minutes the sun is within the tolerance
    of its Horizon profile. Candidates with no such minute are left out.

    Only the minutes the window's tiles hold the profile for are looked at: the
    morning or the afternoon, while the sun stands at -2 degrees or higher (no
    profile is lower). They are every minute either scorer reads the profile.
    """
    world = join_tiles(tiles)
    walks = walk_metres(world, query.origin_lat, query.origin_lon, TILE_REACH_M)
    within_cap = np.flatnonzero(walks >= 0)
    noon = int(np.argmax(track.apparent_elevation))
    half = slice(0, noon) if query.window == "morning" else slice(noon, len(track.times))
    looked_at = np.zeros(len(track.times), dtype=bool)
    looked_at[half] = track.apparent_elevation[half] >= STORAGE_MIN_DEG
    near: dict[str, list[int]] = {}
    if not looked_at.any():
        return near
    first_minute = int(np.argmax(looked_at))
    last_minute = len(looked_at) - int(np.argmax(looked_at[::-1]))
    for first in range(0, within_cap.size, _CHUNK):
        chunk = within_cap[first : first + _CHUNK]
        horizon = horizon_at_sun(world.profile_codes[chunk], track, first_minute, last_minute)
        elevation = track.apparent_elevation[first_minute:last_minute]
        close = np.abs(elevation - horizon) < NEAR_BOUNDARY_DEG
        for row in np.flatnonzero(close.any(axis=1)):
            near[world.candidate_id(int(chunk[row]))] = (
                first_minute + np.flatnonzero(close[row])
            ).tolist()
    return near


def _near_low_sun_band(track: SunTrack) -> list[int]:
    """The minutes of the day the sun is within the tolerance of an end of the 0-30 degree band."""
    elevation = track.apparent_elevation
    close = (np.abs(elevation - LOW_SUN_MIN_DEG) < NEAR_BOUNDARY_DEG) | (
        np.abs(elevation - LOW_SUN_MAX_DEG) < NEAR_BOUNDARY_DEG
    )
    minutes: list[int] = np.flatnonzero(close).tolist()
    return minutes


def fixture_text(document: dict[str, Any]) -> str:
    """A fixture exactly as it is stored and printed: compact JSON on one line."""
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"


def write_fixtures(
    build_dir: Path, queries: Sequence[SetQuery], report: Callable[[str], None] = silent
) -> Path:
    """Write `fixtures/` into a build directory: one fixture per query, and the index.

    Replaces any `fixtures/` already there. A query whose Answer does not have
    the status it is in the set to exercise is reported, not refused: the
    fixture is still what the reference answers.
    """
    manifest = read_manifest(build_dir)
    directory = build_dir / FIXTURES_DIR
    if directory.exists():
        for stale in directory.glob("*.json"):
            stale.unlink()
    directory.mkdir(exist_ok=True)

    lines = []
    for entry in queries:
        document = fixture(entry.query, build_dir)
        (directory / f"{entry.id}.json").write_text(fixture_text(document), encoding="utf-8")
        status = document["answer"]["status"]
        if entry.expect is not None and status != entry.expect:
            report(f"fixture {entry.id}: status is {status}, the query set expects {entry.expect}")
        lines.append(
            {
                "id": entry.id,
                "file": f"{entry.id}.json",
                "status": status,
                "tiles": document["tiles"],
            }
        )
    index = {"format": manifest["format"], "build": manifest["build"], "fixtures": lines}
    (directory / INDEX_NAME).write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    report(f"fixtures: {len(lines)} written to {directory}")
    return directory
