"""`ciao-sun fetch`: pull every build input into a local, hash-locked cache.

Inputs, all anonymous downloads:

- Environment Agency LIDAR Composite, 1 m, as 5 km tile zips: last-return DSM,
  DTM and first-return DSM for every tile within the margin of the coverage.
- OS Terrain 50 for Great Britain, one zip.
- A dated Geofabrik `.osm.pbf` extract.
- The basemap: the coverage's tiles out of a pinned Protomaps daily build, read
  from the 140 GB planet archive by byte range (`basemap.extract`).

Layout under the fetch root (cached per source, tile and version):

    fetch.lock.json
    ea/<product>/<year>/<tile>.zip
    terrain50/<version>/terr50_gagg_gb.zip
    osm/<region-with-dashes>-<yymmdd>.osm.pbf
    basemap/<build date>/z<zooms>_x<columns>_y<rows>.pmtiles

`fetch.lock.json` lists every input with its source, version, URL, SHA-256,
size, retrieval time and path relative to the lockfile, so `read_lockfile` is
all the build needs to find its inputs.

No upstream publishes a SHA-256, so verification is trust-on-first-use: the
first fetch records each hash, and from then on any cached or re-downloaded
file that differs from its lockfile hash is refused.

The EA tile URLs are the portal's own undocumented backend (see the
`research/lidar-access` branch); they are built in `_ea_url` and nowhere else.

Protomaps keeps every daily build for a week and, after that, only the last
build of each patch version of its basemap
(https://docs.protomaps.com/basemaps/downloads). So the pinned build must be
the last of a patch version that a newer version has since replaced: any other
build is deleted within the week, or is not yet known to be the last.
`_PROTOMAPS_BUILDS_URL` is the list the builds page (maps.protomaps.com/builds)
reads; it is not documented.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path
from typing import Any, Protocol

from ciao_sun import __version__, basemap
from ciao_sun.coverage import Coverage
from ciao_sun.report import silent
from ciao_sun.tiles import tile_codes_near_polygon

LOCKFILE_NAME = "fetch.lock.json"
LOCKFILE_VERSION = 1

DEFAULT_MARGIN_M = 3000.0
DEFAULT_EA_YEAR = "2022"
DEFAULT_OSM_REGION = "europe/united-kingdom/england"
DEFAULT_PROTOMAPS_BUILD = "20260811"  # the last build of basemap version 4.15.1

MIN_REQUEST_INTERVAL_S = 1.0
BACKOFF_403_S = (30.0, 60.0, 120.0, 240.0, 480.0)
MAX_DROPS_WITHOUT_PROGRESS = 5

# kind -> (EA product slug, dataset name)
EA_PRODUCTS: dict[str, tuple[str, str]] = {
    "dsm": (
        "lidar_composite_last_return_dsm",
        "Environment Agency LIDAR Composite Last Return DSM 1m",
    ),
    "dtm": ("lidar_composite_dtm", "Environment Agency LIDAR Composite DTM 1m"),
    "first_return_dsm": (
        "lidar_composite_first_return_dsm",
        "Environment Agency LIDAR Composite First Return DSM 1m",
    ),
}

_EA_BASE = "https://environment.data.gov.uk/tiles/collections/survey"
_TERRAIN50_PRODUCT_URL = "https://api.os.uk/downloads/v1/products/Terrain50"
_TERRAIN50_URL = (
    _TERRAIN50_PRODUCT_URL + "/downloads?area=GB&format=ASCII+Grid+and+GML+%28Grid%29&redirect"
)
_TERRAIN50_FILE = "terr50_gagg_gb.zip"
_GEOFABRIK_BASE = "https://download.geofabrik.de"
_PROTOMAPS_BASE = "https://build.protomaps.com"
_PROTOMAPS_BUILDS_URL = "https://build-metadata.protomaps.dev/builds.json"


class FetchError(Exception):
    """A fetch could not be completed."""


class HashMismatchError(FetchError):
    """A file's SHA-256 is not the one the lockfile recorded for it."""


class TransportError(Exception):
    """The connection failed or dropped; an HttpClient raises this, never a status."""


def _no_op() -> None:
    return None


@dataclass(frozen=True)
class Response:
    """An HTTP response: the status and the body as an iterable of byte chunks.

    Iterating `chunks` raises TransportError if the connection drops mid-body.
    """

    status: int
    chunks: Iterable[bytes]
    close: Callable[[], None] = _no_op


class HttpClient(Protocol):
    """The one HTTP operation fetch needs: a GET that follows redirects."""

    def get(self, url: str, headers: Mapping[str, str]) -> Response: ...


@dataclass(frozen=True)
class LockedInput:
    """One line of the lockfile. `path` is relative to the lockfile's directory.

    An `absent` input is an EA tile the server does not publish (404), such as
    open sea; it has no file and no hash.
    """

    kind: str  # "dsm" | "dtm" | "first_return_dsm" | "terrain50" | "osm" | "basemap"
    source: str
    tile: str | None
    version: str
    url: str
    path: str
    sha256: str | None
    bytes: int | None
    fetched_at: str
    absent: bool = False


@dataclass(frozen=True)
class Lockfile:
    root: Path
    coverage: Coverage
    margin_m: float
    inputs: tuple[LockedInput, ...]

    def path_of(self, entry: LockedInput) -> Path:
        return self.root / entry.path


def read_lockfile(root: Path) -> Lockfile:
    """Read `<root>/fetch.lock.json`."""
    path = root / LOCKFILE_NAME
    try:
        document = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise FetchError(f"Cannot read lockfile {path}: {exc}") from exc
    if not isinstance(document, dict) or document.get("lockfile") != LOCKFILE_VERSION:
        raise FetchError(f"{path} is not a version {LOCKFILE_VERSION} fetch lockfile.")
    try:
        return Lockfile(
            root=root,
            coverage=Coverage.from_geojson(document["coverage"]),
            margin_m=float(document["margin_m"]),
            inputs=tuple(LockedInput(**item) for item in document["inputs"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FetchError(f"Malformed lockfile {path}: {exc}") from exc


def _utc_now() -> datetime:
    return datetime.now(UTC)


def fetch(
    coverage: Coverage,
    root: Path,
    *,
    osm_date: str,
    client: HttpClient,
    ea_year: str = DEFAULT_EA_YEAR,
    osm_region: str = DEFAULT_OSM_REGION,
    terrain50_version: str | None = None,
    protomaps_build: str = DEFAULT_PROTOMAPS_BUILD,
    margin_m: float = DEFAULT_MARGIN_M,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = _utc_now,
    report: Callable[[str], None] = silent,
) -> Lockfile:
    """Bring `root` up to date with every build input and rewrite its lockfile.

    Files already cached are not requested again. If a lockfile exists, every
    cached or downloaded file must match the hash it recorded, else
    HashMismatchError. On any failure the previous lockfile is left as it was
    and partial downloads are kept for the next run to resume.
    """
    if not re.fullmatch(r"\d{6}", osm_date):
        raise FetchError(f"OSM date must be YYMMDD as in Geofabrik's file names, not {osm_date!r}.")
    if not re.fullmatch(r"\d{4}", ea_year):
        raise FetchError(f"EA composite year must be YYYY, not {ea_year!r}.")
    osm_region = osm_region.strip("/")
    if not re.fullmatch(r"[a-z0-9-]+(/[a-z0-9-]+)*", osm_region):
        raise FetchError(f"Not a Geofabrik region path: {osm_region!r}.")
    if terrain50_version is not None and not re.fullmatch(r"[\w.-]+", terrain50_version):
        raise FetchError(f"Not a Terrain 50 version: {terrain50_version!r}.")
    if not re.fullmatch(r"\d{8}", protomaps_build):
        raise FetchError(f"Protomaps build must be its date as YYYYMMDD, not {protomaps_build!r}.")

    root.mkdir(parents=True, exist_ok=True)
    session = _Session(client, clock, sleep, report)
    previous = _previous_entries(root)
    stamp = now().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    wanted: list[_Wanted] = []
    for tile in tile_codes_near_polygon(coverage.rings_bng(), margin_m):
        for kind, (product, source) in EA_PRODUCTS.items():
            wanted.append(
                _Wanted(
                    kind=kind,
                    source=source,
                    tile=tile,
                    version=ea_year,
                    url=_ea_url(product, ea_year, tile),
                    path=f"ea/{product}/{ea_year}/{tile}.zip",
                    may_be_absent=True,
                )
            )
    t50_version = _terrain50_version(root, terrain50_version, session)
    wanted.append(
        _Wanted(
            kind="terrain50",
            source="Ordnance Survey OS Terrain 50, ASCII Grid, GB",
            tile=None,
            version=t50_version,
            url=_TERRAIN50_URL,
            path=f"terrain50/{t50_version}/{_TERRAIN50_FILE}",
        )
    )
    wanted.append(
        _Wanted(
            kind="osm",
            source=f"Geofabrik OpenStreetMap extract {osm_region}",
            tile=None,
            version=osm_date,
            url=f"{_GEOFABRIK_BASE}/{osm_region}-{osm_date}.osm.pbf",
            path=f"osm/{osm_region.replace('/', '-')}-{osm_date}.osm.pbf",
        )
    )
    x0, x1, y0, y1 = basemap.tile_range(coverage, basemap.MAX_ZOOM)
    wanted.append(
        _Wanted(
            kind="basemap",
            source="Protomaps basemap daily build",
            tile=None,
            version=protomaps_build,
            url=f"{_PROTOMAPS_BASE}/{protomaps_build}.pmtiles",
            path=f"basemap/{protomaps_build}/z{basemap.MIN_ZOOM}-{basemap.MAX_ZOOM}"
            f"_x{x0}-{x1}_y{y0}-{y1}.pmtiles",
            download=functools.partial(_extract_basemap, coverage),
        )
    )

    entries = [_obtain(item, root, previous.get(item.path), session, stamp) for item in wanted]

    lock = Lockfile(root=root, coverage=coverage, margin_m=margin_m, inputs=tuple(entries))
    _write_lockfile(lock)
    return lock


@dataclass(frozen=True)
class _Wanted:
    kind: str
    source: str
    tile: str | None
    version: str
    url: str
    path: str
    may_be_absent: bool = False
    # Writes the input to a `.part` file; False means the server does not publish it.
    download: Callable[[_Wanted, Path, _Session], bool] | None = None


def _ea_url(product: str, year: str, tile: str) -> str:
    return f"{_EA_BASE}/{product}/{year}/1/{tile}"


class _Session:
    """Throttled requests: spaced out, backing off on 403."""

    def __init__(
        self,
        client: HttpClient,
        clock: Callable[[], float],
        sleep: Callable[[float], None],
        report: Callable[[str], None],
    ) -> None:
        self._client = client
        self._clock = clock
        self._sleep = sleep
        self.report = report
        self._last_request: float | None = None

    def get(self, url: str, headers: Mapping[str, str]) -> Response:
        """GET with throttling. TransportError on connect is returned to the caller."""
        for backoff in (*BACKOFF_403_S, None):
            if self._last_request is not None:
                wait = self._last_request + MIN_REQUEST_INTERVAL_S - self._clock()
                if wait > 0:
                    self._sleep(wait)
            self._last_request = self._clock()
            response = self._client.get(url, headers)
            if response.status != 403:
                return response
            response.close()
            if backoff is not None:
                self.report(f"403 from {url}; backing off {backoff:.0f} s")
                self._sleep(backoff)
        raise FetchError(
            f"{url}: still HTTP 403 after {len(BACKOFF_403_S)} backoffs; "
            "the server is refusing us. Run fetch again later; it resumes where it stopped."
        )

    def get_bytes(self, url: str) -> bytes:
        """A small body, whole. Retries dropped connections."""
        for _ in range(MAX_DROPS_WITHOUT_PROGRESS):
            try:
                response = self.get(url, {})
                if response.status != 200:
                    response.close()
                    raise FetchError(f"{url}: HTTP {response.status}")
                return b"".join(response.chunks)
            except TransportError as exc:
                self.report(f"connection dropped for {url}: {exc}")
        raise FetchError(f"{url}: connection dropped {MAX_DROPS_WITHOUT_PROGRESS} times.")

    def get_range(self, url: str, offset: int, length: int) -> bytes:
        """`length` bytes of a large file from `offset`; fewer only at its end. Retries drops."""
        headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
        for _ in range(MAX_DROPS_WITHOUT_PROGRESS):
            try:
                response = self.get(url, headers)
                if response.status == 200:
                    response.close()
                    raise FetchError(
                        f"{url}: the server ignored the Range header and offered the whole file."
                    )
                if response.status != 206:
                    response.close()
                    raise FetchError(f"{url}: HTTP {response.status}")
                return b"".join(response.chunks)
            except TransportError as exc:
                self.report(f"connection dropped for {url}: {exc}")
        raise FetchError(f"{url}: connection dropped {MAX_DROPS_WITHOUT_PROGRESS} times.")


def _terrain50_version(root: Path, pinned: str | None, session: _Session) -> str:
    """The Terrain 50 version to use: cached if we have it, else what OS serves now.

    OS only ever serves its current release, so a version that is not cached
    is confirmed against the product metadata before it is downloaded.
    """
    cached = sorted(
        p.parent.name for p in (root / "terrain50").glob(f"*/{_TERRAIN50_FILE}") if p.is_file()
    )
    if pinned is not None and pinned in cached:
        return pinned
    if pinned is None and cached:
        return cached[-1]
    try:
        served = json.loads(session.get_bytes(_TERRAIN50_PRODUCT_URL))["version"]
    except (ValueError, KeyError, TypeError) as exc:
        raise FetchError(
            f"{_TERRAIN50_PRODUCT_URL}: could not read the Terrain 50 version: {exc!r}"
        ) from exc
    if not isinstance(served, str) or not re.fullmatch(r"[\w.-]+", served):
        raise FetchError(f"{_TERRAIN50_PRODUCT_URL}: unusable Terrain 50 version {served!r}")
    if pinned is not None and served != pinned:
        raise FetchError(
            f"OS now serves Terrain 50 version {served}, not the pinned {pinned}, "
            "and no copy of the pinned version is cached."
        )
    return served


def _extract_basemap(coverage: Coverage, item: _Wanted, part: Path, session: _Session) -> bool:
    """Cut the coverage's basemap tiles from the pinned Protomaps build into `part`."""
    _check_protomaps_build(item.version, session)
    try:
        basemap.extract(functools.partial(session.get_range, item.url), coverage, part)
    except basemap.BasemapError as exc:
        raise FetchError(f"{item.url}: {exc}") from exc
    return True


def _check_protomaps_build(build: str, session: _Session) -> None:
    """Refuse a build Protomaps does not keep: one that is not the last of a finished version."""
    try:
        listed = json.loads(session.get_bytes(_PROTOMAPS_BUILDS_URL))
        builds = sorted(
            (str(entry["key"]).removesuffix(".pmtiles"), str(entry["version"])) for entry in listed
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise FetchError(
            f"{_PROTOMAPS_BUILDS_URL}: could not read the list of Protomaps builds: {exc!r}"
        ) from exc
    if not builds:
        raise FetchError(f"{_PROTOMAPS_BUILDS_URL}: Protomaps lists no builds.")
    newest_version = builds[-1][1]
    last_of = {version: date for date, version in builds}  # sorted, so the last date wins
    kept = sorted(date for version, date in last_of.items() if version != newest_version)
    advice = (
        f"Pin the last build of a version Protomaps has finished with, which it keeps: "
        f"the newest is {kept[-1]}."
        if kept
        else "Protomaps lists no finished version yet."
    )
    versions = dict(builds)
    if build not in versions:
        raise FetchError(f"Protomaps has no build dated {build}. {advice}")
    version = versions[build]
    if version == newest_version:
        raise FetchError(
            f"Protomaps build {build} is of basemap version {version}, which is still being "
            f"built daily, so it will be deleted within a week. {advice}"
        )
    if last_of[version] != build:
        raise FetchError(
            f"Protomaps build {build} is not the last build of basemap version {version} "
            f"({last_of[version]} is), so it will be deleted within a week. {advice}"
        )


def _obtain(
    item: _Wanted,
    root: Path,
    previous: LockedInput | None,
    session: _Session,
    stamp: str,
) -> LockedInput:
    dest = root / item.path
    expected = previous.sha256 if previous is not None else None

    if not dest.exists():
        if previous is not None and previous.absent and previous.url == item.url:
            return previous
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        session.report(f"fetching {item.path}")
        if not (item.download or _download)(item, part, session):
            session.report(f"not published (404), recorded as absent: {item.path}")
            return _entry(item, None, None, stamp, absent=True)
        _check_hash(item, part, expected, "downloaded")
        part.replace(dest)
        downloaded = True
    else:
        _check_hash(item, dest, expected, "cached")
        downloaded = False

    digest = sha256_of(dest)
    if previous is not None and previous.sha256 == digest and not downloaded:
        fetched_at = previous.fetched_at
    else:
        fetched_at = stamp
    return _entry(item, digest, dest.stat().st_size, fetched_at)


def _entry(
    item: _Wanted, digest: str | None, size: int | None, fetched_at: str, absent: bool = False
) -> LockedInput:
    return LockedInput(
        kind=item.kind,
        source=item.source,
        tile=item.tile,
        version=item.version,
        url=item.url,
        path=item.path,
        sha256=digest,
        bytes=size,
        fetched_at=fetched_at,
        absent=absent,
    )


def _download(item: _Wanted, part: Path, session: _Session) -> bool:
    """Download to `part`, resuming whatever is already there. False means 404."""
    drops = 0
    while True:
        offset = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        try:
            response = session.get(item.url, headers)
            if response.status == 206 and offset:
                mode = "ab"
            elif response.status == 200:
                mode = "wb"  # no partial file, or the server ignored Range: start again
            elif response.status == 416:
                response.close()
                part.unlink(missing_ok=True)  # the partial file is not a prefix of the real one
                continue
            elif response.status == 404 and item.may_be_absent:
                response.close()
                part.unlink(missing_ok=True)
                return False
            else:
                response.close()
                raise FetchError(f"{item.url}: HTTP {response.status}")
            with open(part, mode) as out:
                for chunk in response.chunks:
                    out.write(chunk)
            return True
        except TransportError as exc:
            received = part.stat().st_size if part.exists() else 0
            drops = 1 if received > offset else drops + 1
            if drops >= MAX_DROPS_WITHOUT_PROGRESS:
                raise FetchError(
                    f"{item.url}: connection dropped {drops} times in a row without progress "
                    f"({exc}). Run fetch again; it resumes from {received} bytes."
                ) from exc
            session.report(f"connection dropped at {received} bytes, resuming {item.path}")


def _check_hash(item: _Wanted, file: Path, expected: str | None, what: str) -> None:
    if expected is None:
        return
    actual = sha256_of(file)
    if actual == expected:
        return
    if what == "downloaded":
        file.unlink()
    raise HashMismatchError(
        f"SHA-256 mismatch for {what} {item.path}\n"
        f"  lockfile: {expected}\n"
        f"  {what}: {actual}\n"
        f"  from {item.url}\n"
        "The upstream file changed or the copy is corrupt. If the change is expected, "
        f"delete {item.path} and its lockfile entry (or {LOCKFILE_NAME}) and fetch again."
    )


def sha256_of(path: Path) -> str:
    """The file's SHA-256 as lowercase hex: the checksum lockfiles and manifests record."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def _previous_entries(root: Path) -> dict[str, LockedInput]:
    if not (root / LOCKFILE_NAME).exists():
        return {}
    return {entry.path: entry for entry in read_lockfile(root).inputs}


def _write_lockfile(lock: Lockfile) -> None:
    document: dict[str, Any] = {
        "lockfile": LOCKFILE_VERSION,
        "coverage": lock.coverage.geometry,
        "margin_m": lock.margin_m,
        "inputs": [asdict(entry) for entry in lock.inputs],
    }
    text = json.dumps(document, indent=2) + "\n"
    path = lock.root / LOCKFILE_NAME
    if path.exists() and path.read_text() == text:
        return
    scratch = path.with_name(path.name + ".tmp")
    scratch.write_text(text)
    scratch.replace(path)


class UrllibClient:
    """The real HttpClient: stdlib urllib, following redirects."""

    def __init__(self, timeout_s: float = 60.0) -> None:
        self._timeout_s = timeout_s
        self._user_agent = f"ciao-sun/{__version__} (fetch; polite, serial, cached)"

    def get(self, url: str, headers: Mapping[str, str]) -> Response:
        request = urllib.request.Request(url, headers={"User-Agent": self._user_agent, **headers})
        try:
            raw = urllib.request.urlopen(request, timeout=self._timeout_s)
        except urllib.error.HTTPError as exc:
            exc.close()
            return Response(exc.code, iter(()))
        except (OSError, HTTPException) as exc:
            raise TransportError(str(exc)) from exc
        return Response(raw.status, _body_chunks(raw), raw.close)


def _body_chunks(raw: Any) -> Iterator[bytes]:
    declared = raw.headers.get("Content-Length")
    received = 0
    try:
        while True:
            try:
                chunk = raw.read(1 << 20)
            except (OSError, HTTPException) as exc:
                raise TransportError(str(exc)) from exc
            if not chunk:
                break
            received += len(chunk)
            yield chunk
    finally:
        raw.close()
    if declared is not None and declared.isdigit() and received < int(declared):
        raise TransportError(f"body ended at {received} of {declared} bytes")
