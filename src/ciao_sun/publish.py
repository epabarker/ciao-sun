"""`ciao-sun publish`: one build directory -> the data bucket, its inputs -> the inputs archive.

    data bucket     f<format>/<build>/<every file of the build directory>
    inputs bucket   f<format>/<build>/<the OSM .pbf and Terrain 50 zip, at their lockfile paths>

The data bucket is served at the data base URL, so an object's key is its path
under `<dataBase>/` (ADR 0002). `publish` uploads whatever the build directory
holds (`manifest.json`, `tiles/`, `basemap/`, and anything a later build adds),
except hidden files such as `.DS_Store`.

Every data object carries `Cache-Control: public, max-age=31536000, immutable`.
What is stored, by file name:

    *.bin    the gzip file on disk, byte for byte, as application/octet-stream
             with no Content-Encoding: the client gunzips tiles itself
    *.mvt    gzipped here (level 9, no timestamp, so the same bytes every time),
             as application/vnd.mapbox-vector-tile with Content-Encoding: gzip,
             so a browser receives the plain vector tile that is on disk
    *.json   as on disk, application/json
    others   as on disk, application/octet-stream

A published build is never rewritten and nothing is ever deleted (ADR 0002):

- `ObjectStore` can list keys and put objects, and has no delete.
- If any object exists under the build's prefix in either bucket, `publish`
  refuses before uploading anything.
- `manifest.json` is uploaded last, after the inputs archive and every other
  file, so a prefix that holds a manifest is a whole published build.
- `resume=True` finishes an interrupted publish: it is allowed only while the
  prefix has no manifest and holds nothing but this build's keys, and it uploads
  only the keys that are missing. It never replaces an object.

Before anything is uploaded the build is checked against its own manifest (the
build id is the directory name, the tiles are exactly the tile index and match
its SHA-256s, the basemap tile count) and the two archived inputs are checked
against the SHA-256s the manifest recorded, so the archive holds the files the
build was made from even if `fetch` has run again since.

`S3ObjectStore` is the real client, for R2's S3 API. `docs/publishing.md` is the
one-time bucket and CORS setup.
"""

from __future__ import annotations

import gzip
import hashlib
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ciao_sun import basemap
from ciao_sun.fetch import FetchError, read_lockfile
from ciao_sun.manifest import MANIFEST_NAME, read_manifest

CACHE_CONTROL = "public, max-age=31536000, immutable"
ARCHIVED_INPUT_KINDS = ("osm", "terrain50")
DEFAULT_WORKERS = 8

_CONTENT_TYPES = {
    ".json": "application/json",
    ".mvt": "application/vnd.mapbox-vector-tile",
}
_BINARY = "application/octet-stream"


class PublishError(Exception):
    """The build cannot be published as it stands; the message says why."""


class ObjectStoreError(Exception):
    """The object store failed or refused a request; an ObjectStore raises this."""


class ObjectStore(Protocol):
    """The two operations publish needs. There is deliberately no delete."""

    def keys(self, bucket: str, prefix: str) -> Iterator[str]:
        """Every key in `bucket` that starts with `prefix`."""
        ...

    def put(
        self,
        bucket: str,
        key: str,
        body: bytes | Path,
        *,
        content_type: str,
        cache_control: str | None = None,
        content_encoding: str | None = None,
    ) -> None:
        """Store `body` (bytes, or the contents of a file) at `key`."""
        ...


@dataclass(frozen=True)
class Published:
    format: int
    build: str
    prefix: str  # "f<format>/<build>/", in both buckets
    data_objects: int  # in the build, whether uploaded now or already there on a resume
    input_objects: int
    uploaded: int  # objects this run put, across both buckets


@dataclass(frozen=True)
class _Upload:
    bucket: str
    key: str
    path: Path
    cache_control: str | None

    def send(self, store: ObjectStore) -> None:
        content_type = _CONTENT_TYPES.get(self.path.suffix, _BINARY)
        if self.cache_control is not None and self.path.suffix == ".mvt":
            body = gzip.compress(self.path.read_bytes(), compresslevel=9, mtime=0)
            store.put(
                self.bucket, self.key, body, content_type=content_type,
                cache_control=self.cache_control, content_encoding="gzip",
            )  # fmt: skip
        else:
            store.put(
                self.bucket, self.key, self.path, content_type=content_type,
                cache_control=self.cache_control,
            )  # fmt: skip


def _silent(message: str) -> None:
    return None


def publish(
    build_dir: Path,
    inputs_root: Path,
    store: ObjectStore,
    *,
    data_bucket: str,
    inputs_bucket: str,
    resume: bool = False,
    workers: int = DEFAULT_WORKERS,
    report: Callable[[str], None] = _silent,
) -> Published:
    """Upload the build at `build_dir` and archive the inputs it was made from.

    `inputs_root` is the directory `ciao-sun fetch` wrote. Raises PublishError,
    before anything is uploaded, if the build is not whole, the inputs are not
    the build's, or the build's prefix already holds objects (see the module
    docstring for `resume`). An ObjectStoreError from `store` passes through.
    """
    if data_bucket == inputs_bucket:
        raise PublishError(
            f"The data bucket and the inputs bucket are both {data_bucket!r}. The inputs "
            "archive is private and must be a different bucket from the public data."
        )
    manifest = _manifest(build_dir)
    build_id, format_ = str(manifest["build"]), int(manifest["format"])
    prefix = f"f{format_}/{build_id}/"

    files = _build_files(build_dir)
    _check_against_manifest(build_dir, files, manifest)
    data = [
        _Upload(data_bucket, prefix + name, path, CACHE_CONTROL) for name, path in files.items()
    ]
    inputs = [
        _Upload(inputs_bucket, prefix + name, path, None)
        for name, path in _archived_inputs(inputs_root, manifest).items()
    ]

    pending: list[_Upload] = []
    for bucket, uploads in ((inputs_bucket, inputs), (data_bucket, data)):
        existing = set(store.keys(bucket, prefix))
        _check_prefix(bucket, prefix, existing, {u.key for u in uploads}, resume=resume)
        pending += [u for u in uploads if u.key not in existing]

    manifest_key = prefix + MANIFEST_NAME
    last = [u for u in pending if u.bucket == data_bucket and u.key == manifest_key]
    archive = [u for u in pending if u.bucket == inputs_bucket]
    rest = [u for u in pending if u.bucket == data_bucket and u.key != manifest_key]

    for upload in archive:
        report(f"Archiving {upload.path.name} to {upload.bucket}/{upload.key}")
        upload.send(store)
    report(f"Uploading {len(rest) + len(last)} objects to {data_bucket}/{prefix}")
    _send_all(rest, store, workers)
    for upload in last:
        upload.send(store)
    return Published(
        format=format_,
        build=build_id,
        prefix=prefix,
        data_objects=len(data),
        input_objects=len(inputs),
        uploaded=len(pending),
    )


def _manifest(build_dir: Path) -> dict[str, Any]:
    try:
        manifest = read_manifest(build_dir)
    except (OSError, ValueError) as exc:
        raise PublishError(f"{build_dir} is not a build directory: {exc}") from exc
    if manifest.get("build") != build_dir.name:
        raise PublishError(
            f"{build_dir} is not a finished build: its manifest names build "
            f"{manifest.get('build')!r} but the directory is {build_dir.name!r}."
        )
    return manifest


def _build_files(build_dir: Path) -> dict[str, Path]:
    """Every file of the build by its path under the build directory, hidden files left out."""
    files = {}
    for path in sorted(build_dir.rglob("*")):
        relative = path.relative_to(build_dir)
        if path.is_file() and not any(part.startswith(".") for part in relative.parts):
            files[relative.as_posix()] = path
    return files


def _check_against_manifest(
    build_dir: Path, files: dict[str, Path], manifest: dict[str, Any]
) -> None:
    index = manifest.get("tiles", {})
    on_disk = {Path(name).stem for name in files if name.startswith("tiles/")}
    if on_disk != set(index):
        odd = sorted(on_disk ^ set(index))
        raise PublishError(
            f"{build_dir}: the tiles on disk are not the manifest's tile index "
            f"(differing: {', '.join(odd[:5])}{'…' if len(odd) > 5 else ''})."
        )
    for grid_ref, entry in index.items():
        if _sha256(files[f"tiles/{grid_ref}.bin"]) != entry["sha256"]:
            raise PublishError(
                f"{build_dir}: tile {grid_ref} does not match the SHA-256 in the manifest. "
                "The build directory has been changed since it was built."
            )
    described = manifest.get("basemap")
    if described is not None:
        count = sum(1 for name in files if name.startswith(f"{basemap.DIRECTORY}/"))
        if count != described["tileCount"]:
            raise PublishError(
                f"{build_dir}: {count} basemap tiles on disk, but the manifest "
                f"counts {described['tileCount']}."
            )


def _archived_inputs(inputs_root: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    """The OSM extract and Terrain 50 zip this build was made from, by lockfile path."""
    try:
        lock = read_lockfile(inputs_root)
    except FetchError as exc:
        raise PublishError(str(exc)) from exc
    found = {}
    for kind in ARCHIVED_INPUT_KINDS:
        wanted = {
            line["sha256"]
            for line in manifest.get("inputs", [])
            if line["kind"] == kind and not line["absent"]
        }
        if not wanted:
            raise PublishError(f"The manifest records no {kind} input, so none can be archived.")
        matching = [e for e in lock.inputs if e.kind == kind and e.sha256 in wanted]
        if len(matching) != len(wanted):
            raise PublishError(
                f"The {kind} input in {inputs_root} is not the one this build was made from "
                "(its SHA-256 is not in the manifest). Publish with the inputs directory "
                "the build read."
            )
        for entry in matching:
            path = lock.path_of(entry)
            if not path.is_file() or _sha256(path) != entry.sha256:
                raise PublishError(
                    f"{path} is missing or does not match its lockfile SHA-256; "
                    "it cannot be archived as this build's input."
                )
            found[entry.path] = path
    return found


def _check_prefix(
    bucket: str, prefix: str, existing: set[str], expected: set[str], *, resume: bool
) -> None:
    if not existing:
        return
    if not resume:
        raise PublishError(
            f"{bucket}/{prefix} already holds {len(existing)} objects. A published build is "
            "never rewritten: build again for a new build id. If an earlier publish of this "
            "same build was interrupted, finish it with --resume."
        )
    if prefix + MANIFEST_NAME in existing and prefix + MANIFEST_NAME in expected:
        raise PublishError(
            f"{bucket}/{prefix} already holds a manifest: this build is published, "
            "and a published build is never rewritten."
        )
    foreign = sorted(existing - expected)
    if foreign:
        raise PublishError(
            f"{bucket}/{prefix} holds objects that are not part of this build "
            f"(e.g. {foreign[0]}); refusing to resume into it."
        )


def _send_all(uploads: list[_Upload], store: ObjectStore, workers: int) -> None:
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(upload.send, store) for upload in uploads]
        try:
            for future in as_completed(futures):
                future.result()
        except BaseException:
            for future in futures:
                future.cancel()
            raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class S3ObjectStore:
    """ObjectStore over an S3-compatible API (Cloudflare R2), through a boto3 S3 client.

    Each object is one PutObject, so a file must be under the 5 GB single-request limit.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def for_r2(cls, endpoint_url: str) -> S3ObjectStore:
        """A store on the R2 account at `endpoint_url`
        (`https://<account id>.r2.cloudflarestorage.com`).

        The credentials are an R2 API token's S3 key pair, found by boto3 in the
        usual places: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, or a profile.
        """
        import boto3
        from botocore.config import Config

        config = Config(
            # R2 does not take the checksum trailers boto3 sends by default since 1.36.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            retries={"max_attempts": 5, "mode": "standard"},
            max_pool_connections=2 * DEFAULT_WORKERS,
        )
        return cls(boto3.client("s3", endpoint_url=endpoint_url, region_name="auto", config=config))

    def keys(self, bucket: str, prefix: str) -> Iterator[str]:
        from botocore.exceptions import BotoCoreError, ClientError

        request: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        while True:
            try:
                page = self._client.list_objects_v2(**request)
            except (BotoCoreError, ClientError) as exc:
                raise ObjectStoreError(f"Cannot list {bucket}/{prefix}: {exc}") from exc
            for item in page.get("Contents", []):
                yield item["Key"]
            if not page.get("IsTruncated"):
                return
            request["ContinuationToken"] = page["NextContinuationToken"]

    def put(
        self,
        bucket: str,
        key: str,
        body: bytes | Path,
        *,
        content_type: str,
        cache_control: str | None = None,
        content_encoding: str | None = None,
    ) -> None:
        from botocore.exceptions import BotoCoreError, ClientError

        request: dict[str, Any] = {"Bucket": bucket, "Key": key, "ContentType": content_type}
        if cache_control is not None:
            request["CacheControl"] = cache_control
        if content_encoding is not None:
            request["ContentEncoding"] = content_encoding
        try:
            if isinstance(body, Path):
                with open(body, "rb") as f:
                    self._client.put_object(Body=f, **request)
            else:
                self._client.put_object(Body=body, **request)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ObjectStoreError(f"Cannot put {bucket}/{key}: {exc}") from exc
