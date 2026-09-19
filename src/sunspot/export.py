"""GeoJSON, GeoTIFF, and folium map export of search results."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from pyproj import Transformer

from sunspot.search import SearchResult

_BNG_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


def to_geojson(
    result: SearchResult,
    mask: np.ndarray,
    path: Path,
    walk_metres: np.ndarray | None = None,
    start_idx: np.ndarray | None = None,
    end_idx: np.ndarray | None = None,
    duration_minutes: np.ndarray | None = None,
) -> None:
    """All passing candidates as a GeoJSON FeatureCollection of points, in WGS84.

    `start_idx`/`end_idx`/`duration_minutes`, if given, are full-length arrays
    aligned to `result` (from `search.clear_window_minutes`) describing each
    candidate's longest unbroken clear window.
    """
    lon, lat = _BNG_TO_WGS84.transform(result.x[mask], result.y[mask])
    dist = result.distance_m[mask]
    frac = result.fraction_clear[mask]
    idx_full = np.nonzero(mask)[0]
    features = []
    for i in range(len(lon)):
        full_idx = idx_full[i]
        props: dict[str, float | str] = {
            "metres_from_home": float(dist[i]),
            "fraction_clear": float(frac[i]),
        }
        if walk_metres is not None:
            props["walk_metres"] = float(walk_metres[i])
        if start_idx is not None and end_idx is not None and duration_minutes is not None:
            s, e = start_idx[full_idx], end_idx[full_idx]
            if s >= 0:
                props["sun_visible_from"] = result.times[s].isoformat()
                props["sun_visible_until"] = result.times[e].isoformat()
                props["clear_window_minutes"] = float(duration_minutes[full_idx])
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon[i]), float(lat[i])]},
                "properties": props,
            }
        )
    fc = {"type": "FeatureCollection", "features": features}
    Path(path).write_text(json.dumps(fc))


def _rasterize_candidates(
    result: SearchResult,
    values: np.ndarray,
    home_x: float,
    home_y: float,
    radius: float,
    spacing: float,
) -> tuple[np.ndarray, float, float, int]:
    """Scatter per-candidate `values` onto the regular grid they were sampled
    on. Returns (grid, origin_x, origin_y_top, n) where grid is n x n, NaN
    where there is no candidate, north-up (row 0 is the northern edge).
    """
    n = int(round(2 * radius / spacing)) + 1
    grid = np.full((n, n), np.nan, dtype="float64")
    origin_x = home_x - radius
    origin_y_top = home_y + radius
    col = np.rint((result.x - origin_x) / spacing).astype(np.int64)
    row = np.rint((origin_y_top - result.y) / spacing).astype(np.int64)
    ok = (row >= 0) & (row < n) & (col >= 0) & (col < n)
    grid[row[ok], col[ok]] = values[ok]
    return grid, origin_x, origin_y_top, n


def to_horizon_geotiff(
    result: SearchResult,
    home_x: float,
    home_y: float,
    radius: float,
    spacing: float,
    path: Path,
    crs: str = "EPSG:27700",
) -> None:
    """Per-candidate worst obstruction angle as a GeoTIFF, for inspection in QGIS."""
    import rasterio
    from affine import Affine

    grid, origin_x, origin_y_top, n = _rasterize_candidates(
        result, result.worst_horizon_angle, home_x, home_y, radius, spacing
    )
    transform = Affine(spacing, 0.0, origin_x, 0.0, -spacing, origin_y_top)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=n,
        width=n,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=np.nan,
    ) as dst:
        dst.write(grid.astype("float32"), 1)


# A minimum alpha for any candidate with a nonzero clear window, so a short
# (e.g. 1-2 minute) window is still faintly visible rather than indistinguishable
# from full transparency at the low end of the colour scale.
_HEATMAP_MIN_ALPHA = 0.15


def _duration_heatmap_png(
    result: SearchResult,
    duration_minutes: np.ndarray,
    home_x: float,
    home_y: float,
    radius: float,
    spacing: float,
    vmax_minutes: float,
    path: Path,
) -> tuple[list[float], list[float]]:
    """Render per-candidate clear-window duration as an RGBA PNG: fully
    transparent where a candidate is never clear (or there is no candidate),
    colour and opacity scaling with duration otherwise. Returns the image's
    WGS84 bounds as ([lat_min, lon_min], [lat_max, lon_max]).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    from matplotlib import colormaps

    grid, origin_x, origin_y_top, n = _rasterize_candidates(
        result, duration_minutes, home_x, home_y, radius, spacing
    )
    valid = np.isfinite(grid)
    norm = np.clip(np.nan_to_num(grid, nan=0.0) / max(vmax_minutes, 1e-9), 0.0, 1.0)

    cmap = colormaps["YlOrRd"]
    rgba = cmap(norm)
    has_any = valid & (np.nan_to_num(grid, nan=0.0) > 0.0)
    alpha = np.where(has_any, np.maximum(norm, _HEATMAP_MIN_ALPHA), 0.0)
    alpha = np.where(valid, alpha, 0.0)
    rgba[:, :, 3] = alpha
    mpimg.imsave(path, rgba, format="png")

    xs = [origin_x, origin_x + n * spacing]
    ys = [origin_y_top - n * spacing, origin_y_top]
    corner_x = [xs[0], xs[1], xs[0], xs[1]]
    corner_y = [ys[0], ys[0], ys[1], ys[1]]
    lons, lats = _BNG_TO_WGS84.transform(corner_x, corner_y)
    return [float(min(lats)), float(min(lons))], [float(max(lats)), float(max(lons))]


def to_map(
    result: SearchResult,
    mask: np.ndarray,
    home_lat: float,
    home_lon: float,
    path: Path,
    order: np.ndarray | None = None,
    highlight_count: int = 5,
    walk_metres: np.ndarray | None = None,
    start_idx: np.ndarray | None = None,
    end_idx: np.ndarray | None = None,
    duration_minutes: np.ndarray | None = None,
    home_x: float | None = None,
    home_y: float | None = None,
    radius: float | None = None,
    spacing: float | None = None,
    window_minutes: float = 60.0,
) -> None:
    """A folium map with a home marker, the passing points, and (if the
    duration/grid arguments are given) a clear-window-duration heatmap.

    `order` (indices into the full `result` array, nearest first -- the same
    ranking used for the printed table) has its first `highlight_count`
    entries drawn as numbered pins instead of plain dots. `walk_metres`, if
    given, is a full-length array aligned to `result` (NaN where not
    computed) used for the highlighted pins' labels; otherwise straight-line
    distance is shown. `start_idx`/`end_idx` (from `search.clear_window_minutes`),
    if given, add the clear-window clock time to the highlighted pins' labels.

    `duration_minutes` (full-length, aligned to `result`, from
    `search.clear_window_minutes`), together with `home_x`/`home_y`/`radius`/
    `spacing` (the same values passed to `search.score_candidates`), adds a
    heatmap layer: transparent where a candidate is never clear, colour and
    opacity scaling with its longest clear window up to `window_minutes`
    (fully opaque, deep red = clear for the whole tracked window).
    """
    try:
        import folium
    except ImportError as exc:
        raise RuntimeError(
            "folium is not installed; install sunspot[map] to export map.html"
        ) from exc

    highlighted = set(order[:highlight_count].tolist()) if order is not None else set()
    idx_full = np.nonzero(mask)[0]
    lon, lat = _BNG_TO_WGS84.transform(result.x[idx_full], result.y[idx_full])
    frac = result.fraction_clear[idx_full]

    # folium's default OSM tile layer gets blocked by OSM's tile usage policy
    # (osm.wiki/Blocked) for this kind of automated use, and CartoDB's named
    # tiles now require an API key (see folium's own UserWarning). Esri's
    # basemaps are free and keyless for this kind of light, non-commercial use.
    m = folium.Map(
        location=[home_lat, home_lon],
        zoom_start=15,
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Street_Map/MapServer/tile/{z}/{y}/{x}"
        ),
        attr=(
            "Esri, HERE, Garmin, FAO, NOAA, USGS, "
            "&copy; OpenStreetMap contributors, GIS User Community"
        ),
    )

    have_heatmap_inputs = (
        duration_minutes is not None
        and home_x is not None
        and home_y is not None
        and radius is not None
        and spacing is not None
    )
    if have_heatmap_inputs:
        assert duration_minutes is not None
        assert home_x is not None and home_y is not None
        assert radius is not None and spacing is not None
        png_path = path.with_name(path.stem + "_heatmap.png")
        sw, ne = _duration_heatmap_png(
            result, duration_minutes, home_x, home_y, radius, spacing, window_minutes, png_path
        )
        folium.raster_layers.ImageOverlay(
            image=str(png_path),
            bounds=[sw, ne],
            opacity=1.0,
            name="Sun-visible duration",
        ).add_to(m)

        import branca.colormap as bcm

        legend = bcm.LinearColormap(
            colors=["#ffffb2", "#fd8d3c", "#bd0026"],
            vmin=0,
            vmax=window_minutes,
            caption="Longest unbroken clear window (minutes)",
        )
        legend.add_to(m)

    spots = folium.FeatureGroup(name="Spots", show=True)
    folium.Marker(
        [home_lat, home_lon], tooltip="Home", icon=folium.Icon(color="blue")
    ).add_to(spots)
    # The heatmap already shows duration for every candidate far more densely
    # and legibly than one DOM marker each could (thousands of them, for a
    # typical search) -- so only fall back to plotting every passing point as
    # a dot when there is no heatmap to show that instead.
    if not have_heatmap_inputs:
        for i, full_idx in enumerate(idx_full):
            if full_idx in highlighted:
                continue
            folium.CircleMarker(
                [float(lat[i]), float(lon[i])],
                radius=5,
                color="orange",
                fill=True,
                fill_opacity=0.8,
                tooltip=f"{frac[i] * 100:.0f}% clear",
            ).add_to(spots)

    if order is not None:
        for rank, full_idx in enumerate(order[:highlight_count], start=1):
            pt_lon, pt_lat = _BNG_TO_WGS84.transform([result.x[full_idx]], [result.y[full_idx]])
            if walk_metres is not None and np.isfinite(walk_metres[full_idx]):
                dist_label = f"{walk_metres[full_idx]:.0f} m walk"
            else:
                dist_label = f"{result.distance_m[full_idx]:.0f} m"
            window_label = ""
            if start_idx is not None and end_idx is not None and start_idx[full_idx] >= 0:
                s, e = start_idx[full_idx], end_idx[full_idx]
                window_label = (
                    f", sun {result.times[s].strftime('%H:%M')}"
                    f"-{result.times[e].strftime('%H:%M')}"
                )
            folium.Marker(
                [float(pt_lat[0]), float(pt_lon[0])],
                icon=folium.DivIcon(
                    html=(
                        '<div style="background:#c0392b;color:white;'
                        "border-radius:50%;width:24px;height:24px;"
                        "display:flex;align-items:center;justify-content:center;"
                        'font-weight:bold;font-size:13px;border:2px solid white;'
                        'box-shadow:0 0 3px rgba(0,0,0,0.5);">'
                        f"{rank}</div>"
                    ),
                    icon_size=(24, 24),
                    icon_anchor=(12, 12),
                ),
                tooltip=(
                    f"#{rank} -- {dist_label}{window_label}, "
                    f"{result.fraction_clear[full_idx] * 100:.0f}% clear overall"
                ),
            ).add_to(spots)

    spots.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(path))
