"""The built tiles as one world: every Candidate, and walks over the joined walk graph.

Tiles are read through the codec only (`docs/tile-format-f1.md`). The JS
scorer must use the same distance formula, snap and walk rules as this module.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from ciao_sun.tile_codec import Tile, read_tile

WALK_SPEED_M_PER_MIN = 80.0
# Mean Earth radius (IUGG), metres: the one lat/lon distance formula's only constant.
EARTH_RADIUS_M = 6_371_008.8


def load_tiles(directory: Path) -> list[Tile]:
    """Every tile in a build's `tiles/` directory, in grid ref order."""
    return [read_tile(path) for path in sorted(directory.glob("*.bin"))]


def distance_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle (haversine) distance between two WGS84 positions, in metres."""
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    half_dphi = (phi_b - phi_a) / 2.0
    half_dlambda = math.radians(lon_b - lon_a) / 2.0
    h = math.sin(half_dphi) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(half_dlambda) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


@dataclass(frozen=True, eq=False)
class World:
    """All Candidates of the tiles, in (grid ref, index) order, and the joined walk graph.

    Element `k` of every Candidate array is Candidate `k`. Nodes are joined on
    node id; two edges between the same pair of ids are one edge.
    """

    grid_ref: tuple[str, ...]
    index: npt.NDArray[np.int64]  # the Candidate's index within its tile
    name: tuple[str, ...]  # Spot name
    lat: npt.NDArray[np.float64]
    lon: npt.NDArray[np.float64]
    node: npt.NDArray[np.int64]  # into the node arrays below
    offset_cm: npt.NDArray[np.int64]
    profile_codes: npt.NDArray[np.uint8]  # (Candidates, PROFILE_SAMPLES)
    node_lat: npt.NDArray[np.float64]
    node_lon: npt.NDArray[np.float64]
    edges: tuple[tuple[int, int, int], ...]  # (node, node, length in cm), sorted by node ids

    def candidate_id(self, k: int) -> str:
        return f"{self.grid_ref[k]}/{int(self.index[k])}"

    def candidate_order(self, k: int) -> tuple[str, int]:
        """The ascending order of candidateIds: by grid ref, then by index as a number."""
        return (self.grid_ref[k], int(self.index[k]))


def join_tiles(tiles: Sequence[Tile]) -> World:
    node_of_id: dict[int, int] = {}
    node_lat: list[float] = []
    node_lon: list[float] = []
    edge_length: dict[tuple[int, int], int] = {}
    grid_ref: list[str] = []
    name: list[str] = []
    index, lat, lon, node, offset, codes = [], [], [], [], [], []

    for tile in sorted(tiles, key=lambda t: t.grid_ref):
        g, c = tile.walk_graph, tile.candidates
        local = np.empty(g.node_id.shape[0], dtype=np.int64)
        for i, node_id in enumerate(g.node_id.tolist()):
            if node_id not in node_of_id:
                node_of_id[node_id] = len(node_lat)
                node_lat.append(int(g.node_lat_e7[i]) / 1e7)
                node_lon.append(int(g.node_lon_e7[i]) / 1e7)
            local[i] = node_of_id[node_id]
        for a, b, length in zip(
            g.edge_from.tolist(), g.edge_to.tolist(), g.edge_length_cm.tolist(), strict=True
        ):
            ids = (int(g.node_id[a]), int(g.node_id[b]))
            edge_length.setdefault((min(ids), max(ids)), length)
        count = c.lat_e7.shape[0]
        grid_ref += [tile.grid_ref] * count
        name += [tile.spot_name(k) for k in range(count)]
        index.append(np.arange(count, dtype=np.int64))
        lat.append(c.lat_e7 / 1e7)
        lon.append(c.lon_e7 / 1e7)
        node.append(local[c.node_index.astype(np.int64)])
        offset.append(c.offset_cm.astype(np.int64))
        codes.append(c.profile_codes)

    def joined(parts: list[npt.NDArray[np.int64]]) -> npt.NDArray[np.int64]:
        return np.concatenate(parts) if parts else np.empty(0, dtype=np.int64)

    return World(
        grid_ref=tuple(grid_ref),
        index=joined(index),
        name=tuple(name),
        lat=np.concatenate(lat) if lat else np.empty(0),
        lon=np.concatenate(lon) if lon else np.empty(0),
        node=joined(node),
        offset_cm=joined(offset),
        profile_codes=np.concatenate(codes) if codes else np.empty((0, 0), dtype=np.uint8),
        node_lat=np.array(node_lat),
        node_lon=np.array(node_lon),
        edges=tuple(
            (node_of_id[a], node_of_id[b], length) for (a, b), length in sorted(edge_length.items())
        ),
    )


def walk_metres(
    world: World, origin_lat: float, origin_lon: float, limit_m: float
) -> npt.NDArray[np.int64]:
    """Walk from the origin to every Candidate in whole metres; -1 where it exceeds `limit_m`.

    The origin is snapped to the nearest point of the nearest walk edge, each
    edge taken as the straight line between its nodes, on a local flat plane
    centred on the origin. The walk starts at that point (getting to it is not
    counted), splits the snapped edge's length in the same proportion, follows
    the shortest path over the graph (Dijkstra), and ends with the Candidate's
    offset from its node. Centimetres round half up to metres.
    """
    walks = np.full(world.node.shape[0], -1, dtype=np.int64)
    if not world.edges:
        return walks

    # Local plane: metres east and north of the origin.
    east = np.radians(world.node_lon - origin_lon) * math.cos(math.radians(origin_lat))
    north = np.radians(world.node_lat - origin_lat)
    x, y = east * EARTH_RADIUS_M, north * EARTH_RADIUS_M

    best: tuple[float, int, float] | None = None  # (distance, edge, fraction from its first node)
    for e, (a, b, _) in enumerate(world.edges):
        dx, dy = x[b] - x[a], y[b] - y[a]
        span = dx * dx + dy * dy
        t = 0.0 if span == 0.0 else min(1.0, max(0.0, -(x[a] * dx + y[a] * dy) / span))
        away = math.hypot(x[a] + t * dx, y[a] + t * dy)
        if best is None or away < best[0]:
            best = (away, e, t)
    assert best is not None
    _, snapped, fraction = best

    neighbours: dict[int, list[tuple[int, int]]] = {}
    for a, b, length in world.edges:
        neighbours.setdefault(a, []).append((b, length))
        neighbours.setdefault(b, []).append((a, length))

    a, b, length = world.edges[snapped]
    limit_cm = limit_m * 100.0
    reached: dict[int, float] = {}
    queue = [(fraction * length, a), ((1.0 - fraction) * length, b)]
    heapq.heapify(queue)
    while queue:
        so_far, n = heapq.heappop(queue)
        if n in reached or so_far > limit_cm:
            continue
        reached[n] = so_far
        for other, step in neighbours[n]:
            if other not in reached:
                heapq.heappush(queue, (so_far + step, other))

    for k, n in enumerate(world.node.tolist()):
        if n in reached:
            metres = math.floor((reached[n] + int(world.offset_cm[k])) / 100.0 + 0.5)
            if metres <= limit_m:
                walks[k] = metres
    return walks
