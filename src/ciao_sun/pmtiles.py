"""PMTiles v3: read a tile archive through byte ranges, and write a small one.

A PMTiles archive is one file holding a pyramid of map tiles. Protomaps
publishes its basemap as one (about 140 GB for the planet), meant to be read
with HTTP Range requests; `Archive` does that through any `read(offset, length)`
function, so the same code reads the remote build and a local extract.

Layout (https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md):

- a 127-byte header: where the sections are, how they are compressed, the zoom
  range and bounds;
- a root directory, inside the first 16 KiB;
- JSON metadata;
- optional leaf directories;
- the tile data.

A tile is addressed by its tile id: its place along a Hilbert curve through its
zoom level, after every tile of the lower zooms. A directory is a sorted list
of entries `(tile id, offset, length, run length)`. An entry with a run length
of n stands for n consecutive tile ids with the same content; a run length of
0 points at a leaf directory instead.

`write_archive` writes what `basemap.extract` cut from a build, and the tiny
archives the tests read.
"""

from __future__ import annotations

import gzip
import json
import struct
from bisect import bisect_right
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HEADER_BYTES = 127
ROOT_REACH_BYTES = 16384  # the header and root directory lie within this many bytes
_MAGIC = b"PMTiles"
_VERSION = 3
_HEADER = struct.Struct("<7sB11Q4B2B4iB2i")

COMPRESSION_NONE = 1
COMPRESSION_GZIP = 2
TILE_TYPE_MVT = 1

Zxy = tuple[int, int, int]
ReadRange = Callable[[int, int], bytes]
"""`read(offset, length)`: that many bytes from there, fewer only at the end of the file."""


class PMTilesError(Exception):
    """Not a PMTiles v3 archive this module can read."""


def tile_id(z: int, x: int, y: int) -> int:
    """The tile id of tile `z/x/y`."""
    if not (0 <= z <= 31 and 0 <= x < 1 << z and 0 <= y < 1 << z):
        raise PMTilesError(f"No such tile: {z}/{x}/{y}.")
    distance = 0
    s = (1 << z) >> 1
    while s > 0:
        rx, ry = int(x & s > 0), int(y & s > 0)
        distance += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        s >>= 1
    return ((1 << 2 * z) - 1) // 3 + distance


def zxy_of(tile: int) -> Zxy:
    """The `z/x/y` of a tile id."""
    z = 0
    while ((1 << 2 * (z + 1)) - 1) // 3 <= tile:
        z += 1
    distance = tile - ((1 << 2 * z) - 1) // 3
    x = y = 0
    s = 1
    while s < 1 << z:
        rx = 1 & (distance // 2)
        ry = 1 & (distance ^ rx)
        if ry == 0:
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        distance //= 4
        s <<= 1
    return z, x, y


@dataclass(frozen=True)
class Header:
    root_offset: int
    root_length: int
    metadata_offset: int
    metadata_length: int
    leaf_offset: int
    leaf_length: int
    tile_data_offset: int
    tile_data_length: int
    internal_compression: int
    tile_compression: int
    tile_type: int
    min_zoom: int
    max_zoom: int
    bounds: tuple[float, float, float, float]  # west, south, east, north, degrees


@dataclass(frozen=True)
class _Entry:
    tile_id: int
    offset: int
    length: int
    run_length: int


def _parse_header(data: bytes) -> Header:
    if len(data) < HEADER_BYTES or data[:7] != _MAGIC:
        raise PMTilesError("Not a PMTiles archive: it does not start with the PMTiles magic.")
    fields = _HEADER.unpack(data[:HEADER_BYTES])
    if fields[1] != _VERSION:
        raise PMTilesError(f"PMTiles version {fields[1]}, not {_VERSION}.")
    return Header(
        root_offset=fields[2], root_length=fields[3],
        metadata_offset=fields[4], metadata_length=fields[5],
        leaf_offset=fields[6], leaf_length=fields[7],
        tile_data_offset=fields[8], tile_data_length=fields[9],
        internal_compression=fields[14], tile_compression=fields[15], tile_type=fields[16],
        min_zoom=fields[17], max_zoom=fields[18],
        bounds=(fields[19] / 1e7, fields[20] / 1e7, fields[21] / 1e7, fields[22] / 1e7),
    )  # fmt: skip


def decompress(data: bytes, compression: int) -> bytes:
    """Undo one of the header's compressions."""
    if compression == COMPRESSION_NONE:
        return data
    if compression == COMPRESSION_GZIP:
        try:
            return gzip.decompress(data)
        except (OSError, EOFError) as exc:
            raise PMTilesError(f"Corrupt gzip data in the archive: {exc}") from exc
    raise PMTilesError(f"PMTiles compression {compression} is not supported (only none and gzip).")


def _varints(data: bytes) -> list[int]:
    values: list[int] = []
    value = shift = 0
    for byte in data:
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            values.append(value)
            value = shift = 0
    if shift:
        raise PMTilesError("A PMTiles directory ends inside a number.")
    return values


def _parse_directory(data: bytes, compression: int) -> list[_Entry]:
    numbers = _varints(decompress(data, compression))
    count = numbers[0] if numbers else 0
    if not count or len(numbers) != 1 + 4 * count:
        raise PMTilesError("A PMTiles directory does not hold the entries it declares.")
    deltas, runs, lengths, offsets = (
        numbers[1 + k * count : 1 + (k + 1) * count] for k in range(4)
    )
    entries: list[_Entry] = []
    tile = 0
    for i in range(count):
        tile += deltas[i]
        if offsets[i] == 0:
            if i == 0:
                raise PMTilesError("A PMTiles directory's first entry has no offset.")
            offset = entries[-1].offset + entries[-1].length
        else:
            offset = offsets[i] - 1
        entries.append(_Entry(tile, offset, lengths[i], runs[i]))
    return entries


class Archive:
    """A PMTiles archive read through `read(offset, length)`.

    The first read takes the header and root directory together; leaf
    directories are read once each and kept.
    """

    def __init__(self, read: ReadRange) -> None:
        self._read = read
        head = read(0, ROOT_REACH_BYTES)
        self.header = _parse_header(head)
        root_end = self.header.root_offset + self.header.root_length
        if root_end <= len(head):
            root = head[self.header.root_offset : root_end]
        else:
            root = self._exactly(self.header.root_offset, self.header.root_length)
        self._root = _parse_directory(root, self.header.internal_compression)
        self._leaves: dict[tuple[int, int], list[_Entry]] = {}

    @classmethod
    def open(cls, path: Path) -> Archive:
        """A local archive. Each read opens the file, so there is nothing to close."""

        def read(offset: int, length: int) -> bytes:
            with open(path, "rb") as f:
                f.seek(offset)
                return f.read(length)

        return cls(read)

    def _exactly(self, offset: int, length: int) -> bytes:
        data = self._read(offset, length)
        if len(data) != length:
            raise PMTilesError(
                f"The archive ends early: wanted {length} bytes at {offset}, got {len(data)}."
            )
        return data

    def metadata(self) -> dict[str, Any]:
        """The archive's JSON metadata."""
        raw = self._exactly(self.header.metadata_offset, self.header.metadata_length)
        try:
            document = json.loads(decompress(raw, self.header.internal_compression))
        except ValueError as exc:
            raise PMTilesError(f"The archive's metadata is not JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise PMTilesError("The archive's metadata is not a JSON object.")
        return document

    def locate(self, z: int, x: int, y: int) -> tuple[int, int] | None:
        """Where tile `z/x/y` is stored, as (offset in the file, length); None if absent."""
        wanted = tile_id(z, x, y)
        directory = self._root
        for _ in range(4):  # the root and at most three levels of leaves
            at = bisect_right(directory, wanted, key=lambda entry: entry.tile_id) - 1
            if at < 0:
                return None
            entry = directory[at]
            if entry.run_length == 0:
                directory = self._leaf(entry.offset, entry.length)
            elif wanted - entry.tile_id < entry.run_length:
                return self.header.tile_data_offset + entry.offset, entry.length
            else:
                return None
        raise PMTilesError("The archive's directories are nested too deep.")

    def _leaf(self, offset: int, length: int) -> list[_Entry]:
        if (offset, length) not in self._leaves:
            data = self._exactly(self.header.leaf_offset + offset, length)
            self._leaves[offset, length] = _parse_directory(data, self.header.internal_compression)
        return self._leaves[offset, length]

    def tile(self, z: int, x: int, y: int) -> bytes | None:
        """Tile `z/x/y` as stored (compressed as the header says); None if absent."""
        where = self.locate(z, x, y)
        return None if where is None else self._exactly(*where)


# --- Writing ------------------------------------------------------------------


def _varint(value: int) -> bytes:
    out = bytearray()
    while value >= 0x80:
        out.append(value & 0x7F | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _gzip(data: bytes) -> bytes:
    return gzip.compress(data, mtime=0)  # no timestamp: the same input gives the same bytes


def _directory(entries: list[_Entry]) -> bytes:
    out = bytearray(_varint(len(entries)))
    previous = 0
    for entry in entries:
        out += _varint(entry.tile_id - previous)
        previous = entry.tile_id
    for entry in entries:
        out += _varint(entry.run_length)
    for entry in entries:
        out += _varint(entry.length)
    for i, entry in enumerate(entries):
        follows = i > 0 and entry.offset == entries[i - 1].offset + entries[i - 1].length
        out += _varint(0 if follows else entry.offset + 1)
    return _gzip(bytes(out))


def _directories(entries: list[_Entry]) -> tuple[bytes, bytes]:
    """The root directory and the leaf section. Leaves only if the root alone is too big."""
    room = ROOT_REACH_BYTES - HEADER_BYTES
    root = _directory(entries)
    per_leaf = 4096
    while len(root) > room:
        leaves = bytearray()
        pointers: list[_Entry] = []
        for start in range(0, len(entries), per_leaf):
            leaf = _directory(entries[start : start + per_leaf])
            pointers.append(_Entry(entries[start].tile_id, len(leaves), len(leaf), 0))
            leaves += leaf
        root = _directory(pointers)
        if len(root) <= room:
            return root, bytes(leaves)
        per_leaf *= 2
    return root, b""


def write_archive(
    path: Path,
    tiles: Mapping[Zxy, bytes],
    *,
    metadata: Mapping[str, Any],
    tile_compression: int,
    bounds: tuple[float, float, float, float],
    tile_type: int = TILE_TYPE_MVT,
) -> None:
    """Write `tiles` (each already compressed as `tile_compression` says) as an archive.

    The same tiles and metadata give the same bytes. Tiles with the same
    content are stored once.
    """
    if not tiles:
        raise PMTilesError("An archive needs at least one tile.")
    data = bytearray()
    stored: dict[bytes, int] = {}
    entries: list[_Entry] = []
    for tile, (z, x, y) in sorted((tile_id(*zxy), zxy) for zxy in tiles):
        content = tiles[z, x, y]
        if content not in stored:
            stored[content] = len(data)
            data += content
        entries.append(_Entry(tile, stored[content], len(content), 1))
    root, leaves = _directories(entries)
    meta = _gzip(json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode())
    zooms = [z for z, _, _ in tiles]
    west, south, east, north = (round(value * 1e7) for value in bounds)
    root_offset = HEADER_BYTES
    metadata_offset = root_offset + len(root)
    leaf_offset = metadata_offset + len(meta)
    tile_data_offset = leaf_offset + len(leaves)
    header = _HEADER.pack(
        _MAGIC, _VERSION,
        root_offset, len(root), metadata_offset, len(meta), leaf_offset, len(leaves),
        tile_data_offset, len(data),
        len(entries), len(entries), len(stored),
        1, COMPRESSION_GZIP, tile_compression, tile_type,
        min(zooms), max(zooms),
        west, south, east, north,
        min(zooms), (west + east) // 2, (south + north) // 2,
    )  # fmt: skip
    path.write_bytes(header + root + meta + leaves + bytes(data))
