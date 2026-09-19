"""Optional walking-distance ranking via OSMnx (feature-flagged, off by default).

Walking distance also implicitly filters out candidates in private gardens
(no path reaches them), which straight-line ranking cannot do.
"""

from __future__ import annotations

import warnings

import numpy as np


def walk_distances(
    home_lat: float,
    home_lon: float,
    lat: np.ndarray,
    lon: np.ndarray,
    radius_m: float,
) -> np.ndarray | None:
    """Shortest walking-network distance (m) from home to each point, or None.

    Returns None (with a warning) if osmnx/networkx are not installed, so
    callers can fall back to straight-line distance.
    """
    try:
        import networkx as nx
        import osmnx as ox
    except ImportError:
        warnings.warn(
            "osmnx/networkx not installed; falling back to straight-line distance. "
            "Install sunspot[routing] to enable walking distance.",
            stacklevel=2,
        )
        return None

    # osmnx otherwise drops a `cache/` directory in the current working
    # directory by default; keep it alongside our own raster cache instead.
    ox.settings.cache_folder = "data/cache/osmnx"

    graph = ox.graph_from_point(
        (home_lat, home_lon), dist=radius_m + 200.0, network_type="walk"
    )
    home_node = ox.distance.nearest_nodes(graph, home_lon, home_lat)
    nodes = ox.distance.nearest_nodes(graph, lon.tolist(), lat.tolist())

    out = np.full(len(lat), np.nan, dtype="float64")
    for i, node in enumerate(nodes):
        try:
            out[i] = nx.shortest_path_length(graph, home_node, node, weight="length")
        except nx.NetworkXNoPath:
            out[i] = np.nan
    return out
