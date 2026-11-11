"""ciao-sun CLI: `fetch`, `build` and `profile-only`."""

from __future__ import annotations

import csv
import os
import warnings
from pathlib import Path

import numpy as np
import typer
from pyproj import Transformer

from ciao_sun import build as tile_build
from ciao_sun import fetch as fetch_inputs
from ciao_sun.build_checks import BuildCheckError
from ciao_sun.config import CiaoSunConfig
from ciao_sun.coverage import Coverage, CoverageError
from ciao_sun.horizon import horizon_angle, meridian_convergence, ray_samples
from ciao_sun.raster import TilesNotFoundError, find_tiles, load_mosaic_cached
from ciao_sun.raster import sample as raster_sample
from ciao_sun.solar import NOMINAL_RISE_SET_ELEVATION_DEG, sun_track
from ciao_sun.terrain50 import Terrain50Error

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
def fetch(
    coverage: Path = typer.Option(
        ...,
        "--coverage",
        help="GeoJSON file holding the coverage polygon (Polygon or MultiPolygon, WGS84 "
        "longitude/latitude): the area the build will produce Candidates for. EA LIDAR is "
        "fetched for this polygon plus --margin.",
    ),
    osm_date: str = typer.Option(
        ...,
        "--osm-date",
        help="Date of the Geofabrik extract as YYMMDD, e.g. 261110. Geofabrik keeps dated "
        "extracts for a limited time; pick one listed on download.geofabrik.de.",
    ),
    out: Path = typer.Option(
        Path("data/inputs"), "--out", help="Directory for the inputs and fetch.lock.json."
    ),
    margin: float = typer.Option(
        fetch_inputs.DEFAULT_MARGIN_M,
        "--margin",
        help="Metres of EA LIDAR to fetch beyond the coverage (the near-field ray length).",
    ),
    ea_year: str = typer.Option(
        fetch_inputs.DEFAULT_EA_YEAR, "--ea-year", help="EA LIDAR Composite year."
    ),
    osm_region: str = typer.Option(
        fetch_inputs.DEFAULT_OSM_REGION,
        "--osm-region",
        help="Geofabrik region path. It must contain the coverage plus the margin.",
    ),
    terrain50_version: str | None = typer.Option(
        None,
        "--terrain50-version",
        help="Pin an OS Terrain 50 release, e.g. 2026-07. Default: the cached release, "
        "else the one OS serves now. Fails if the pin is neither cached nor current.",
    ),
) -> None:
    """Download every build input for a coverage polygon and lock it by hash.

    \b
    Inputs:
      - Environment Agency LIDAR Composite, 1 m, in 5 km tiles: last-return DSM,
        DTM and first-return DSM, for the coverage plus 3 km (see --margin).
      - OS Terrain 50 for Great Britain (the far horizon).
      - A dated Geofabrik .osm.pbf extract (streets, paths, buildings).

    Requests are spaced about a second apart and back off on HTTP 403. An
    interrupted download resumes on the next run, and a run with everything
    already cached makes no requests.

    Every input is recorded in fetch.lock.json with its source, version, SHA-256
    and path. Once recorded, a cached or re-downloaded file whose SHA-256
    differs is refused. EA tiles the server does not publish (open sea) are
    recorded as absent.
    """
    try:
        polygon = Coverage.from_file(coverage)
        lock = fetch_inputs.fetch(
            polygon,
            out,
            osm_date=osm_date,
            client=fetch_inputs.UrllibClient(),
            ea_year=ea_year,
            osm_region=osm_region,
            terrain50_version=terrain50_version,
            margin_m=margin,
            report=typer.echo,
        )
    except (CoverageError, fetch_inputs.FetchError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    present = [entry for entry in lock.inputs if not entry.absent]
    absent = len(lock.inputs) - len(present)
    size_mb = sum(entry.bytes or 0 for entry in present) / 1e6
    typer.echo(
        f"{len(present)} inputs ({size_mb:.0f} MB) locked in {out / fetch_inputs.LOCKFILE_NAME}"
        + (f"; {absent} EA tiles not published" if absent else "")
    )


@app.command()
def build(
    coverage: Path = typer.Option(
        ...,
        "--coverage",
        help="GeoJSON file holding the coverage polygon (Polygon or MultiPolygon, WGS84 "
        "longitude/latitude). Candidates come only from inside it. It must lie within "
        "the coverage the inputs were fetched for.",
    ),
    inputs: Path = typer.Option(
        Path("data/inputs"),
        "--inputs",
        help="Directory `ciao-sun fetch` wrote: the inputs and fetch.lock.json.",
    ),
    out: Path = typer.Option(
        Path("data/builds"),
        "--out",
        help="Where builds go. This build is written to <out>/f1/<build id>/.",
    ),
    workers: int = typer.Option(
        max(1, (os.cpu_count() or 2) - 1), "--workers", min=1, help="Tiles to build at once."
    ),
) -> None:
    """Build the tiles and manifest for a coverage polygon from the fetched inputs.

    \b
    Writes one build directory:
      <out>/f1/<build id>/manifest.json
      <out>/f1/<build id>/tiles/<grid ref>.bin   one per 1 km square

    The build id is today's UTC date plus a letter, e.g. 20261110a.

    \b
    Two checks fail the build, and a failed build leaves no build directory:
      - tile Horizon profiles are compared with direct ray casting at a sample
        of Candidates;
      - no Candidate's horizon may be set by a water cell (the water guard).

    The manifest records the attribution, the licence, the LIDAR survey years,
    every input's version and SHA-256, the coverage, the tile index and the
    tolerances the checks passed at.
    """
    try:
        polygon = Coverage.from_file(coverage)
        build_dir = tile_build.build(polygon, inputs, out, workers=workers, report=typer.echo)
    except (
        CoverageError,
        fetch_inputs.FetchError,
        tile_build.BuildError,
        BuildCheckError,
        Terrain50Error,
    ) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    typer.echo(f"Wrote {build_dir}")


@app.command(name="profile-only")
def profile_only(
    point: str = typer.Argument(..., help="LAT,LON in WGS84 degrees"),
    config: Path | None = typer.Option(None, "--config"),
    date: str | None = typer.Option(None, "--date", help="Default: config, else 2026-12-21"),
    max_ray: float | None = typer.Option(
        None, "--max-ray", help="Metres. Default: config, else 3000"
    ),
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
    date, max_ray = cfg.date, cfg.max_ray
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

    track = sun_track(lat, lon, date, cfg.tz)
    up = track.elevation >= NOMINAL_RISE_SET_ELEVATION_DEG
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(azimuths, angles, label="Horizon (obstruction) angle", color="tab:gray")
    ax.plot(
        track.azimuth[up],
        track.apparent_elevation[up],
        label="Sun track (Nominal sunrise to Nominal sunset)",
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
