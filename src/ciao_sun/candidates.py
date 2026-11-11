"""Candidates, the walk graph and Spot names for one 1 km tile, from OSM and LIDAR.

`load_walk_network` reads the dated `.osm.pbf` once. `build_tile` then gives one
tile's Candidates and walk graph as a `TileOutline`: everything in the tile
except the Horizon profiles, which the horizon precompute adds with
`TileOutline.with_profiles`.

The rules, all from the Stage 1 spec:

- The walk graph is the public walkable OSM ways. Every OSM node along a way is a
  graph node, and its id is the OSM node id, so ids agree across tiles.
- A tile holds every edge that touches its square, so an edge that crosses a
  tile boundary is in both tiles.
- Candidates are the points whose easting and northing are multiples of 10 m,
  on open ground (last-return DSM - DTM <= 1 m), within 12 m of a walk edge.
- A Candidate snaps to the nearer end of its nearest edge.
- Its Spot name is the smallest named green space containing it, else its
  nearest edge's name, else "Path", "Lane" or "Steps" "off" the named street
  nearest its snapped node along the walk graph.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import osmium
from pyproj import Transformer

from ciao_sun.raster import RasterGrid, sample
from ciao_sun.tile_codec import Candidates, Tile, WalkGraph

# A Candidate is at most this far from a public walk edge. Binding: the spec
# sets it over the older routing module's unlimited snap.
SNAP_M = 12.0
CANDIDATE_SPACING_M = 10
# Open ground: the last-return surface is at most this far above the bare earth.
OPEN_GROUND_MAX_M = 1.0
TILE_M = 1000

_WGS84_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
_BNG_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)

_Floats = npt.NDArray[np.float64]

# --- 1 km OS grid refs -------------------------------------------------------

_HUNDRED_KM = 100_000
_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"  # the grid has no I


def _square_letters(e100k: int, n100k: int) -> str:
    """The two letters of a 100 km square (OS, "A guide to coordinate systems", Annex C)."""
    if not (0 <= e100k <= 6 and 0 <= n100k <= 12):
        raise ValueError(f"100 km square ({e100k}, {n100k}) is outside the National Grid")
    first = (19 - n100k) - (19 - n100k) % 5 + (e100k + 10) // 5
    second = (19 - n100k) * 5 % 25 + e100k % 5
    return _LETTERS[first] + _LETTERS[second]


_SQUARE_ORIGINS = {
    _square_letters(e, n): (e * _HUNDRED_KM, n * _HUNDRED_KM) for e in range(7) for n in range(13)
}


def grid_ref_of(easting: float, northing: float) -> str:
    """The 1 km grid ref (e.g. "ST5873") of the square holding a National Grid point."""
    e100k, n100k = int(easting // _HUNDRED_KM), int(northing // _HUNDRED_KM)
    e_km = int((easting - e100k * _HUNDRED_KM) // TILE_M)
    n_km = int((northing - n100k * _HUNDRED_KM) // TILE_M)
    return f"{_square_letters(e100k, n100k)}{e_km:02d}{n_km:02d}"


def grid_ref_origin(grid_ref: str) -> tuple[int, int]:
    """The (easting, northing) of the south-west corner of a 1 km grid ref's square."""
    origin = _SQUARE_ORIGINS.get(grid_ref[:2])
    if origin is None or len(grid_ref) != 6 or not grid_ref[2:].isdecimal():
        raise ValueError(f"{grid_ref!r} is not a 1 km OS grid ref like 'ST5873'")
    return (origin[0] + int(grid_ref[2:4]) * TILE_M, origin[1] + int(grid_ref[4:6]) * TILE_M)


# --- Reading OSM -------------------------------------------------------------

# `highway` values that are not somewhere to walk.
_NOT_WALKABLE = frozenset(
    {
        "motorway", "motorway_link", "construction", "proposed", "planned", "abandoned",
        "razed", "raceway", "bus_guideway", "busway", "platform", "corridor", "elevator",
        "escalator", "rest_area", "services", "no",
    }
)  # fmt: skip
# `access` / `foot` values that keep the public out.
_NOT_PUBLIC = frozenset(
    {"no", "private", "customers", "delivery", "permit", "residents", "agricultural",
     "forestry", "military"}
)  # fmt: skip
_PRIVATE_SERVICE = frozenset({"private", "driveway"})

_PATH, _LANE, _STEPS = 0, 1, 2
_KIND_WORDS = ("Path", "Lane", "Steps")
_PATH_HIGHWAYS = frozenset({"footway", "path", "pedestrian", "cycleway", "bridleway"})

_GREEN_TAGS = {
    "leisure": frozenset(
        {"park", "common", "recreation_ground", "nature_reserve", "playing_fields"}
    ),
    "landuse": frozenset({"recreation_ground", "village_green", "grass", "meadow", "cemetery"}),
}


def _is_public_walk(tags: Any) -> bool:
    """Whether a way with these tags is one the public may walk along."""
    highway = tags.get("highway")
    if highway is None or highway in _NOT_WALKABLE:
        return False
    if tags.get("area") == "yes" or tags.get("motorroad") == "yes":
        return False
    foot = tags.get("foot")
    if foot is not None:
        # `foot` speaks for people on foot whatever `access` says about vehicles.
        return foot not in _NOT_PUBLIC
    if tags.get("access") in _NOT_PUBLIC:
        return False
    return not (highway == "service" and tags.get("service") in _PRIVATE_SERVICE)


def _way_kind(highway: str) -> int:
    if highway == "steps":
        return _STEPS
    return _PATH if highway in _PATH_HIGHWAYS else _LANE


def _is_named_green_space(tags: Any) -> bool:
    if not tags.get("name") or tags.get("access") in _NOT_PUBLIC:
        return False
    return any(tags.get(key) in values for key, values in _GREEN_TAGS.items())


@dataclass(frozen=True, eq=False)
class _GreenSpace:
    name: str
    area_m2: float
    # Every ring, outer and inner, as segments; a point is inside when a ray from
    # it crosses an odd number of them.
    x1: _Floats
    y1: _Floats
    x2: _Floats
    y2: _Floats

    def contains(self, x: _Floats, y: _Floats) -> npt.NDArray[np.bool_]:
        inside = np.zeros(x.shape, dtype=bool)
        box = (
            (x >= self.x1.min()) & (x <= self.x1.max())
            & (y >= self.y1.min()) & (y <= self.y1.max())
        )  # fmt: skip
        if not box.any():
            return inside
        px, py = x[box][:, None], y[box][:, None]
        straddles = (self.y1 > py) != (self.y2 > py)
        rise = np.where(self.y2 == self.y1, 1.0, self.y2 - self.y1)
        at_x = self.x1 + (py - self.y1) * (self.x2 - self.x1) / rise
        inside[box] = (straddles & (px < at_x)).sum(axis=1) % 2 == 1
        return inside


@dataclass(frozen=True, eq=False)
class WalkNetwork:
    """The public walk network and named green spaces of one OSM extract.

    Build it with `load_walk_network`; hand it to `build_tile`. Its fields are
    for `build_tile`, not for callers.
    """

    node_id: npt.NDArray[np.uint64]  # ascending
    node_lat_e7: npt.NDArray[np.int32]
    node_lon_e7: npt.NDArray[np.int32]
    node_x: _Floats  # National Grid metres
    node_y: _Floats
    # Per node: index into `names` of the named street nearest along the graph, or -1.
    node_street: npt.NDArray[np.int64]
    # Per edge: its end nodes as indexes into the node arrays, with a < b.
    edge_a: npt.NDArray[np.int64]
    edge_b: npt.NDArray[np.int64]
    edge_length_m: _Floats
    edge_kind: npt.NDArray[np.int64]
    edge_name: npt.NDArray[np.int64]  # index into `names`, or -1 if unnamed
    names: tuple[str, ...]
    green_spaces: tuple[_GreenSpace, ...]  # smallest first

    def grid_refs(self) -> list[str]:
        """The 1 km squares that can have a tile: those within the snap distance of an edge."""
        ax, ay = self.node_x[self.edge_a], self.node_y[self.edge_a]
        bx, by = self.node_x[self.edge_b], self.node_y[self.edge_b]
        west = np.floor((np.minimum(ax, bx) - SNAP_M) / TILE_M).astype(np.int64)
        east = np.floor((np.maximum(ax, bx) + SNAP_M) / TILE_M).astype(np.int64)
        south = np.floor((np.minimum(ay, by) - SNAP_M) / TILE_M).astype(np.int64)
        north = np.floor((np.maximum(ay, by) + SNAP_M) / TILE_M).astype(np.int64)
        boxes = np.unique(np.stack([west, east, south, north], axis=1), axis=0)
        squares = {
            (int(i), int(j))
            for w, e, s, n in boxes
            for i in range(w, e + 1)
            for j in range(s, n + 1)
        }
        return sorted(
            grid_ref
            for grid_ref in (grid_ref_of(i * TILE_M, j * TILE_M) for i, j in squares)
            if _touches_square(ax, ay, bx, by, *grid_ref_origin(grid_ref), pad=SNAP_M).any()
        )


def _to_bng(lon_e7: Iterable[int], lat_e7: Iterable[int]) -> tuple[_Floats, _Floats]:
    lon = np.asarray(list(lon_e7), dtype=np.float64) / 1e7
    lat = np.asarray(list(lat_e7), dtype=np.float64) / 1e7
    x, y = _WGS84_TO_BNG.transform(lon, lat)
    return np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)


def _green_space(name: str, rings: list[tuple[bool, list[tuple[int, int]]]]) -> _GreenSpace:
    """`rings` are (is outer, [(lon_e7, lat_e7), ...]) with the first point repeated last."""
    area = 0.0
    x1s, y1s, x2s, y2s = [], [], [], []
    for is_outer, ring in rings:
        x, y = _to_bng((p[0] for p in ring), (p[1] for p in ring))
        ring_area = 0.5 * abs(float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])))
        area += ring_area if is_outer else -ring_area
        x1s.append(x[:-1])
        y1s.append(y[:-1])
        x2s.append(x[1:])
        y2s.append(y[1:])
    return _GreenSpace(
        name, area, np.concatenate(x1s), np.concatenate(y1s), np.concatenate(x2s),
        np.concatenate(y2s),
    )  # fmt: skip


def _nearest_named_street(
    n_nodes: int,
    edge_a: npt.NDArray[np.int64],
    edge_b: npt.NDArray[np.int64],
    edge_length_m: _Floats,
    edge_name: npt.NDArray[np.int64],
    names: tuple[str, ...],
) -> npt.NDArray[np.int64]:
    """For every node, the named street nearest along the graph (-1 if none is joined).

    One Dijkstra from every node on a named edge at once. Equal distances go to
    the name that sorts first, so the answer does not depend on file order.
    """
    neighbours: list[list[tuple[int, float]]] = [[] for _ in range(n_nodes)]
    heap: list[tuple[float, str, int, int]] = []
    for a, b, length, name in zip(
        edge_a.tolist(), edge_b.tolist(), edge_length_m.tolist(), edge_name.tolist(), strict=True
    ):
        neighbours[a].append((b, length))
        neighbours[b].append((a, length))
        if name >= 0:
            heap.append((0.0, names[name], name, a))
            heap.append((0.0, names[name], name, b))
    heapq.heapify(heap)
    street = np.full(n_nodes, -1, dtype=np.int64)
    while heap:
        distance, text, name, node = heapq.heappop(heap)
        if street[node] >= 0:
            continue
        street[node] = name
        for other, length in neighbours[node]:
            if street[other] < 0:
                heapq.heappush(heap, (distance + length, text, name, other))
    return street


def load_walk_network(osm_pbf: Path) -> WalkNetwork:
    """Read the public walk network and the named green spaces from an OSM extract."""
    node_position: dict[int, tuple[int, int]] = {}  # id -> (lon_e7, lat_e7)
    edges: dict[tuple[int, int], tuple[int, str | None]] = {}  # (id, id) -> (kind, name)
    spaces: list[_GreenSpace] = []

    for obj in osmium.FileProcessor(str(osm_pbf)).with_locations().with_areas():
        if isinstance(obj, osmium.osm.Way):
            if not _is_public_walk(obj.tags):
                continue
            kind, name = _way_kind(obj.tags["highway"]), obj.tags.get("name") or None
            # A way can run on past the edge of the extract, where its nodes are missing.
            here = [
                (n.ref, n.location.x, n.location.y) for n in obj.nodes if n.location.valid()
            ]
            for (a, a_lon, a_lat), (b, b_lon, b_lat) in zip(here, here[1:], strict=False):
                if a == b:
                    continue
                node_position[a], node_position[b] = (a_lon, a_lat), (b_lon, b_lat)
                key = (min(a, b), max(a, b))
                # Two ways along the same pair of nodes are one edge; a name wins.
                if key not in edges or (edges[key][1] is None and name is not None):
                    edges[key] = (kind, name)
        elif isinstance(obj, osmium.osm.Area) and _is_named_green_space(obj.tags):
            rings: list[tuple[bool, list[tuple[int, int]]]] = []
            for outer in obj.outer_rings():
                rings.append((True, [(n.location.x, n.location.y) for n in outer]))
                for inner in obj.inner_rings(outer):
                    rings.append((False, [(n.location.x, n.location.y) for n in inner]))
            if rings:
                spaces.append(_green_space(obj.tags["name"], rings))

    node_id = np.array(sorted(node_position), dtype=np.uint64)
    index_of = {int(osm_id): index for index, osm_id in enumerate(node_id.tolist())}
    lon_e7 = [node_position[osm_id][0] for osm_id in index_of]
    lat_e7 = [node_position[osm_id][1] for osm_id in index_of]
    node_x, node_y = _to_bng(lon_e7, lat_e7)

    pairs = sorted(edges)
    names = tuple(sorted({name for _, name in edges.values() if name is not None}))
    name_index = {name: index for index, name in enumerate(names)}
    edge_a = np.array([index_of[a] for a, _ in pairs], dtype=np.int64)
    edge_b = np.array([index_of[b] for _, b in pairs], dtype=np.int64)
    edge_kind = np.array([edges[pair][0] for pair in pairs], dtype=np.int64)
    edge_name = np.array(
        [-1 if (name := edges[pair][1]) is None else name_index[name] for pair in pairs],
        dtype=np.int64,
    )
    edge_length_m = np.hypot(node_x[edge_a] - node_x[edge_b], node_y[edge_a] - node_y[edge_b])

    return WalkNetwork(
        node_id=node_id,
        node_lat_e7=np.array(lat_e7, dtype=np.int32),
        node_lon_e7=np.array(lon_e7, dtype=np.int32),
        node_x=node_x,
        node_y=node_y,
        node_street=_nearest_named_street(
            node_id.size, edge_a, edge_b, edge_length_m, edge_name, names
        ),
        edge_a=edge_a,
        edge_b=edge_b,
        edge_length_m=edge_length_m,
        edge_kind=edge_kind,
        edge_name=edge_name,
        names=names,
        green_spaces=tuple(sorted(spaces, key=lambda space: (space.area_m2, space.name))),
    )


# --- Building a tile ---------------------------------------------------------


@dataclass(frozen=True, eq=False)
class TileOutline:
    """One tile's Candidates and walk graph: the whole tile but its Horizon profiles.

    Candidates are in order of northing, then easting. `easting` and `northing`
    are their National Grid positions, for casting their Horizon profiles; the
    other fields are as in the tile codec's `Candidates`.
    """

    grid_ref: str
    easting: _Floats
    northing: _Floats
    lat_e7: npt.NDArray[np.int32]
    lon_e7: npt.NDArray[np.int32]
    node_index: npt.NDArray[np.uint32]
    offset_cm: npt.NDArray[np.uint32]
    name_index: npt.NDArray[np.uint32]
    names: tuple[str, ...]
    walk_graph: WalkGraph

    def with_profiles(self, profile_codes: npt.NDArray[np.uint8]) -> Tile:
        """The finished tile, given each Candidate's Horizon profile as storage codes."""
        return Tile(
            grid_ref=self.grid_ref,
            names=self.names,
            candidates=Candidates(
                self.lat_e7, self.lon_e7, self.node_index, self.offset_cm, self.name_index,
                profile_codes,
            ),  # fmt: skip
            walk_graph=self.walk_graph,
        )


def _touches_square(
    ax: _Floats, ay: _Floats, bx: _Floats, by: _Floats, west: float, south: float, pad: float = 0.0
) -> npt.NDArray[np.bool_]:
    """Which segments a-b touch the tile square (edges included), grown by `pad` each way."""
    lo_x, hi_x = west - pad, west + TILE_M + pad
    lo_y, hi_y = south - pad, south + TILE_M + pad
    dx, dy = bx - ax, by - ay
    enter, leave = np.zeros(ax.shape), np.ones(ax.shape)
    possible = np.ones(ax.shape, dtype=bool)
    # Liang-Barsky: clip the segment's parameter range against each side in turn.
    for step, room in ((-dx, ax - lo_x), (dx, hi_x - ax), (-dy, ay - lo_y), (dy, hi_y - ay)):
        level = step == 0
        possible &= ~level | (room >= 0)
        at = room / np.where(level, 1.0, step)
        enter = np.where(step < 0, np.maximum(enter, at), enter)
        leave = np.where(step > 0, np.minimum(leave, at), leave)
    return possible & (enter <= leave)


def _nearest_segment(
    px: _Floats, py: _Floats, ax: _Floats, ay: _Floats, bx: _Floats, by: _Floats
) -> tuple[npt.NDArray[np.int64], _Floats]:
    """For each point, its nearest segment a-b and the distance to it.

    Distances equal to the millimetre go to the earlier segment.
    """
    dx, dy = bx - ax, by - ay
    length2 = np.where((dx == 0) & (dy == 0), 1.0, dx * dx + dy * dy)
    which = np.empty(px.size, dtype=np.int64)
    distance = np.empty(px.size, dtype=np.float64)
    chunk = max(1, 2_000_000 // max(1, ax.size))
    for start in range(0, px.size, chunk):
        x, y = px[start : start + chunk, None], py[start : start + chunk, None]
        along = np.clip(((x - ax) * dx + (y - ay) * dy) / length2, 0.0, 1.0)
        d = np.hypot(x - (ax + along * dx), y - (ay + along * dy))
        nearest = np.argmin(np.rint(d * 1000.0), axis=1)
        which[start : start + chunk] = nearest
        distance[start : start + chunk] = d[np.arange(nearest.size), nearest]
    return which, distance


def build_tile(
    network: WalkNetwork, grid_ref: str, dsm: RasterGrid, dtm: RasterGrid
) -> TileOutline | None:
    """One 1 km tile's Candidates and walk graph, or None if the square has neither.

    `dsm` is the last-return surface and `dtm` the bare earth; where either has
    no data there are no Candidates.
    """
    west, south = grid_ref_origin(grid_ref)
    ax, ay = network.node_x[network.edge_a], network.node_y[network.edge_a]
    bx, by = network.node_x[network.edge_b], network.node_y[network.edge_b]

    # Edges a Candidate of this tile could snap to. Named edges go first, so a
    # Candidate equally near a street and an unnamed way takes the street.
    near = np.flatnonzero(_touches_square(ax, ay, bx, by, west, south, pad=SNAP_M))
    near = near[np.argsort(network.edge_name[near] < 0, kind="stable")]

    steps = np.arange(0, TILE_M, CANDIDATE_SPACING_M, dtype=np.float64)
    grid_x, grid_y = np.meshgrid(west + steps, south + steps)
    x, y = grid_x.ravel(), grid_y.ravel()
    if near.size:
        with np.errstate(invalid="ignore"):
            open_ground = (sample(dsm, x, y) - sample(dtm, x, y)) <= OPEN_GROUND_MAX_M
        x, y = x[open_ground], y[open_ground]
        nearest, distance = _nearest_segment(x, y, ax[near], ay[near], bx[near], by[near])
        snapped = distance <= SNAP_M
        x, y, edge = x[snapped], y[snapped], near[nearest[snapped]]
    else:
        x, y, edge = x[:0], y[:0], near

    in_tile = np.zeros(network.edge_a.size, dtype=bool)
    in_tile[_touches_square(ax, ay, bx, by, west, south)] = True
    # A Candidate by the boundary can snap to an edge wholly in the next square.
    in_tile[edge] = True
    tile_edges = np.flatnonzero(in_tile)
    if tile_edges.size == 0:
        return None
    tile_nodes = np.unique(np.concatenate([network.edge_a[tile_edges], network.edge_b[tile_edges]]))

    # Snap each Candidate to the nearer end of its edge (the lower node id if equal).
    to_a = np.hypot(x - ax[edge], y - ay[edge])
    to_b = np.hypot(x - bx[edge], y - by[edge])
    node = np.where(to_a <= to_b, network.edge_a[edge], network.edge_b[edge])
    offset_cm = np.rint(np.minimum(to_a, to_b) * 100.0).astype(np.uint32)

    spot_names = np.full(x.size, None, dtype=object)
    for space in network.green_spaces:  # smallest first, so the first to claim one wins
        unnamed = np.flatnonzero(spot_names == None)  # noqa: E711 (elementwise)
        spot_names[unnamed[space.contains(x[unnamed], y[unnamed])]] = space.name
    for i in np.flatnonzero(spot_names == None):  # noqa: E711
        name, street = network.edge_name[edge[i]], network.node_street[node[i]]
        if name >= 0:
            spot_names[i] = network.names[name]
        else:
            kind = _KIND_WORDS[network.edge_kind[edge[i]]]
            spot_names[i] = kind if street < 0 else f"{kind} off {network.names[street]}"
    names = tuple(sorted(set(spot_names.tolist())))
    name_index = {name: index for index, name in enumerate(names)}

    lon, lat = _BNG_TO_WGS84.transform(x, y)
    return TileOutline(
        grid_ref=grid_ref,
        easting=x,
        northing=y,
        lat_e7=np.rint(np.asarray(lat) * 1e7).astype(np.int32),
        lon_e7=np.rint(np.asarray(lon) * 1e7).astype(np.int32),
        node_index=np.searchsorted(tile_nodes, node).astype(np.uint32),
        offset_cm=offset_cm,
        name_index=np.array([name_index[name] for name in spot_names], dtype=np.uint32),
        names=names,
        walk_graph=WalkGraph(
            node_id=network.node_id[tile_nodes],
            node_lat_e7=network.node_lat_e7[tile_nodes],
            node_lon_e7=network.node_lon_e7[tile_nodes],
            edge_from=np.searchsorted(tile_nodes, network.edge_a[tile_edges]).astype(np.uint32),
            edge_to=np.searchsorted(tile_nodes, network.edge_b[tile_edges]).astype(np.uint32),
            edge_length_cm=np.rint(network.edge_length_m[tile_edges] * 100.0).astype(np.uint32),
        ),
    )
