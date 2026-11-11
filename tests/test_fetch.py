"""`ciao-sun fetch` against a fake HTTP client: no real EA, OS, Geofabrik or Protomaps traffic.

Everything is observed through `fetch()`, the lockfile it writes and the files
the lockfile points at. Time is a fake clock that only `sleep` advances.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pyproj import Transformer

from ciao_sun.basemap import tiles_covering
from ciao_sun.coverage import Coverage
from ciao_sun.fetch import (
    FetchError,
    HashMismatchError,
    Response,
    TransportError,
    fetch,
    read_lockfile,
)
from ciao_sun.pmtiles import Archive
from tests import basemap_world as protomaps

EA = "https://environment.data.gov.uk/tiles/collections/survey"
DSM_URL = f"{EA}/lidar_composite_last_return_dsm/2022/1/ST5570"
DTM_URL = f"{EA}/lidar_composite_dtm/2022/1/ST5570"
FIRST_URL = f"{EA}/lidar_composite_first_return_dsm/2022/1/ST5570"
T50_META_URL = "https://api.os.uk/downloads/v1/products/Terrain50"
T50_URL = (
    "https://api.os.uk/downloads/v1/products/Terrain50/downloads"
    "?area=GB&format=ASCII+Grid+and+GML+%28Grid%29&redirect"
)
OSM_URL = "https://download.geofabrik.de/europe/united-kingdom/england-261110.osm.pbf"

_BNG_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


def _coverage_in_st5570() -> Coverage:
    """A 100 m square at the centre of 5 km tile ST5570."""
    cx, cy, h = 357_500.0, 172_500.0, 50.0
    corners = [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]
    ring = [list(_BNG_TO_WGS84.transform(x, y)) for x, y in corners]
    ring.append(ring[0])
    return Coverage.from_geojson({"type": "Polygon", "coordinates": [ring]})


PROTOMAPS_BUILD = protomaps.archive_bytes(_coverage_in_st5570().bounds_wgs84())


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


Handler = Callable[[Mapping[str, str]], Response]


class FakeWeb:
    """A fake HTTP client plus the fake clock it timestamps requests with."""

    def __init__(self) -> None:
        self.now = 1_000.0
        self.sleeps: list[float] = []
        self.requests: list[tuple[float, str, dict[str, str]]] = []
        self.bodies: dict[str, bytes] = {
            DSM_URL: b"dsm-zip-bytes " * 40,
            DTM_URL: b"dtm-zip-bytes " * 40,
            FIRST_URL: b"first-return-zip-bytes " * 40,
            T50_META_URL: json.dumps({"id": "Terrain50", "version": "2026-07"}).encode(),
            T50_URL: b"terrain-50-gb-zip " * 40,
            OSM_URL: b"osm-pbf-bytes " * 40,
            protomaps.BUILDS_URL: protomaps.builds_json(),
            protomaps.ARCHIVE_URL: PROTOMAPS_BUILD,
        }
        self.scripted: dict[str, list[Handler]] = {}
        self.honour_range = True
        self.protomaps_honours_range = True

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def get(self, url: str, headers: Mapping[str, str]) -> Response:
        self.requests.append((self.now, url, dict(headers)))
        queue = self.scripted.get(url)
        if queue:
            return queue.pop(0)(headers)
        return self.serve(url, headers)

    def serve(self, url: str, headers: Mapping[str, str]) -> Response:
        if url not in self.bodies:
            return Response(404, iter(()))
        body = self.bodies[url]
        rng = headers.get("Range")
        if url == protomaps.ARCHIVE_URL:
            return protomaps.serve_range(body, headers if self.protomaps_honours_range else {})
        if rng and self.honour_range:
            return protomaps.serve_range(body, headers)
        return Response(200, iter([body[:100], body[100:]]))

    def urls(self) -> list[str]:
        return [url for _, url, _ in self.requests]

    def drop_after(self, url: str, n_bytes: int, times: int = 1) -> None:
        """The next `times` requests for `url` die after `n_bytes` of what they'd serve."""

        def handler(headers: Mapping[str, str]) -> Response:
            whole = b"".join(self.serve(url, headers).chunks)
            status = 206 if headers.get("Range") and self.honour_range else 200

            def chunks() -> Iterator[bytes]:
                yield whole[:n_bytes]
                raise TransportError("connection reset")

            return Response(status, chunks())

        self.scripted.setdefault(url, []).extend([handler] * times)


def _run(web: FakeWeb, root: Path, **kwargs: object):
    options: dict[str, object] = {"osm_date": "261110", "margin_m": 0.0}
    options.update(kwargs)
    return fetch(
        _coverage_in_st5570(),
        root,
        client=web,
        clock=web.clock,
        sleep=web.sleep,
        now=lambda: datetime(2026, 11, 11, 9, 30, tzinfo=UTC),
        **options,  # type: ignore[arg-type]
    )


@pytest.fixture
def web() -> FakeWeb:
    return FakeWeb()


# --- what gets fetched, and the lockfile ------------------------------------


def test_fetch_downloads_all_three_ea_products_terrain_50_and_the_osm_extract(web, tmp_path):
    _run(web, tmp_path)

    lock = read_lockfile(tmp_path)
    by_kind = {entry.kind: entry for entry in lock.inputs}
    assert sorted(by_kind) == ["basemap", "dsm", "dtm", "first_return_dsm", "osm", "terrain50"]
    for kind, url in [
        ("dsm", DSM_URL), ("dtm", DTM_URL), ("first_return_dsm", FIRST_URL),
        ("terrain50", T50_URL), ("osm", OSM_URL),
    ]:
        entry = by_kind[kind]
        assert entry.url == url
        assert lock.path_of(entry).read_bytes() == web.bodies[url]
        assert entry.sha256 == _sha(web.bodies[url])
        assert entry.bytes == len(web.bodies[url])


def test_lockfile_records_source_version_and_retrieval_time_for_every_input(web, tmp_path):
    _run(web, tmp_path)

    raw = json.loads((tmp_path / "fetch.lock.json").read_text())
    versions = {item["kind"]: item["version"] for item in raw["inputs"]}
    assert versions == {
        "dsm": "2022", "dtm": "2022", "first_return_dsm": "2022",
        "terrain50": "2026-07", "osm": "261110", "basemap": "20260811",
    }
    for item in raw["inputs"]:
        assert item["source"]
        assert len(item["sha256"]) == 64
        assert item["fetched_at"] == "2026-11-11T09:30:00Z"
    tiles = {item["kind"]: item["tile"] for item in raw["inputs"]}
    assert tiles["dsm"] == tiles["dtm"] == tiles["first_return_dsm"] == "ST5570"
    assert tiles["terrain50"] is None and tiles["osm"] is None


def test_inputs_are_cached_per_source_tile_and_version(web, tmp_path):
    _run(web, tmp_path)

    lock = read_lockfile(tmp_path)
    paths = {entry.kind: entry.path for entry in lock.inputs}
    assert paths == {
        "dsm": "ea/lidar_composite_last_return_dsm/2022/ST5570.zip",
        "dtm": "ea/lidar_composite_dtm/2022/ST5570.zip",
        "first_return_dsm": "ea/lidar_composite_first_return_dsm/2022/ST5570.zip",
        "terrain50": "terrain50/2026-07/terr50_gagg_gb.zip",
        "osm": "osm/europe-united-kingdom-england-261110.osm.pbf",
        "basemap": "basemap/20260811/z10-15_x16146-16146_y10904-10904.pmtiles",
    }


def test_lockfile_carries_the_coverage_and_margin_the_inputs_were_fetched_for(web, tmp_path):
    _run(web, tmp_path)

    lock = read_lockfile(tmp_path)
    assert lock.margin_m == 0.0
    assert lock.coverage == _coverage_in_st5570()


def test_default_margin_fetches_ea_tiles_within_3_km_of_the_coverage(web, tmp_path):
    for tile in ["ST5070", "ST5565", "ST5575", "ST6070"]:
        for product in ["last_return_dsm", "dtm", "first_return_dsm"]:
            web.bodies[f"{EA}/lidar_composite_{product}/2022/1/{tile}"] = tile.encode()

    fetch(_coverage_in_st5570(), tmp_path, osm_date="261110", client=web,
          clock=web.clock, sleep=web.sleep)

    lock = read_lockfile(tmp_path)
    assert sorted(e.tile for e in lock.inputs if e.kind == "dsm") == [
        "ST5070", "ST5565", "ST5570", "ST5575", "ST6070",
    ]
    assert lock.margin_m == 3000.0


def test_pinned_terrain_50_version_is_confirmed_against_what_os_serves(web, tmp_path):
    with pytest.raises(FetchError, match="2026-07"):
        _run(web, tmp_path, terrain50_version="2025-07")

    assert T50_URL not in web.urls()


def test_pinned_terrain_50_version_already_cached_is_used_without_asking_os(web, tmp_path):
    _run(web, tmp_path)
    web.bodies[T50_META_URL] = json.dumps({"id": "Terrain50", "version": "2027-07"}).encode()
    web.requests.clear()

    _run(web, tmp_path, terrain50_version="2026-07")

    assert web.requests == []
    (entry,) = [e for e in read_lockfile(tmp_path).inputs if e.kind == "terrain50"]
    assert entry.version == "2026-07"


def test_ea_tile_the_server_does_not_publish_is_recorded_as_absent(web, tmp_path):
    del web.bodies[FIRST_URL]

    _run(web, tmp_path)

    (entry,) = [e for e in read_lockfile(tmp_path).inputs if e.kind == "first_return_dsm"]
    assert entry.absent and entry.sha256 is None
    assert not (tmp_path / entry.path).exists()


def test_missing_terrain_50_or_osm_is_an_error_not_an_absence(web, tmp_path):
    del web.bodies[OSM_URL]

    with pytest.raises(FetchError, match="404"):
        _run(web, tmp_path)


# --- throttling and backoff ----------------------------------------------------


def test_requests_are_spaced_at_least_a_second_apart(web, tmp_path):
    _run(web, tmp_path)

    times = [t for t, _, _ in web.requests]
    assert len(times) > 6  # six downloads, then the basemap's byte ranges
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    assert min(gaps) >= 1.0


def test_a_403_backs_off_before_retrying_and_then_carries_on(web, tmp_path):
    web.scripted[DTM_URL] = [lambda headers: Response(403, iter(()))] * 2

    _run(web, tmp_path)

    dtm_times = [t for t, url, _ in web.requests if url == DTM_URL]
    assert len(dtm_times) == 3
    first_wait, second_wait = dtm_times[1] - dtm_times[0], dtm_times[2] - dtm_times[1]
    assert first_wait >= 30.0
    assert second_wait >= 2 * first_wait
    (entry,) = [e for e in read_lockfile(tmp_path).inputs if e.kind == "dtm"]
    assert entry.sha256 == _sha(web.bodies[DTM_URL])


def test_endless_403s_give_up_with_an_error(web, tmp_path):
    web.scripted[DTM_URL] = [lambda headers: Response(403, iter(()))] * 50

    with pytest.raises(FetchError, match="403"):
        _run(web, tmp_path)

    assert not (tmp_path / "fetch.lock.json").exists()


# --- resume ----------------------------------------------------------------------


def test_a_dropped_connection_resumes_from_the_bytes_already_received(web, tmp_path):
    web.drop_after(OSM_URL, 137)

    _run(web, tmp_path)

    osm_requests = [headers for _, url, headers in web.requests if url == OSM_URL]
    assert len(osm_requests) == 2
    assert "Range" not in osm_requests[0]
    assert osm_requests[1]["Range"] == "bytes=137-"
    (entry,) = [e for e in read_lockfile(tmp_path).inputs if e.kind == "osm"]
    assert (tmp_path / entry.path).read_bytes() == web.bodies[OSM_URL]


def test_a_later_run_resumes_a_download_an_earlier_run_gave_up_on(web, tmp_path):
    web.drop_after(OSM_URL, 60, times=1)
    web.drop_after(OSM_URL, 0, times=50)
    with pytest.raises(FetchError, match="dropped"):
        _run(web, tmp_path)
    web.scripted.clear()
    web.requests.clear()

    _run(web, tmp_path)

    # The basemap comes after the OSM extract, so the first run never reached it.
    assert [
        (url, headers) for _, url, headers in web.requests if "protomaps" not in url
    ] == [(OSM_URL, {"Range": "bytes=60-"})]
    (entry,) = [e for e in read_lockfile(tmp_path).inputs if e.kind == "osm"]
    assert (tmp_path / entry.path).read_bytes() == web.bodies[OSM_URL]


def test_a_server_that_ignores_range_restarts_the_file_instead_of_corrupting_it(web, tmp_path):
    web.honour_range = False
    web.drop_after(DSM_URL, 137)

    _run(web, tmp_path)

    (entry,) = [e for e in read_lockfile(tmp_path).inputs if e.kind == "dsm"]
    assert (tmp_path / entry.path).read_bytes() == web.bodies[DSM_URL]


# --- idempotence and hash verification -----------------------------------------------


def test_a_second_run_makes_no_requests_and_leaves_the_lockfile_alone(web, tmp_path):
    _run(web, tmp_path)
    before = (tmp_path / "fetch.lock.json").read_bytes()
    web.requests.clear()

    fetch(_coverage_in_st5570(), tmp_path, osm_date="261110", margin_m=0.0, client=web,
          clock=web.clock, sleep=web.sleep,
          now=lambda: datetime(2027, 1, 1, tzinfo=UTC))

    assert web.requests == []
    assert (tmp_path / "fetch.lock.json").read_bytes() == before


def test_a_second_run_does_not_ask_again_for_an_absent_ea_tile(web, tmp_path):
    del web.bodies[FIRST_URL]
    _run(web, tmp_path)
    web.requests.clear()

    _run(web, tmp_path)

    assert web.requests == []


def test_a_download_that_differs_from_the_lockfile_hash_fails_loudly(web, tmp_path):
    _run(web, tmp_path)
    (entry,) = [e for e in read_lockfile(tmp_path).inputs if e.kind == "dtm"]
    (tmp_path / entry.path).unlink()
    web.bodies[DTM_URL] = b"upstream quietly republished this tile"

    with pytest.raises(HashMismatchError) as excinfo:
        _run(web, tmp_path)

    assert entry.path in str(excinfo.value)
    assert entry.sha256 in str(excinfo.value)
    assert _sha(web.bodies[DTM_URL]) in str(excinfo.value)
    assert not (tmp_path / entry.path).exists()
    assert read_lockfile(tmp_path).inputs[0].fetched_at  # the old lockfile survives


def test_a_cached_file_that_no_longer_matches_the_lockfile_fails_loudly(web, tmp_path):
    _run(web, tmp_path)
    (entry,) = [e for e in read_lockfile(tmp_path).inputs if e.kind == "osm"]
    (tmp_path / entry.path).write_bytes(b"bit rot")
    web.requests.clear()

    with pytest.raises(HashMismatchError):
        _run(web, tmp_path)

    assert web.requests == []


def test_changing_the_osm_date_fetches_only_the_new_extract(web, tmp_path):
    _run(web, tmp_path)
    newer = OSM_URL.replace("261110", "261201")
    web.bodies[newer] = b"a newer extract"
    web.requests.clear()

    _run(web, tmp_path, osm_date="261201")

    assert web.urls() == [newer]
    (entry,) = [e for e in read_lockfile(tmp_path).inputs if e.kind == "osm"]
    assert entry.version == "261201"
    assert entry.sha256 == _sha(b"a newer extract")


# --- the basemap ------------------------------------------------------------------


def _basemap_entry(root: Path):
    (entry,) = [e for e in read_lockfile(root).inputs if e.kind == "basemap"]
    return entry


def test_fetch_cuts_the_coverages_basemap_tiles_from_the_pinned_protomaps_build(web, tmp_path):
    _run(web, tmp_path)

    entry = _basemap_entry(tmp_path)
    assert entry.version == "20260811"  # the Protomaps build date
    assert entry.url == "https://build.protomaps.com/20260811.pmtiles"
    assert "Protomaps" in entry.source
    assert entry.path.startswith("basemap/20260811/") and entry.path.endswith(".pmtiles")
    cut = tmp_path / entry.path
    assert entry.sha256 == _sha(cut.read_bytes()) and entry.bytes == cut.stat().st_size
    archive = Archive.open(cut)
    wanted = tiles_covering(_coverage_in_st5570())
    assert len(wanted) >= 6
    for z, x, y in wanted:
        assert archive.tile(z, x, y) is not None


def test_the_protomaps_build_is_only_ever_read_by_byte_range(web, tmp_path):
    _run(web, tmp_path)

    asked = [headers for _, url, headers in web.requests if url == protomaps.ARCHIVE_URL]
    assert asked
    for headers in asked:
        first, _, last = headers["Range"].removeprefix("bytes=").partition("-")
        assert int(first) <= int(last)
    assert len(cut := (tmp_path / _basemap_entry(tmp_path).path).read_bytes()) < len(
        PROTOMAPS_BUILD
    ), len(cut)


def test_a_server_that_ignores_range_is_not_sent_the_whole_planet(web, tmp_path):
    web.protomaps_honours_range = False

    with pytest.raises(FetchError, match="ignored the Range header"):
        _run(web, tmp_path)


@pytest.mark.parametrize(
    ("build", "why"),
    [
        ("20260810", "not the last build of basemap version 4.15.1"),
        ("20261111", "4.15.2, which is still being built daily"),
        ("20200101", "no build dated 20200101"),
    ],
)
def test_a_build_protomaps_will_not_keep_is_refused_and_the_one_to_pin_is_named(
    web, tmp_path, build, why
):
    web.bodies[f"https://build.protomaps.com/{build}.pmtiles"] = PROTOMAPS_BUILD

    with pytest.raises(FetchError) as excinfo:
        _run(web, tmp_path, protomaps_build=build)

    assert why in str(excinfo.value)
    assert "the newest is 20260811" in str(excinfo.value)
    assert not any("build.protomaps.com" in url for url in web.urls())


def test_a_protomaps_build_that_is_not_a_date_is_refused_before_any_request(web, tmp_path):
    with pytest.raises(FetchError, match="YYYYMMDD"):
        _run(web, tmp_path, protomaps_build="latest")

    assert web.requests == []


def test_a_build_lacking_one_of_the_coverages_tiles_is_an_error(web, tmp_path):
    z, x, y = tiles_covering(_coverage_in_st5570())[-1]
    web.bodies[protomaps.ARCHIVE_URL] = protomaps.archive_bytes(
        _coverage_in_st5570().bounds_wgs84(), without=(z, x, y)
    )

    with pytest.raises(FetchError, match=f"no tile {z}/{x}/{y}"):
        _run(web, tmp_path)


def test_a_wider_coverage_gets_its_own_basemap_cut(web, tmp_path):
    _run(web, tmp_path)
    first = _basemap_entry(tmp_path).path
    wide = Coverage.from_geojson({
        "type": "Polygon",
        "coordinates": [[[-2.65, 51.43], [-2.55, 51.43], [-2.55, 51.47], [-2.65, 51.47],
                         [-2.65, 51.43]]],
    })  # fmt: skip
    web.bodies[protomaps.ARCHIVE_URL] = protomaps.archive_bytes(wide.bounds_wgs84())

    fetch(wide, tmp_path, osm_date="261110", margin_m=0.0, client=web, clock=web.clock,
          sleep=web.sleep, now=lambda: datetime(2026, 11, 12, tzinfo=UTC))  # fmt: skip

    assert _basemap_entry(tmp_path).path != first
