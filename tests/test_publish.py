"""`ciao-sun publish`: build directory -> object store (#53).

A real build of the synthetic world of `tests/build_world.py` is published to a
fake object store. Nothing here reaches a real bucket.
"""

from __future__ import annotations

import gzip
import json
import re
import shutil
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import boto3
import pytest
from botocore.stub import ANY, Stubber
from typer.testing import CliRunner

from ciao_sun import publish as publisher
from ciao_sun.build import build
from ciao_sun.cli import app
from ciao_sun.fetch import read_lockfile
from ciao_sun.publish import ObjectStoreError, PublishError, S3ObjectStore, publish
from tests import build_world as world

IMMUTABLE = "public, max-age=31536000, immutable"
DATA, INPUTS = "data-bucket", "inputs-bucket"


@dataclass(frozen=True)
class Stored:
    body: bytes
    content_type: str
    cache_control: str | None
    content_encoding: str | None


class FakeStore:
    """An object store in memory. It can list and put, and nothing else: there is
    no way to delete through it, and it fails a put over an existing object."""

    def __init__(self, fail_after: int | None = None) -> None:
        self.objects: dict[tuple[str, str], Stored] = {}
        self.order: list[tuple[str, str]] = []
        self.fail_after = fail_after
        self._lock = threading.Lock()

    def keys(self, bucket: str, prefix: str) -> Iterator[str]:
        with self._lock:
            found = sorted(k for b, k in self.objects if b == bucket and k.startswith(prefix))
        return iter(found)

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
        data = body.read_bytes() if isinstance(body, Path) else body
        with self._lock:
            assert (bucket, key) not in self.objects, f"{bucket}/{key} was overwritten"
            if self.fail_after is not None and len(self.order) >= self.fail_after:
                raise ObjectStoreError("the connection dropped")
            self.objects[bucket, key] = Stored(data, content_type, cache_control, content_encoding)
            self.order.append((bucket, key))

    def bucket(self, name: str) -> dict[str, Stored]:
        return {key: stored for (bucket, key), stored in self.objects.items() if bucket == name}


@dataclass(frozen=True)
class Built:
    directory: Path
    inputs: Path

    @property
    def prefix(self) -> str:
        return f"f1/{self.directory.name}/"

    def files(self) -> dict[str, Path]:
        return {
            path.relative_to(self.directory).as_posix(): path
            for path in sorted(self.directory.rglob("*"))
            if path.is_file()
        }


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Built:
    root = tmp_path_factory.mktemp("publish")
    lock = world.fetch_inputs(root)
    directory = build(world.coverage(), lock.root, root / "builds", today=date(2026, 11, 11))
    return Built(directory, lock.root)


def _publish(built: Built, store: FakeStore, *, resume: bool = False, workers: int = 4) -> None:
    publish(
        built.directory, built.inputs, store, data_bucket=DATA, inputs_bucket=INPUTS,
        resume=resume, workers=workers,
    )  # fmt: skip


def test_every_file_of_the_build_is_published_under_its_format_and_build_id(built: Built):
    store = FakeStore()

    _publish(built, store)

    published = store.bucket(DATA)
    assert set(published) == {built.prefix + name for name in built.files()}
    assert built.prefix + "manifest.json" in published
    assert any(key.startswith(built.prefix + "tiles/") for key in published)
    assert any(key.startswith(built.prefix + "basemap/") for key in published)


def test_every_published_object_is_cached_for_a_year_and_immutable(built: Built):
    store = FakeStore()

    _publish(built, store)

    assert {stored.cache_control for stored in store.bucket(DATA).values()} == {IMMUTABLE}


def test_tiles_are_stored_as_the_gzip_files_on_disk_with_no_content_encoding(built: Built):
    store = FakeStore()

    _publish(built, store)

    tiles = {name: path for name, path in built.files().items() if name.startswith("tiles/")}
    assert tiles
    for name, path in tiles.items():
        stored = store.bucket(DATA)[built.prefix + name]
        assert stored.body == path.read_bytes()
        assert stored.body[:2] == b"\x1f\x8b"
        assert stored.content_encoding is None
        assert stored.content_type == "application/octet-stream"


def test_basemap_tiles_are_served_gzipped_and_decode_to_the_vector_tile_on_disk(built: Built):
    store, again = FakeStore(), FakeStore()

    _publish(built, store)
    _publish(built, again)

    tiles = {name: path for name, path in built.files().items() if name.endswith(".mvt")}
    assert tiles
    for name, path in tiles.items():
        stored = store.bucket(DATA)[built.prefix + name]
        assert stored.content_type == "application/vnd.mapbox-vector-tile"
        assert stored.content_encoding == "gzip"
        assert gzip.decompress(stored.body) == path.read_bytes()
        assert stored.body == again.bucket(DATA)[built.prefix + name].body


def test_the_manifest_is_json_and_is_the_last_object_uploaded(built: Built):
    store = FakeStore()

    _publish(built, store)

    assert store.order[-1] == (DATA, built.prefix + "manifest.json")
    stored = store.bucket(DATA)[built.prefix + "manifest.json"]
    assert stored.content_type == "application/json"
    assert stored.content_encoding is None
    assert json.loads(stored.body)["build"] == built.directory.name


def test_the_osm_extract_and_terrain_50_zip_are_archived_in_the_private_bucket(built: Built):
    store = FakeStore()

    _publish(built, store)

    lock = read_lockfile(built.inputs)
    wanted = {e.path: lock.path_of(e) for e in lock.inputs if e.kind in ("osm", "terrain50")}
    assert len(wanted) == 2
    archived = store.bucket(INPUTS)
    assert set(archived) == {built.prefix + path for path in wanted}
    for path, file in wanted.items():
        stored = archived[built.prefix + path]
        assert stored.body == file.read_bytes()
        assert stored.cache_control is None and stored.content_encoding is None
    assert not any(key.endswith((".pbf", ".zip")) for key in store.bucket(DATA))


def _copy(built: Built, root: Path, build_id: str | None = None) -> Built:
    """A copy of the build, renamed to `build_id` in its directory and manifest."""
    build_id = build_id or built.directory.name
    directory = root / "f1" / build_id
    shutil.copytree(built.directory, directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["build"] = build_id
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return Built(directory, built.inputs)


def test_whatever_else_the_build_directory_holds_is_published_too(built: Built, tmp_path: Path):
    copy = _copy(built, tmp_path)
    (copy.directory / "fixtures").mkdir()
    (copy.directory / "fixtures" / "morning.json").write_text('{"queries": []}')
    (copy.directory / ".DS_Store").write_bytes(b"finder")
    store = FakeStore()

    _publish(copy, store)

    stored = store.bucket(DATA)[copy.prefix + "fixtures/morning.json"]
    assert stored.body == b'{"queries": []}'
    assert (stored.content_type, stored.cache_control) == ("application/json", IMMUTABLE)
    assert not any(".DS_Store" in key for key in store.bucket(DATA))


@pytest.mark.parametrize("bucket", [DATA, INPUTS])
def test_a_build_prefix_that_already_exists_refuses_before_any_upload(built: Built, bucket: str):
    store = FakeStore()
    store.put(bucket, built.prefix + "tiles/ST0000.bin", b"old", content_type="x")
    before = dict(store.objects)

    with pytest.raises(PublishError, match="never rewritten"):
        _publish(built, store)

    assert store.objects == before


def test_publishing_the_same_build_twice_is_refused(built: Built):
    store = FakeStore()
    _publish(built, store)
    before = dict(store.objects)

    for resume in (False, True):
        with pytest.raises(PublishError, match="never rewritten"):
            _publish(built, store, resume=resume)

    assert store.objects == before


def test_a_later_build_leaves_every_object_of_an_earlier_one_in_place(built: Built, tmp_path: Path):
    store = FakeStore()
    _publish(built, store)
    before = dict(store.objects)

    later = _copy(built, tmp_path, "20261112a")
    _publish(later, store)

    assert before.items() <= store.objects.items()
    assert later.prefix + "manifest.json" in store.bucket(DATA)


def test_an_interrupted_publish_has_no_manifest_and_resume_uploads_only_what_is_missing(
    built: Built,
):
    store = FakeStore(fail_after=4)
    with pytest.raises(ObjectStoreError):
        _publish(built, store, workers=1)
    interrupted = dict(store.objects)
    assert len(interrupted) == 4
    assert (DATA, built.prefix + "manifest.json") not in interrupted

    store.fail_after = None
    with pytest.raises(PublishError, match="--resume"):
        _publish(built, store)
    _publish(built, store, resume=True)  # the fake fails any put over an existing object

    complete = FakeStore()
    _publish(built, complete)
    assert store.objects == complete.objects
    assert store.order[-1] == (DATA, built.prefix + "manifest.json")


def test_resume_refuses_a_prefix_that_holds_another_builds_objects(built: Built):
    store = FakeStore()
    store.put(DATA, built.prefix + "tiles/ZZ9999.bin", b"other", content_type="x")

    with pytest.raises(PublishError, match="not part of this build"):
        _publish(built, store, resume=True)

    assert len(store.objects) == 1


def test_a_tile_changed_since_the_build_is_refused(built: Built, tmp_path: Path):
    copy = _copy(built, tmp_path)
    tile = next((copy.directory / "tiles" / "evening").glob("*.bin"))
    tile.write_bytes(tile.read_bytes() + b"\x00")
    store = FakeStore()

    with pytest.raises(PublishError, match=tile.stem):
        _publish(copy, store)

    assert not store.objects


def test_a_tile_missing_from_the_build_directory_is_refused(built: Built, tmp_path: Path):
    copy = _copy(built, tmp_path)
    next((copy.directory / "tiles" / "morning").glob("*.bin")).unlink()
    store = FakeStore()

    with pytest.raises(PublishError, match="tile index"):
        _publish(copy, store)

    assert not store.objects


def test_an_unfinished_build_directory_is_refused(built: Built, tmp_path: Path):
    partial = tmp_path / "f1" / f"{built.directory.name}.partial"
    shutil.copytree(built.directory, partial)
    store = FakeStore()

    with pytest.raises(PublishError, match="not a finished build"):
        _publish(Built(partial, built.inputs), store)
    with pytest.raises(PublishError, match="not a build directory"):
        _publish(Built(tmp_path / "f1", built.inputs), store)

    assert not store.objects


def test_inputs_that_are_not_the_ones_the_build_was_made_from_are_refused(
    built: Built, tmp_path: Path
):
    inputs = tmp_path / "inputs"
    shutil.copytree(built.inputs, inputs)
    lock_path = inputs / "fetch.lock.json"
    document = json.loads(lock_path.read_text())
    (osm,) = [item for item in document["inputs"] if item["kind"] == "osm"]
    (inputs / osm["path"]).write_bytes(b"a newer extract")
    osm["sha256"] = "0" * 64
    lock_path.write_text(json.dumps(document))
    store = FakeStore()

    with pytest.raises(PublishError, match="osm"):
        _publish(Built(built.directory, inputs), store)

    assert not store.objects


def test_an_input_file_changed_on_disk_is_refused(built: Built, tmp_path: Path):
    inputs = tmp_path / "inputs"
    shutil.copytree(built.inputs, inputs)
    lock = read_lockfile(inputs)
    (terrain,) = [entry for entry in lock.inputs if entry.kind == "terrain50"]
    lock.path_of(terrain).write_bytes(b"truncated")
    store = FakeStore()

    with pytest.raises(PublishError, match="terr50_gagg_gb.zip"):
        _publish(Built(built.directory, inputs), store)

    assert not store.objects


def test_one_bucket_for_both_the_data_and_the_private_inputs_is_refused(built: Built):
    store = FakeStore()

    with pytest.raises(PublishError, match="private"):
        publish(built.directory, built.inputs, store, data_bucket=DATA, inputs_bucket=DATA)

    assert not store.objects


# --- the command ---------------------------------------------------------------------------

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(output: str) -> str:
    return " ".join(_ANSI.sub("", output).split())


def _command(built: Built, *extra: str) -> list[str]:
    return [
        "publish", str(built.directory), "--inputs", str(built.inputs),
        "--data-bucket", DATA, "--inputs-bucket", INPUTS,
        "--endpoint-url", "https://account.r2.example", *extra,
    ]  # fmt: skip


@pytest.fixture
def cli_store(monkeypatch: pytest.MonkeyPatch) -> FakeStore:
    """The store the command gets in place of the real R2 client."""
    store = FakeStore()

    def for_r2(endpoint_url: str) -> FakeStore:
        assert endpoint_url == "https://account.r2.example"
        return store

    monkeypatch.setattr(publisher.S3ObjectStore, "for_r2", staticmethod(for_r2))
    for name in ("CIAO_SUN_DATA_BUCKET", "CIAO_SUN_INPUTS_BUCKET", "CIAO_SUN_R2_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    return store


def test_the_publish_command_uploads_the_build_and_says_where(built: Built, cli_store: FakeStore):
    result = CliRunner().invoke(app, _command(built))

    assert result.exit_code == 0, result.output
    assert set(cli_store.bucket(DATA)) == {built.prefix + name for name in built.files()}
    assert len(cli_store.bucket(INPUTS)) == 2
    assert f"{DATA}/{built.prefix}" in _plain(result.output)


def test_the_publish_command_reports_a_refusal_without_a_traceback(
    built: Built, cli_store: FakeStore
):
    assert CliRunner().invoke(app, _command(built)).exit_code == 0
    before = dict(cli_store.objects)

    result = CliRunner().invoke(app, _command(built))

    assert result.exit_code == 1
    assert "never rewritten" in _plain(result.output) and "Traceback" not in result.output
    assert cli_store.objects == before


def test_the_publish_command_reports_a_failed_upload_and_resumes(
    built: Built, cli_store: FakeStore
):
    cli_store.fail_after = 3

    failed = CliRunner().invoke(app, _command(built))

    assert failed.exit_code == 1
    assert "--resume" in _plain(failed.output) and "Traceback" not in failed.output

    cli_store.fail_after = None
    resumed = CliRunner().invoke(app, _command(built, "--resume"))

    assert resumed.exit_code == 0, resumed.output
    assert built.prefix + "manifest.json" in cli_store.bucket(DATA)


def test_the_publish_command_takes_its_buckets_and_endpoint_from_the_environment(
    built: Built, cli_store: FakeStore, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("CIAO_SUN_DATA_BUCKET", DATA)
    monkeypatch.setenv("CIAO_SUN_INPUTS_BUCKET", INPUTS)
    monkeypatch.setenv("CIAO_SUN_R2_ENDPOINT", "https://account.r2.example")

    result = CliRunner().invoke(
        app, ["publish", str(built.directory), "--inputs", str(built.inputs)]
    )

    assert result.exit_code == 0, result.output
    assert built.prefix + "manifest.json" in cli_store.bucket(DATA)


def test_publish_help_says_what_is_uploaded_and_that_nothing_is_rewritten():
    result = CliRunner().invoke(app, ["publish", "--help"], terminal_width=200)
    assert result.exit_code == 0, result.output
    text = _plain(result.output)
    for phrase in [
        "f<format>/<build id>/", "immutable", "never rewritten", "--resume", "--data-bucket",
        "--inputs-bucket", "--endpoint-url", "CIAO_SUN_R2_ENDPOINT", "AWS_ACCESS_KEY_ID",
        "Terrain 50", "docs/publishing.md",
    ]:  # fmt: skip
        assert phrase in text, f"`publish --help` does not mention {phrase!r}"


# --- the S3 client, against botocore's stubber: requests are validated, never sent ---------


@pytest.fixture
def s3() -> Iterator[tuple[S3ObjectStore, Stubber]]:
    client = boto3.client(
        "s3", endpoint_url="https://account.r2.invalid", region_name="auto",
        aws_access_key_id="not-a-key", aws_secret_access_key="not-a-secret",
    )  # fmt: skip
    with Stubber(client) as stubber:
        yield S3ObjectStore(client), stubber
        stubber.assert_no_pending_responses()


def test_the_s3_store_puts_an_object_with_its_headers(
    s3: tuple[S3ObjectStore, Stubber], tmp_path: Path
):
    store, stubber = s3
    stubber.add_response(
        "put_object", {},
        {"Bucket": DATA, "Key": "f1/b/basemap/10/1/2.mvt", "Body": b"gz",
         "ContentType": "application/vnd.mapbox-vector-tile", "CacheControl": IMMUTABLE,
         "ContentEncoding": "gzip"},
    )  # fmt: skip
    stubber.add_response(
        "put_object", {},
        {"Bucket": INPUTS, "Key": "f1/b/osm/x.osm.pbf", "Body": ANY,
         "ContentType": "application/octet-stream"},
    )  # fmt: skip
    file = tmp_path / "x.osm.pbf"
    file.write_bytes(b"pbf")

    store.put(
        DATA, "f1/b/basemap/10/1/2.mvt", b"gz", content_type="application/vnd.mapbox-vector-tile",
        cache_control=IMMUTABLE, content_encoding="gzip",
    )  # fmt: skip
    store.put(INPUTS, "f1/b/osm/x.osm.pbf", file, content_type="application/octet-stream")


def test_the_s3_store_lists_every_page_of_keys_under_a_prefix(s3: tuple[S3ObjectStore, Stubber]):
    store, stubber = s3
    stubber.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": "f1/b/a"}], "IsTruncated": True, "NextContinuationToken": "t"},
        {"Bucket": DATA, "Prefix": "f1/b/"},
    )
    stubber.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": "f1/b/c"}], "IsTruncated": False},
        {"Bucket": DATA, "Prefix": "f1/b/", "ContinuationToken": "t"},
    )
    stubber.add_response("list_objects_v2", {"IsTruncated": False}, {"Bucket": DATA, "Prefix": "x"})

    assert list(store.keys(DATA, "f1/b/")) == ["f1/b/a", "f1/b/c"]
    assert list(store.keys(DATA, "x")) == []


def test_the_s3_store_reports_a_refused_request_as_an_object_store_error(
    s3: tuple[S3ObjectStore, Stubber],
):
    store, stubber = s3
    stubber.add_client_error("put_object", "AccessDenied", "Access Denied", 403)
    stubber.add_client_error("list_objects_v2", "NoSuchBucket", "No such bucket", 404)

    with pytest.raises(ObjectStoreError, match="AccessDenied"):
        store.put(DATA, "k", b"x", content_type="application/json")
    with pytest.raises(ObjectStoreError, match="NoSuchBucket"):
        list(store.keys(DATA, "f1/"))
