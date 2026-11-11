"""ciao-sun CLI: the `tiles` placeholder (until `fetch` replaces it) and `profile-only`."""

from __future__ import annotations

import csv
import warnings
from pathlib import Path

import numpy as np
import typer
from pyproj import Transformer

from ciao_sun.config import CiaoSunConfig
from ciao_sun.horizon import horizon_angle, meridian_convergence, ray_samples
from ciao_sun.raster import TilesNotFoundError, find_tiles, load_mosaic_cached
from ciao_sun.raster import sample as raster_sample
from ciao_sun.solar import sunrise_hour_track
from ciao_sun.tiles import tile_codes_for_aoi

app = typer.Typer(add_completion=False, no_args_is_help=True)

_WGS84_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)

EYE_HEIGHT_DEFAULT = 1.6


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
    cfg = CiaoSunConfig.load(config, home_lat=lat, home_lon=lon, date=date, max_ray=max_ray)
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
