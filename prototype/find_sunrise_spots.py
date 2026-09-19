"""
find_sunrise_spots.py

Find the nearest locations to a home point that have an unobstructed view of the
sun during the first hour after sunrise, using Environment Agency LIDAR.

Data:
  LIDAR Composite DSM - 1m  (obstacles: buildings + vegetation + terrain)
  LIDAR Composite DTM - 1m  (bare earth: used for observer standing height)
  https://environment.data.gov.uk/  ->  search "LIDAR" -> Download the Survey Data
  GeoTIFF, EPSG:27700, metres AOD.  (c) Environment Agency, OGL.

Deps:
  pip install rasterio pyproj pvlib pandas numpy
Optional (walking distance instead of straight line):
  pip install osmnx networkx
"""

import glob

import numpy as np
import pandas as pd
import pvlib
import rasterio
from pyproj import Transformer
from rasterio.merge import merge

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
DSM_TILES = sorted(glob.glob("data/dsm/*.tif"))
DTM_TILES = sorted(glob.glob("data/dtm/*.tif"))

HOME_LAT, HOME_LON = 51.4720, -2.6040      # replace with your own
DATE = "2026-12-21"                        # worst case; try equinox too
TZ = "Europe/London"

SEARCH_RADIUS = 1500      # m around home to consider
CANDIDATE_SPACING = 10    # m between candidate positions
EYE_HEIGHT = 1.6          # m above bare earth
MAX_RAY = 8000            # m: furthest obstacle considered
PASS_FRACTION = 0.5       # 1.0 = clear for the whole hour; 0.5 = half of it
NODATA_BELOW = -100.0     # EA nodata is typically -9999

R_EFF = 6371000.0 * 1.13  # earth radius with standard refraction

# ----------------------------------------------------------------------------
# Raster helpers
# ----------------------------------------------------------------------------


def load_mosaic(paths):
    if not paths:
        raise FileNotFoundError("No tiles found - check the glob paths.")
    srcs = [rasterio.open(p) for p in paths]
    arr, transform = merge(srcs)
    for s in srcs:
        s.close()
    band = arr[0].astype("float32")
    band[band < NODATA_BELOW] = np.nan
    return band, transform


def sample(band, transform, x, y):
    """Nearest-neighbour sample of a raster at projected coords. NaN off-grid."""
    col = np.rint((x - transform.c) / transform.a).astype(np.int64)
    row = np.rint((y - transform.f) / transform.e).astype(np.int64)
    ok = (
        (row >= 0) & (row < band.shape[0]) & (col >= 0) & (col < band.shape[1])
    )
    out = np.full(x.shape, np.nan, dtype="float32")
    out[ok] = band[row[ok], col[ok]]
    return out


# ----------------------------------------------------------------------------
# Sun geometry
# ----------------------------------------------------------------------------


def sunrise_hour_track(lat, lon, date, tz=TZ, step="5min", minutes=60):
    """Return (azimuth, apparent_elevation) arrays for the hour after sunrise."""
    day = pd.date_range(f"{date} 00:00", f"{date} 23:59", freq="1min", tz=tz)
    sp = pvlib.solarposition.get_solarposition(day, lat, lon)
    above = sp.index[sp["apparent_elevation"] > -0.833]
    if len(above) == 0:
        raise ValueError("Sun never rises on that date at that latitude.")
    sunrise = above[0]

    window = pd.date_range(
        sunrise, sunrise + pd.Timedelta(minutes=minutes), freq=step, tz=tz
    )
    sp = pvlib.solarposition.get_solarposition(window, lat, lon)
    print(f"Sunrise {sunrise:%H:%M %Z}; "
          f"azimuth {sp['azimuth'].iloc[0]:.1f} -> {sp['azimuth'].iloc[-1]:.1f} deg, "
          f"elevation up to {sp['apparent_elevation'].iloc[-1]:.1f} deg")
    return sp["azimuth"].to_numpy(), sp["apparent_elevation"].to_numpy()


# ----------------------------------------------------------------------------
# Horizon
# ----------------------------------------------------------------------------

# Variable sampling: dense near the observer where parallax matters most.
RAY_D = np.concatenate([
    np.arange(2.0, 200.0, 1.0),
    np.arange(200.0, 1000.0, 5.0),
    np.arange(1000.0, MAX_RAY, 20.0),
])
CURVE_DROP = RAY_D ** 2 / (2.0 * R_EFF)


def horizon_angle(dsm, transform, px, py, pz, azimuth_deg):
    """Max obstruction angle (deg) along one azimuth, for many observer points."""
    th = np.radians(azimuth_deg)
    xs = px[:, None] + RAY_D[None, :] * np.sin(th)
    ys = py[:, None] + RAY_D[None, :] * np.cos(th)
    zs = sample(dsm, transform, xs, ys)
    rise = zs - pz[:, None] - CURVE_DROP[None, :]
    ang = np.degrees(np.arctan2(rise, RAY_D[None, :]))
    return np.nanmax(ang, axis=1)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main():
    dsm, tf = load_mosaic(DSM_TILES)
    dtm, tf_dtm = load_mosaic(DTM_TILES)
    if tf != tf_dtm or dsm.shape != dtm.shape:
        raise ValueError("DSM and DTM mosaics are not aligned - clip to a "
                         "common AOI first (rasterio.mask or gdalwarp -te).")

    to_bng = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    hx, hy = to_bng.transform(HOME_LON, HOME_LAT)
    print(f"Home: {hx:.0f} E, {hy:.0f} N")

    az_track, el_track = sunrise_hour_track(HOME_LAT, HOME_LON, DATE)
    need_pass = int(np.ceil(PASS_FRACTION * len(az_track)))

    # Candidate grid, circular mask
    offs = np.arange(-SEARCH_RADIUS, SEARCH_RADIUS + 1, CANDIDATE_SPACING)
    gx, gy = np.meshgrid(hx + offs, hy + offs)
    gx, gy = gx.ravel(), gy.ravel()
    dist = np.hypot(gx - hx, gy - hy)
    keep = dist <= SEARCH_RADIUS
    gx, gy, dist = gx[keep], gy[keep], dist[keep]

    ground = sample(dtm, tf, gx, gy)
    valid = np.isfinite(ground)
    gx, gy, dist, ground = gx[valid], gy[valid], dist[valid], ground[valid]
    gz = ground + EYE_HEIGHT
    print(f"{len(gx):,} candidate positions")

    n_clear = np.zeros(len(gx), dtype=np.int16)
    CHUNK = 4000
    for start in range(0, len(gx), CHUNK):
        sl = slice(start, start + CHUNK)
        px, py, pz = gx[sl], gy[sl], gz[sl]
        tally = np.zeros(len(px), dtype=np.int16)
        for az, el in zip(az_track, el_track):
            tally += (horizon_angle(dsm, tf, px, py, pz, az) < el)
        n_clear[sl] = tally
        print(f"  {min(start + CHUNK, len(gx)):,}/{len(gx):,}", end="\r")
    print()

    passing = n_clear >= need_pass
    print(f"{passing.sum():,} positions clear for >= {need_pass}/{len(az_track)} steps")
    if not passing.any():
        print("Nothing passes. Widen SEARCH_RADIUS or lower PASS_FRACTION.")
        return

    order = np.argsort(dist[passing])[:20]
    px, py, pd_ = gx[passing][order], gy[passing][order], dist[passing][order]

    to_wgs = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    lon, lat = to_wgs.transform(px, py)

    print("\nNearest clear spots (straight-line distance):")
    for i in range(len(px)):
        print(f"  {pd_[i]:6.0f} m   {lat[i]:.6f}, {lon[i]:.6f}   "
              f"https://www.google.com/maps?q={lat[i]:.6f},{lon[i]:.6f}")

    # Full result as a GeoJSON of passing points, for QGIS / Folium
    import json
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(a), float(b)]},
                "properties": {"metres_from_home": float(c)},
            }
            for a, b, c in zip(*to_wgs.transform(gx[passing], gy[passing]),
                               dist[passing])
        ],
    }
    with open("clear_sunrise_spots.geojson", "w") as f:
        json.dump(fc, f)
    print("\nWrote clear_sunrise_spots.geojson")


if __name__ == "__main__":
    main()
