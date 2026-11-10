"""sunspot CLI: tiles, find, compare, and the --profile-only debug command."""

from __future__ import annotations

import csv
import warnings
from pathlib import Path

import numpy as np
import typer
from pyproj import Transformer

from sunspot.config import SunspotConfig
from sunspot.export import to_geojson, to_horizon_geotiff, to_map
from sunspot.horizon import horizon_angle, meridian_convergence, ray_samples
from sunspot.raster import (
    RasterGrid,
    TilesNotFoundError,
    assert_aligned,
    find_tiles,
    load_mosaic_cached,
)
from sunspot.raster import (
    sample as raster_sample,
)
from sunspot.search import (
    SearchResult,
    clear_window_minutes,
    passing_mask,
    passing_mask_duration,
    rank_nearest,
    score_candidates,
)
from sunspot.solar import sunrise_hour_track
from sunspot.tiles import tile_codes_for_aoi

app = typer.Typer(add_completion=False, no_args_is_help=True)

_WGS84_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
_BNG_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)

EYE_HEIGHT_DEFAULT = 1.6

# A brisk-but-not-rushed walking pace, for the "leave home by" estimate. This is
# a rough assumption, not measured -- real walking speed varies a lot by person
# and terrain.
WALK_SPEED_M_PER_MIN = 80.0


def _parse_centre(centre: str) -> tuple[float, float]:
    parts = centre.split(",")
    if len(parts) != 2:
        raise typer.BadParameter("Expected LAT,LON e.g. 51.4720,-2.6040")
    try:
        return float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise typer.BadParameter("Expected LAT,LON e.g. 51.4720,-2.6040") from exc


@app.command()
def tiles(
    centre: str = typer.Option(..., "--centre", help="Home LAT,LON in WGS84 degrees"),
    radius: float = typer.Option(1500.0, "--radius", help="Search radius in metres"),
) -> None:
    """Print the OS 5 km tile codes to download for this area of interest."""
    lat, lon = _parse_centre(centre)
    codes = tile_codes_for_aoi(lat, lon, radius)
    typer.echo(", ".join(codes))


def _load_config(
    config: Path | None,
    centre: str | None,
    date: str | None,
    radius: float | None,
    min_clear_minutes: float | None = None,
) -> SunspotConfig:
    overrides: dict[str, object] = {}
    if centre is not None:
        lat, lon = _parse_centre(centre)
        overrides["home_lat"] = lat
        overrides["home_lon"] = lon
    if date is not None:
        overrides["date"] = date
    if radius is not None:
        overrides["radius"] = radius
    if min_clear_minutes is not None:
        overrides["min_clear_minutes"] = min_clear_minutes
    return SunspotConfig.load(config, **overrides)


def _load_rasters(cfg: SunspotConfig) -> tuple[RasterGrid, RasterGrid, float, float]:
    hx, hy = _WGS84_TO_BNG.transform(cfg.home_lon, cfg.home_lat)
    pad = cfg.radius + cfg.max_ray
    bounds = (hx - pad, hy - pad, hx + pad, hy + pad)
    dsm_paths = find_tiles(cfg.dsm_dir)
    dtm_paths = find_tiles(cfg.dtm_dir)
    dsm = load_mosaic_cached(dsm_paths, bounds, cfg.cache_dir, "dsm")
    dtm = load_mosaic_cached(dtm_paths, bounds, cfg.cache_dir, "dtm")
    assert_aligned(dsm, dtm)
    return dsm, dtm, hx, hy


def _print_table(
    result: SearchResult,
    order: np.ndarray,
    limit: int = 20,
    walk_metres: np.ndarray | None = None,
    start_idx: np.ndarray | None = None,
    end_idx: np.ndarray | None = None,
    duration_minutes: np.ndarray | None = None,
) -> None:
    top = order[:limit]
    lon, lat = _BNG_TO_WGS84.transform(result.x[top], result.y[top])
    show_window = start_idx is not None and end_idx is not None and duration_minutes is not None

    header = f"{'dist (m)':>10}  "
    if walk_metres is not None:
        header += f"{'walk':>16}  "
    if show_window:
        header += f"{'sun visible':>17}  {'mins':>5}  "
    header += f"{'lat':>10}  {'lon':>11}  {'clear':>6}"
    typer.echo(header)

    for i, idx in enumerate(top):
        row = f"{result.distance_m[idx]:10.0f}  "
        if walk_metres is not None:
            w = walk_metres[idx]
            if np.isfinite(w):
                row += f"{w:5.0f} m (~{w / WALK_SPEED_M_PER_MIN:.0f} min)  "
            else:
                row += f"{'--':>16}  "
        if show_window:
            assert start_idx is not None and end_idx is not None and duration_minutes is not None
            s, e = start_idx[idx], end_idx[idx]
            if s < 0:
                row += f"{'never clear':>17}  {'--':>5}  "
            else:
                t0 = result.times[s].strftime("%H:%M")
                t1 = result.times[e].strftime("%H:%M")
                row += f"{t0:>8}-{t1:<8}  {duration_minutes[idx]:5.0f}  "
        row += (
            f"{lat[i]:10.6f}  {lon[i]:11.6f}  "
            f"{result.fraction_clear[idx] * 100:5.0f}%"
        )
        typer.echo(row)


@app.command()
def find(
    config: Path | None = typer.Option(None, "--config"),
    centre: str | None = typer.Option(None, "--centre"),
    date: str | None = typer.Option(None, "--date"),
    radius: float | None = typer.Option(None, "--radius"),
    min_clear_minutes: float | None = typer.Option(
        None,
        "--min-clear-minutes",
        help="Require an unbroken clear window of at least this many minutes",
    ),
    walk: bool = typer.Option(False, "--walk", help="Rank by walking distance via osmnx"),
    output_dir: Path = typer.Option(Path("."), "--output-dir"),
    map_: bool = typer.Option(False, "--map", help="Also write map.html"),
) -> None:
    """Find the nearest sunrise viewpoints to home with an unbroken clear window.

    A candidate passes if it has at least one unbroken run of clear time steps
    spanning >= min_clear_minutes (default from config, 5 minutes) -- not merely
    an overall fraction of the hour clear, which says nothing about whether the
    clear steps are contiguous or scattered.
    """
    try:
        cfg = _load_config(config, centre, date, radius, min_clear_minutes)
        dsm, dtm, hx, hy = _load_rasters(cfg)
    except (TilesNotFoundError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    track = sunrise_hour_track(
        cfg.home_lat, cfg.home_lon, cfg.date, cfg.tz, cfg.step_minutes, cfg.window_minutes
    )
    typer.echo(f"Sunrise {track.sunrise:%Y-%m-%d %H:%M %Z}")

    try:
        result = score_candidates(
            dsm,
            dtm,
            hx,
            hy,
            cfg.radius,
            cfg.spacing,
            cfg.eye_height,
            track,
            cfg.max_ray,
            curvature=cfg.curvature,
            chunk_size=cfg.chunk_size,
        )
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    duration_minutes, start_idx, end_idx = clear_window_minutes(result)
    mask = passing_mask_duration(duration_minutes, cfg.min_clear_minutes)
    order = rank_nearest(result, mask)
    typer.echo(
        f"{mask.sum()} of {len(result.x)} candidates have an unbroken clear window "
        f">= {cfg.min_clear_minutes:.0f} minutes"
    )

    walk_metres = None  # aligned to result.x[mask], for to_geojson
    walk_metres_full = None  # aligned to the full result array, for the table
    if walk and mask.any():
        from sunspot.routing import walk_distances

        idx_full = np.nonzero(mask)[0]
        lon, lat = _BNG_TO_WGS84.transform(result.x[idx_full], result.y[idx_full])
        walk_metres = walk_distances(cfg.home_lat, cfg.home_lon, lat, lon, cfg.radius)
        if walk_metres is not None:
            order = idx_full[np.argsort(np.nan_to_num(walk_metres, nan=np.inf))]
            walk_metres_full = np.full(len(result.x), np.nan, dtype="float64")
            walk_metres_full[idx_full] = walk_metres

    output_dir.mkdir(parents=True, exist_ok=True)
    to_geojson(
        result,
        mask,
        output_dir / "clear_spots.geojson",
        walk_metres,
        start_idx=start_idx,
        end_idx=end_idx,
        duration_minutes=duration_minutes,
    )
    to_horizon_geotiff(result, hx, hy, cfg.radius, cfg.spacing, output_dir / "horizon_angle.tif")
    if map_:
        to_map(
            result,
            mask,
            cfg.home_lat,
            cfg.home_lon,
            output_dir / "map.html",
            order=order,
            walk_metres=walk_metres_full,
            start_idx=start_idx,
            end_idx=end_idx,
            duration_minutes=duration_minutes,
            home_x=hx,
            home_y=hy,
            radius=cfg.radius,
            spacing=cfg.spacing,
            window_minutes=cfg.window_minutes,
        )

    if mask.any():
        _print_table(
            result,
            order,
            walk_metres=walk_metres_full,
            start_idx=start_idx,
            end_idx=end_idx,
            duration_minutes=duration_minutes,
        )
    else:
        typer.echo(
            "Nothing passes. Widen --radius, lower --min-clear-minutes, or try a "
            "finer --step-minutes in the config (coarse steps under-report short windows)."
        )


@app.command()
def compare(
    centre: str = typer.Option(..., "--centre"),
    dates: str = typer.Option(..., "--dates", help="Comma-separated YYYY-MM-DD dates"),
    radius: float = typer.Option(1500.0, "--radius"),
    output_dir: Path = typer.Option(Path("."), "--output-dir"),
) -> None:
    """Intersect the passing sets across several dates, for year-round spots."""
    date_list = [d.strip() for d in dates.split(",") if d.strip()]
    if len(date_list) < 2:
        raise typer.BadParameter("Give at least two comma-separated dates")

    lat, lon = _parse_centre(centre)
    dsm = dtm = None
    hx = hy = 0.0
    combined_mask: np.ndarray | None = None
    result = None

    for date in date_list:
        cfg = SunspotConfig.load(None, home_lat=lat, home_lon=lon, date=date, radius=radius)
        try:
            dsm, dtm, hx, hy = _load_rasters(cfg)
        except (TilesNotFoundError, ValueError) as exc:
            typer.secho(str(exc), fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        track = sunrise_hour_track(
            cfg.home_lat, cfg.home_lon, cfg.date, cfg.tz, cfg.step_minutes, cfg.window_minutes
        )
        result = score_candidates(
            dsm, dtm, hx, hy, cfg.radius, cfg.spacing, cfg.eye_height, track, cfg.max_ray,
            curvature=cfg.curvature, chunk_size=cfg.chunk_size,
        )
        mask = passing_mask(result, cfg.pass_fraction)
        combined_mask = mask if combined_mask is None else (combined_mask & mask)
        typer.echo(f"{date}: {mask.sum()} clear positions")

    assert result is not None and combined_mask is not None
    order = rank_nearest(result, combined_mask)
    typer.echo(f"{combined_mask.sum()} positions clear on all {len(date_list)} dates")
    output_dir.mkdir(parents=True, exist_ok=True)
    to_geojson(result, combined_mask, output_dir / "clear_spots.geojson")
    if combined_mask.any():
        _print_table(result, order)


@app.command(name="profile-only")
def profile_only(
    point: str = typer.Argument(..., help="LAT,LON in WGS84 degrees"),
    config: Path | None = typer.Option(None, "--config"),
    date: str = typer.Option("2026-12-21", "--date"),
    max_ray: float = typer.Option(3000.0, "--max-ray"),
    eye_height: float = typer.Option(EYE_HEIGHT_DEFAULT, "--eye-height"),
    curvature: bool = typer.Option(True, "--curvature/--no-curvature"),
    output_dir: Path = typer.Option(Path("."), "--output-dir"),
) -> None:
    """Dump the full Horizon profile (angle vs true azimuth) for one point, plus a plot.

    Azimuths are clockwise from true north, as for the sun track overlaid on the
    plot. Manual sanity check: compare the plot against heywhatsthat.com for the
    same coordinate, which computes the same thing (also from true north) from
    independent terrain data.
    """
    lat, lon = _parse_centre(point)
    cfg = SunspotConfig.load(config, home_lat=lat, home_lon=lon, date=date, max_ray=max_ray)
    px, py = _WGS84_TO_BNG.transform(lon, lat)
    pad = max_ray
    bounds = (px - pad, py - pad, px + pad, py + pad)
    try:
        dsm_paths = find_tiles(cfg.dsm_dir)
        dtm_paths = find_tiles(cfg.dtm_dir)
        dsm = load_mosaic_cached(dsm_paths, bounds, cfg.cache_dir, "dsm")
        dtm = load_mosaic_cached(dtm_paths, bounds, cfg.cache_dir, "dtm")
    except TilesNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    ground = raster_sample(dtm, np.array([px]), np.array([py]))[0]
    if not np.isfinite(ground):
        typer.secho(f"No DTM coverage at {lat},{lon}.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    pz = float(ground) + eye_height

    ray_d = ray_samples(max_ray)
    convergence = meridian_convergence(px, py)
    azimuths = np.arange(0.0, 360.0, 1.0)  # true azimuths
    px_arr, py_arr, pz_arr = np.array([px]), np.array([py]), np.array([pz])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN (slice|axis) encountered")
        angles = np.array(
            [
                horizon_angle(
                    dsm, px_arr, py_arr, pz_arr, az, ray_d,
                    convergence_deg=convergence, curvature=curvature,
                )[0]
                for az in azimuths
            ]
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "horizon_profile.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["true_azimuth_deg", "horizon_angle_deg"])
        for az, ang in zip(azimuths, angles, strict=True):
            w.writerow([az, ang])
    typer.echo(f"Wrote {csv_path} (meridian convergence here: {convergence:+.4f} deg)")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    track = sunrise_hour_track(lat, lon, date, cfg.tz, cfg.step_minutes, cfg.window_minutes)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(azimuths, angles, label="Horizon (obstruction) angle", color="tab:gray")
    ax.plot(
        track.azimuth,
        track.apparent_elevation,
        label="Sun track (hour after sunrise)",
        color="tab:orange",
    )
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel("True azimuth (deg, from true north)")
    ax.set_ylabel("Angle (deg)")
    ax.set_title(f"Horizon profile at {lat:.5f},{lon:.5f} -- {date}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    png_path = output_dir / "horizon_profile.png"
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    typer.echo(f"Wrote {png_path}")


if __name__ == "__main__":
    app()
