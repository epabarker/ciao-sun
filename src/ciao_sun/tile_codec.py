"""Tile format f1: the storage code for Horizon profiles and the tile codec.

`docs/tile-format-f1.md` is the specification; this module is one
implementation of it. The reader here is the one the reference scorer and the
tests use, so nothing else in the package parses tile bytes.
"""

from __future__ import annotations

import gzip
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

# The storage code: 228 codes in a uint8.
#   codes   0-120: -2.0 deg to 10.0 deg in 0.1 deg steps
#   codes 121-227: 10.5 deg to 63.5 deg in 0.5 deg steps
CODE_COUNT = 228
_FINE_MIN_DEG = -2.0
_FINE_STEP_DEG = 0.1
_FINE_TOP_CODE = 120
_FINE_TOP_DEG = 10.0
_COARSE_STEP_DEG = 0.5
_TOP_CODE = CODE_COUNT - 1
# Halfway between the last fine angle (10.0) and the first coarse one (10.5).
_FINE_COARSE_SPLIT_DEG = 10.25


def degrees_to_codes(degrees: npt.ArrayLike) -> npt.NDArray[np.uint8]:
    """Horizon profile angles in degrees -> storage codes.

    Each angle takes the nearest code; angles outside -2.0..63.5 clamp to the
    nearest end of the range.
    """
    deg = np.asarray(degrees, dtype=np.float64)
    if np.isnan(deg).any():
        raise ValueError("Horizon profile angles must not be NaN")
    fine = np.floor((deg - _FINE_MIN_DEG) / _FINE_STEP_DEG + 0.5)
    coarse = _FINE_TOP_CODE + np.floor((deg - _FINE_TOP_DEG) / _COARSE_STEP_DEG + 0.5)
    codes = np.where(deg < _FINE_COARSE_SPLIT_DEG, np.minimum(fine, _FINE_TOP_CODE), coarse)
    return np.clip(codes, 0, _TOP_CODE).astype(np.uint8)


def codes_to_degrees(codes: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Storage codes -> Horizon profile angles in degrees."""
    c = np.asarray(codes, dtype=np.int64)
    if ((c < 0) | (c > _TOP_CODE)).any():
        raise ValueError(f"storage codes must be 0-{_TOP_CODE}; there are only {CODE_COUNT} codes")
    fine = _FINE_MIN_DEG + _FINE_STEP_DEG * c
    coarse = _FINE_TOP_DEG + _COARSE_STEP_DEG * (c - _FINE_TOP_CODE)
    return np.where(c <= _FINE_TOP_CODE, fine, coarse)


# --- The tile ------------------------------------------------------------

FORMAT = 1
# One Horizon profile sample per 0.25 deg of true azimuth, clockwise from true
# north: sample i is at i * 0.25 deg.
PROFILE_SAMPLES = 1440

_MAGIC = b"CSUN"
_GRID_REF = re.compile(r"[A-HJ-Z]{2}[0-9]{4}")
_HEADER = struct.Struct("<4sH6sIIII")
# Node ids stay below 2^53 so a reader can hold them exactly in an IEEE double.
_NODE_ID_LIMIT = 2**53
_NAME_MAX_BYTES = 0xFFFF

_I32 = np.dtype("<i4")
_U32 = np.dtype("<u4")
_U64 = np.dtype("<u8")


class TileFormatError(ValueError):
    """The bytes, or the tile handed to the writer, are not a valid f1 tile."""


class UnsupportedFormatError(TileFormatError):
    """The tile is in a format this reader does not know."""


@dataclass(frozen=True, eq=False)
class Candidates:
    """A tile's Candidates, one array element (or profile row) per Candidate.

    Positions are WGS84 degrees * 1e7. `node_index` indexes the tile's
    walk-graph nodes and `name_index` indexes the tile's Spot names. `offset_cm` is the distance
    from the Candidate to its snapped node.
    """

    lat_e7: npt.NDArray[np.int32]
    lon_e7: npt.NDArray[np.int32]
    node_index: npt.NDArray[np.uint32]
    offset_cm: npt.NDArray[np.uint32]
    name_index: npt.NDArray[np.uint32]
    profile_codes: npt.NDArray[np.uint8]  # shape (Candidates, PROFILE_SAMPLES)


@dataclass(frozen=True, eq=False)
class WalkGraph:
    """A tile's walk graph. Edges refer to nodes by index into the node arrays."""

    node_id: npt.NDArray[np.uint64]
    node_lat_e7: npt.NDArray[np.int32]
    node_lon_e7: npt.NDArray[np.int32]
    edge_from: npt.NDArray[np.uint32]
    edge_to: npt.NDArray[np.uint32]
    edge_length_cm: npt.NDArray[np.uint32]


@dataclass(frozen=True, eq=False)
class Tile:
    """One 1 km BNG tile, named by its OS grid ref (e.g. "ST5873")."""

    grid_ref: str
    names: tuple[str, ...]
    candidates: Candidates
    walk_graph: WalkGraph

    def spot_name(self, candidate: int) -> str:
        return self.names[int(self.candidates.name_index[candidate])]

    def horizon_profile_degrees(self, candidate: int) -> npt.NDArray[np.float64]:
        """The Candidate's Horizon profile in degrees, by true azimuth sample."""
        return codes_to_degrees(self.candidates.profile_codes[candidate])


def _column(
    values: npt.NDArray[Any], dtype: np.dtype[Any], count: int, what: str
) -> npt.NDArray[Any]:
    if values.dtype != dtype.newbyteorder("=") or values.shape != (count,):
        raise TileFormatError(
            f"{what} must be {dtype.name} of shape ({count},), "
            f"got {values.dtype.name} of shape {values.shape}"
        )
    return values.astype(dtype, copy=False)


def _check_indexes(indexes: npt.NDArray[np.uint32], limit: int, what: str) -> None:
    if indexes.size and int(indexes.max()) >= limit:
        raise TileFormatError(f"{what} {int(indexes.max())} is out of range (only {limit} exist)")


def _check_references(tile: Tile) -> None:
    """The rules a tile must obey beyond its byte layout; shared by writer and reader."""
    c, g = tile.candidates, tile.walk_graph
    nodes = g.node_id.shape[0]
    _check_indexes(c.node_index, nodes, "Candidate walk node index")
    _check_indexes(c.name_index, len(tile.names), "Candidate Spot name index")
    _check_indexes(g.edge_from, nodes, "edge 'from' node index")
    _check_indexes(g.edge_to, nodes, "edge 'to' node index")
    if c.profile_codes.size and int(c.profile_codes.max()) >= CODE_COUNT:
        raise TileFormatError(
            f"Horizon profile code {int(c.profile_codes.max())} is not one of the "
            f"{CODE_COUNT} storage codes"
        )
    if g.node_id.size and int(g.node_id.max()) >= _NODE_ID_LIMIT:
        raise TileFormatError("walk node ids must be below 2^53")
    if np.unique(g.node_id).size != g.node_id.size:
        raise TileFormatError("walk node ids must be unique within a tile")


def encode_tile(tile: Tile) -> bytes:
    """A tile -> the bytes of its published `.bin` file."""
    if not _GRID_REF.fullmatch(tile.grid_ref):
        raise TileFormatError(f"{tile.grid_ref!r} is not a 1 km OS grid ref like 'ST5873'")
    c, g = tile.candidates, tile.walk_graph
    n_cand, n_node, n_edge = c.lat_e7.shape[0], g.node_id.shape[0], g.edge_from.shape[0]
    columns = [
        _column(c.lat_e7, _I32, n_cand, "Candidate latitude"),
        _column(c.lon_e7, _I32, n_cand, "Candidate longitude"),
        _column(c.node_index, _U32, n_cand, "Candidate walk node index"),
        _column(c.offset_cm, _U32, n_cand, "Candidate offset"),
        _column(c.name_index, _U32, n_cand, "Candidate Spot name index"),
        _column(g.node_id, _U64, n_node, "walk node id"),
        _column(g.node_lat_e7, _I32, n_node, "walk node latitude"),
        _column(g.node_lon_e7, _I32, n_node, "walk node longitude"),
        _column(g.edge_from, _U32, n_edge, "edge 'from' node index"),
        _column(g.edge_to, _U32, n_edge, "edge 'to' node index"),
        _column(g.edge_length_cm, _U32, n_edge, "edge length"),
    ]
    if c.profile_codes.dtype != np.uint8 or c.profile_codes.shape != (n_cand, PROFILE_SAMPLES):
        raise TileFormatError(
            f"Horizon profile codes must be uint8 of shape ({n_cand}, {PROFILE_SAMPLES}), "
            f"got {c.profile_codes.dtype.name} of shape {c.profile_codes.shape}"
        )
    _check_references(tile)

    # Delta along azimuth, mod 256: uint8 subtraction wraps, which is the rule.
    deltas = c.profile_codes.copy()
    deltas[:, 1:] -= c.profile_codes[:, :-1]

    parts = [
        _HEADER.pack(
            _MAGIC, FORMAT, tile.grid_ref.encode("ascii"), n_cand, n_node, n_edge, len(tile.names)
        ),
        *(column.tobytes() for column in columns),
        deltas.tobytes(),
    ]
    for name in tile.names:
        encoded = name.encode("utf-8")
        if len(encoded) > _NAME_MAX_BYTES:
            raise TileFormatError(f"Spot name is longer than {_NAME_MAX_BYTES} UTF-8 bytes")
        parts += [struct.pack("<H", len(encoded)), encoded]
    # mtime=0 keeps the bytes a pure function of the tile.
    return gzip.compress(b"".join(parts), compresslevel=9, mtime=0)


class _Cursor:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._at = 0

    def take(self, size: int) -> bytes:
        end = self._at + size
        if end > len(self._data):
            raise TileFormatError("tile is truncated")
        chunk = self._data[self._at : end]
        self._at = end
        return chunk

    def column(self, dtype: np.dtype[Any], count: int) -> npt.NDArray[Any]:
        raw = np.frombuffer(self.take(dtype.itemsize * count), dtype=dtype)
        return raw.astype(dtype.newbyteorder("="))

    def at_end(self) -> bool:
        return self._at == len(self._data)


def decode_tile(data: bytes) -> Tile:
    """The bytes of a published `.bin` file -> the tile."""
    try:
        cursor = _Cursor(gzip.decompress(data))
    except (OSError, EOFError, zlib.error) as exc:
        raise TileFormatError(f"tile is not valid gzip: {exc}") from exc

    magic, fmt, grid_ref, n_cand, n_node, n_edge, n_name = _HEADER.unpack(cursor.take(_HEADER.size))
    if magic != _MAGIC:
        raise TileFormatError("not a Ciao Sun tile (bad magic)")
    if fmt != FORMAT:
        raise UnsupportedFormatError(
            f"tile is format f{fmt}; this reader only understands f{FORMAT}"
        )

    lat_e7, lon_e7 = cursor.column(_I32, n_cand), cursor.column(_I32, n_cand)
    node_index, offset_cm, name_index = (cursor.column(_U32, n_cand) for _ in range(3))
    node_id = cursor.column(_U64, n_node)
    node_lat_e7, node_lon_e7 = cursor.column(_I32, n_node), cursor.column(_I32, n_node)
    edge_from, edge_to, edge_length_cm = (cursor.column(_U32, n_edge) for _ in range(3))
    deltas = cursor.column(np.dtype(np.uint8), n_cand * PROFILE_SAMPLES)
    # Undo the azimuth delta: a running sum mod 256.
    profile_codes = np.cumsum(deltas.reshape(n_cand, PROFILE_SAMPLES), axis=1, dtype=np.uint8)
    try:
        names = tuple(
            cursor.take(struct.unpack("<H", cursor.take(2))[0]).decode("utf-8")
            for _ in range(n_name)
        )
    except UnicodeDecodeError as exc:
        raise TileFormatError("Spot name is not valid UTF-8") from exc
    if not cursor.at_end():
        raise TileFormatError("tile has bytes after its last field")

    tile = Tile(
        grid_ref=grid_ref.decode("ascii", errors="replace"),
        names=names,
        candidates=Candidates(lat_e7, lon_e7, node_index, offset_cm, name_index, profile_codes),
        walk_graph=WalkGraph(node_id, node_lat_e7, node_lon_e7, edge_from, edge_to, edge_length_cm),
    )
    if not _GRID_REF.fullmatch(tile.grid_ref):
        raise TileFormatError(f"{tile.grid_ref!r} is not a 1 km OS grid ref")
    _check_references(tile)
    return tile


def write_tile(tile: Tile, directory: Path) -> Path:
    """Write a tile into `directory` as `<grid ref>.bin` and return its path."""
    data = encode_tile(tile)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{tile.grid_ref}.bin"
    path.write_bytes(data)
    return path


def read_tile(path: Path) -> Tile:
    """Read a tile file, checking it is the tile its file name says it is."""
    tile = decode_tile(path.read_bytes())
    if path.name != f"{tile.grid_ref}.bin":
        raise TileFormatError(f"{path.name} holds tile {tile.grid_ref}")
    return tile
