"""Golden fixtures: the generator, `ciao-sun reference` and the committed sets (#41).

The synthetic build of `tests/build_world.py` is built once with the synthetic
query set, by the same function that regenerates the committed set. Fixtures
are read back as the JSON documents `docs/fixtures.md` describes.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from ciao_sun.cli import app
from ciao_sun.coverage import Coverage
from ciao_sun.manifest import read_manifest
from ciao_sun.reference import Query, answer
from ciao_sun.reference.fixtures import (
    QuerySetError,
    bristol_query_set,
    parse_query_set,
    read_query_set,
    tiles_touched,
    write_fixtures,
)
from ciao_sun.solar import sun_track
from ciao_sun.tile_codec import encode_tile, read_tile
from tests import synthetic_fixtures

# Rich colours help output on GitHub Actions, splitting option names with escape codes.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Generated:
    def __init__(self, build_dir: Path) -> None:
        self.build_dir = build_dir
        self.index = json.loads((build_dir / "fixtures" / "index.json").read_text())

    def text(self, fixture_id: str) -> str:
        return (self.build_dir / "fixtures" / f"{fixture_id}.json").read_text(encoding="utf-8")

    def fixture(self, fixture_id: str) -> dict[str, Any]:
        document: dict[str, Any] = json.loads(self.text(fixture_id))
        return document


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Generated:
    return Generated(synthetic_fixtures.regenerate(tmp_path_factory.mktemp("synthetic")))


# --- `ciao-sun reference` -------------------------------------------------------


def test_reference_prints_exactly_the_fixture_the_generator_wrote_for_the_query(
    generated: Generated, tmp_path: Path
):
    for line in generated.index["fixtures"]:
        query = tmp_path / f"{line['id']}.query.json"
        query.write_text(json.dumps(generated.fixture(line["id"])["query"]))

        result = CliRunner().invoke(
            app, ["reference", str(query), "--build", str(generated.build_dir)]
        )

        assert result.exit_code == 0, result.output
        assert result.output == generated.text(line["id"]), line["id"]


def test_reference_takes_the_query_as_json_or_from_a_fixture_file(generated: Generated):
    stored = generated.build_dir / "fixtures" / "morning-winter-solstice.json"
    inline = json.dumps(generated.fixture("morning-winter-solstice")["query"])

    for argument in (str(stored), inline):
        result = CliRunner().invoke(
            app, ["reference", argument, "--build", str(generated.build_dir)]
        )
        assert result.exit_code == 0, result.output
        assert result.output == stored.read_text(encoding="utf-8")


def test_reference_refuses_a_malformed_query_without_a_traceback(generated: Generated):
    result = CliRunner().invoke(
        app, ["reference", '{"window": "morning"}', "--build", str(generated.build_dir)]
    )

    assert result.exit_code == 1
    assert "Query" in result.output and "Traceback" not in result.output


def test_reference_help_describes_the_query_and_the_output():
    result = CliRunner().invoke(app, ["reference", "--help"], terminal_width=200)
    assert result.exit_code == 0, result.output
    text = " ".join(_ANSI.sub("", result.output).split())
    for phrase in [
        "--build", "manifest.json", "wakeTime", "maxWalkMin", "origin", "sunTrack",
        "nearBoundary", "not-covered", "docs/fixtures.md",
    ]:  # fmt: skip
        assert phrase in text, f"`reference --help` does not mention {phrase!r}"


# --- What the build writes ------------------------------------------------------


def test_a_build_writes_one_fixture_per_query_of_the_query_set_and_indexes_them(
    generated: Generated,
):
    queries = {entry.id: entry for entry in read_query_set(synthetic_fixtures.QUERIES)}
    written = sorted(path.stem for path in (generated.build_dir / "fixtures").glob("*.json"))

    assert generated.index["format"] == 1
    assert generated.index["build"] == generated.build_dir.name == synthetic_fixtures.BUILD_ID
    assert [line["id"] for line in generated.index["fixtures"]] == list(queries)
    assert written == sorted([*queries, "index"])
    for line in generated.index["fixtures"]:
        fixture = generated.fixture(line["id"])
        assert line["file"] == f"{line['id']}.json"
        assert Query.from_json(fixture["query"]) == queries[line["id"]].query
        assert line["status"] == fixture["answer"]["status"]
        assert line["tiles"] == fixture["tiles"]


def test_a_fixture_holds_the_answer_of_the_reference_over_the_tiles_it_names(
    generated: Generated,
):
    manifest = read_manifest(generated.build_dir)
    coverage = Coverage.from_geojson(manifest["coverage"])
    for line in generated.index["fixtures"]:
        fixture = generated.fixture(line["id"])
        tiles = [
            read_tile(generated.build_dir / "tiles" / f"{ref}.bin") for ref in fixture["tiles"]
        ]

        expected = answer(Query.from_json(fixture["query"]), tiles, coverage).to_json()

        assert fixture["answer"] == expected, line["id"]


def test_a_query_touches_the_tiles_within_a_twenty_minute_walk_of_its_origin(
    generated: Generated,
):
    # Both squares of the synthetic build are within 1,600 m of anywhere in it.
    assert generated.fixture("morning-winter-solstice")["tiles"] == ["ST5773", "ST5873"]

    origin = {"lat": 51.4589122, "lon": -2.6051884}  # easting 358050, northing 173500
    query = Query.from_json(
        {"window": "morning", "date": "2026-06-21", "wakeTime": "07:00", "origin": origin,
         "maxWalkMin": 5, "sky": "clear"}
    )  # fmt: skip
    # ST5673 ends 1,050 m west of the origin and ST5573 2,050 m; ST5875 starts
    # 1,500 m north and ST5876 2,500 m; the corner of ST5675 is 1,831 m away.
    index = ["ST5573", "ST5673", "ST5773", "ST5873", "ST5875", "ST5876", "ST5675"]

    assert tiles_touched(query, index) == ["ST5673", "ST5773", "ST5873", "ST5875"]


def test_an_answer_that_needs_no_tiles_names_none(generated: Generated):
    for fixture_id in ("morning-lamp-only", "evening-no-window", "morning-not-covered"):
        assert generated.fixture(fixture_id)["tiles"] == []


def test_a_fixture_carries_the_sun_track_of_the_query_day_at_its_origin(generated: Generated):
    for fixture_id in ("morning-winter-solstice", "morning-not-covered", "evening-no-window"):
        fixture = generated.fixture(fixture_id)
        query, track = fixture["query"], fixture["sunTrack"]
        reference = sun_track(query["origin"]["lat"], query["origin"]["lon"], query["date"])

        assert track["stepMin"] == 1
        assert pd.Timestamp(track["start"]) == reference.times[0]
        assert len(track["azimuth"]) == len(track["apparentElevation"]) == 1440
        # Stored to 4 decimal places: 200 times finer than the 0.01 degree solar parity.
        assert np.abs(np.array(track["azimuth"]) - reference.azimuth).max() <= 5.1e-5
        assert (
            np.abs(np.array(track["apparentElevation"]) - reference.apparent_elevation).max()
            <= 5.1e-5
        )

    # docs/solar-model.md's worked example is 51.45 N, 2.60 W; the synthetic
    # world is 1 km away, so its solstice track agrees to a few hundredths.
    winter = generated.fixture("morning-winter-solstice")["sunTrack"]
    assert winter["start"] == "2026-12-21T00:00:00+00:00"
    assert winter["azimuth"][8 * 60 + 13] == pytest.approx(128.25, abs=0.05)
    assert winter["apparentElevation"][8 * 60 + 13] == pytest.approx(-0.25, abs=0.05)
    assert generated.fixture("morning-summer-solstice")["sunTrack"]["start"] == (
        "2026-06-21T00:00:00+01:00"
    )


def _gaps(generated: Generated, fixture: dict[str, Any]) -> dict[str, np.ndarray]:
    """|apparent elevation - Horizon profile at the sun's azimuth| at every minute of the
    day, for every Candidate of the fixture's tiles: from the decoded profiles and the
    reference sun track, interpolated by numpy rather than by the scorer."""
    query = fixture["query"]
    track = sun_track(query["origin"]["lat"], query["origin"]["lon"], query["date"])
    sample_azimuths = np.arange(0.0, 360.25, 0.25)
    gaps = {}
    for grid_ref in fixture["tiles"]:
        tile = read_tile(generated.build_dir / "tiles" / f"{grid_ref}.bin")
        for k in range(len(tile.candidates.lat_e7)):
            profile = tile.horizon_profile_degrees(k)
            horizon = np.interp(track.azimuth, sample_azimuths, np.append(profile, profile[0]))
            gaps[f"{grid_ref}/{k}"] = np.abs(track.apparent_elevation - horizon)
    return gaps


def test_near_boundary_minutes_are_those_with_the_sun_within_a_hundredth_of_a_degree_of_a_profile(
    generated: Generated,
):
    listed_somewhere = 0
    for line in generated.index["fixtures"]:
        fixture = generated.fixture(line["id"])
        near = fixture["nearBoundary"]
        assert near["toleranceDeg"] == 0.01
        # Every Candidate of the synthetic build is within the 20 min walk cap.
        gaps = _gaps(generated, fixture)
        assert set(near["candidates"]) <= set(gaps)
        for candidate_id, gap in gaps.items():
            listed = near["candidates"].get(candidate_id, [])
            # A gap within 1e-9 of the tolerance may fall either side.
            assert set(np.flatnonzero(gap < 0.01 - 1e-9)) <= set(listed), line["id"]
            assert set(listed) <= set(np.flatnonzero(gap < 0.01 + 1e-9)), line["id"]
            assert candidate_id not in near["candidates"] or listed, "no empty entries"
        listed_somewhere += len(near["candidates"])

    assert listed_somewhere > 0, "the synthetic set should exercise near-boundary minutes"


def test_near_boundary_also_lists_the_minutes_the_sun_is_at_an_end_of_the_low_sun_band(
    generated: Generated,
):
    seen = 0
    for line in generated.index["fixtures"]:
        fixture = generated.fixture(line["id"])
        query = fixture["query"]
        track = sun_track(query["origin"]["lat"], query["origin"]["lon"], query["date"])
        ends = np.minimum(np.abs(track.apparent_elevation), np.abs(track.apparent_elevation - 30))

        listed = fixture["nearBoundary"]["lowSunBand"]

        assert set(np.flatnonzero(ends < 0.01 - 1e-9)) <= set(listed)
        assert set(listed) <= set(np.flatnonzero(ends < 0.01 + 1e-9))
        seen += len(listed)
    assert seen > 0


# --- The synthetic query set ----------------------------------------------------


def test_every_synthetic_query_gets_the_status_it_is_in_the_set_for(generated: Generated):
    expected = {entry.id: entry.expect for entry in read_query_set(synthetic_fixtures.QUERIES)}
    statuses = {line["id"]: line["status"] for line in generated.index["fixtures"]}

    assert statuses == expected
    assert set(statuses.values()) == {
        "ranked", "fallback", "lamp-only", "no-evening-window", "not-covered",
    }  # fmt: skip


def test_the_synthetic_set_has_each_status_case_of_the_spec(generated: Generated):
    def answer_of(fixture_id: str) -> dict[str, Any]:
        found: dict[str, Any] = generated.fixture(fixture_id)["answer"]
        return found

    overcast = answer_of("morning-overcast-fallback")
    assert overcast["status"] == "fallback" and overcast["durationTargetMin"] == 30
    assert "nearestSunBeyondLimit" not in overcast
    # The walk counts towards the target: stay the rest, in whole minutes rounded up.
    assert overcast["spots"]
    for spot in overcast["spots"]:
        assert spot["stayMin"] == max(math.ceil(30 - spot["walkMin"]), 0)

    no_sun = answer_of("morning-no-sun-in-reach")
    assert no_sun["status"] == "fallback"
    assert [spot["sunMinutes"] for spot in no_sun["spots"]] == [0]
    assert no_sun["nearestSunBeyondLimit"]["sunMinutes"] > 0
    assert no_sun["nearestSunBeyondLimit"]["walkMin"] > 0.1  # beyond the query's max walk

    lamp = answer_of("morning-deep-winter-lamp")
    assert lamp["status"] == "ranked" and lamp["lamp"] is True
    assert answer_of("morning-winter-solstice")["lamp"] is False

    lamp_only = answer_of("morning-lamp-only")
    assert lamp_only["status"] == "lamp-only" and lamp_only["spots"] == []
    assert lamp_only["nextOutdoorLight"] == "2026-12-21T08:13:00+00:00"

    assert answer_of("evening-no-window") == {
        "status": "no-evening-window",
        "nominalSunrise": "2026-12-21T08:13:00+00:00",
        "nominalSunset": "2026-12-21T16:04:00+00:00",
        "solarNoon": "2026-12-21T12:08:00+00:00",
        "spots": [],
    }
    assert answer_of("morning-not-covered") == {"status": "not-covered", "spots": []}


def test_the_synthetic_set_ranks_more_than_one_spot_in_both_windows(generated: Generated):
    for fixture_id in ("morning-deep-winter-lamp", "evening-winter-solstice"):
        spots = generated.fixture(fixture_id)["answer"]["spots"]
        assert len(spots) == 2
        assert spots[0]["lowSunMinutes"] > spots[1]["lowSunMinutes"]
        assert spots[0]["name"] != spots[1]["name"]
    evening = generated.fixture("evening-winter-solstice")["answer"]["spots"]
    assert all("lastSun" in spot for spot in evening)


# --- Query sets -----------------------------------------------------------------


def _set(*lines: dict[str, Any]) -> dict[str, Any]:
    return {"queries": list(lines)}


_QUERY = {
    "window": "morning", "date": "2026-12-21", "wakeTime": "07:00",
    "origin": {"lat": 51.45, "lon": -2.6}, "maxWalkMin": 15, "sky": "clear",
}  # fmt: skip


def test_a_query_set_is_refused_when_an_id_repeats_or_would_not_name_a_file():
    with pytest.raises(QuerySetError, match="twice"):
        parse_query_set(_set({"id": "a", "query": _QUERY}, {"id": "a", "query": _QUERY}))
    for bad in ("Morning", "a/b", "", "index"):
        with pytest.raises(QuerySetError, match="id"):
            parse_query_set(_set({"id": bad, "query": _QUERY}))


def test_a_query_set_is_refused_when_a_query_or_its_expected_status_is_not_valid():
    with pytest.raises(QuerySetError, match="winter.*Query"):
        parse_query_set(_set({"id": "winter", "query": {**_QUERY, "maxWalkMin": 25}}))
    with pytest.raises(QuerySetError, match="winter.*Query"):
        parse_query_set(_set({"id": "winter", "query": {"window": "morning"}}))
    with pytest.raises(QuerySetError, match="status"):
        parse_query_set(_set({"id": "winter", "expect": "sunny", "query": _QUERY}))


def test_a_status_the_query_set_did_not_expect_is_reported_and_the_fixture_still_written(
    generated: Generated, tmp_path: Path
):
    copy = Path(shutil.copytree(generated.build_dir, tmp_path / generated.build_dir.name))
    (entry,) = parse_query_set(
        _set({"id": "surprise", "expect": "fallback",
              "query": generated.fixture("morning-winter-solstice")["query"]})
    )  # fmt: skip
    reported: list[str] = []

    write_fixtures(copy, [entry], reported.append)

    assert any("surprise" in m and "ranked" in m and "fallback" in m for m in reported)
    # The old fixtures are gone: `fixtures/` is exactly the query set's.
    assert sorted(p.name for p in (copy / "fixtures").iterdir()) == ["index.json", "surprise.json"]
    assert json.loads((copy / "fixtures" / "surprise.json").read_text()) == generated.fixture(
        "morning-winter-solstice"
    )


# --- The committed synthetic set ------------------------------------------------

COMMITTED = synthetic_fixtures.SYNTHETIC / "f1" / synthetic_fixtures.BUILD_ID


def test_the_committed_synthetic_set_is_self_contained():
    manifest = read_manifest(COMMITTED)
    index = json.loads((COMMITTED / "fixtures" / "index.json").read_text())

    assert manifest["build"] == index["build"] == synthetic_fixtures.BUILD_ID
    assert sorted(path.stem for path in (COMMITTED / "tiles").glob("*.bin")) == sorted(
        manifest["tiles"]
    )
    for grid_ref, line in manifest["tiles"].items():
        data = (COMMITTED / "tiles" / f"{grid_ref}.bin").read_bytes()
        assert hashlib.sha256(data).hexdigest() == line["sha256"]
    for line in index["fixtures"]:
        assert (COMMITTED / "fixtures" / line["file"]).is_file()
        assert set(line["tiles"]) <= set(manifest["tiles"])


def test_the_committed_synthetic_set_is_what_the_one_command_regenerates(generated: Generated):
    # Compared as decoded content, not bytes: gzip output and the hashes of the
    # synthetic input zips may differ between machines.
    committed = Generated(COMMITTED)
    stale = "run `uv run python -m tests.synthetic_fixtures` and commit fixtures/synthetic"

    assert committed.index == generated.index, stale
    assert sorted(read_manifest(COMMITTED)["tiles"]) == ["ST5773", "ST5873"]
    for grid_ref in ("ST5773", "ST5873"):
        ours = read_tile(COMMITTED / "tiles" / f"{grid_ref}.bin")
        theirs = read_tile(generated.build_dir / "tiles" / f"{grid_ref}.bin")
        assert encode_tile(ours) == encode_tile(theirs), stale
    for line in generated.index["fixtures"]:
        ours, theirs = committed.fixture(line["id"]), generated.fixture(line["id"])
        for part in ("query", "tiles", "answer", "nearBoundary"):
            assert ours[part] == theirs[part], f"{line['id']} {part}: {stale}"
        for series in ("azimuth", "apparentElevation"):
            assert np.allclose(
                ours["sunTrack"][series], theirs["sunTrack"][series], rtol=0, atol=1.5e-4
            ), stale


def test_the_committed_decoded_tiles_are_what_the_reader_makes_of_the_committed_tiles():
    committed = json.loads(synthetic_fixtures.DECODED_TILES.read_text(encoding="utf-8"))

    assert committed == synthetic_fixtures.decoded_tiles(COMMITTED), (
        "run `uv run python -m tests.synthetic_fixtures` and commit fixtures/synthetic"
    )


# --- The Bristol query set ------------------------------------------------------


def test_the_bristol_query_set_covers_every_date_class_and_both_windows():
    queries = [entry.query for entry in bristol_query_set()]
    dates = {(query.date[5:], query.window) for query in queries}

    for window in ("morning", "evening"):
        assert ("06-21", window) in dates, "summer solstice"
        assert ("12-21", window) in dates, "winter solstice"
        assert ("03-20", window) in dates, "March equinox"
        assert ("09-23", window) in dates, "September equinox"
        assert ("01-15", window) in dates, "deep winter"
    assert {query.sky for query in queries} == {"clear", "partly", "overcast"}
    origins = {(query.origin_lat, query.origin_lon) for query in queries}
    assert len(origins) >= 5, "spots across Bristol"


def test_the_bristol_query_set_has_a_query_for_every_status_case():
    queries = {entry.id: entry for entry in bristol_query_set()}

    assert all(entry.expect is not None for entry in queries.values())
    assert {entry.expect for entry in queries.values()} == {
        "ranked", "fallback", "lamp-only", "no-evening-window", "not-covered",
    }  # fmt: skip

    # The cases the sun alone decides hold on any build.
    assert answer(queries["morning-lamp-only"].query, []).status == "lamp-only"
    assert answer(queries["evening-no-window"].query, []).status == "no-evening-window"
    lamp = queries["morning-winter-solstice-lamp"].query
    sunrise = sun_track(lamp.origin_lat, lamp.origin_lon, lamp.date).nominal_sunrise
    assert sunrise is not None
    wake = pd.Timestamp(f"{lamp.date} {lamp.wake_time}", tz="Europe/London")
    assert wake + pd.Timedelta(hours=1) < sunrise < wake + pd.Timedelta(hours=3)

    assert queries["morning-overcast-fallback"].query.sky == "overcast"
    assert queries["morning-overcast-fallback"].expect == "fallback"
    # No sun in reach: a clear sky, and a short walk from a terraced street.
    no_sun = queries["morning-no-sun-in-reach"]
    assert no_sun.expect == "fallback" and no_sun.query.sky == "clear"
    # Bath, 17 km outside the Bristol city boundary.
    assert queries["morning-not-covered"].expect == "not-covered"
    assert queries["morning-not-covered"].query.origin_lon > -2.45
