# sunspot

Find the nearest places you can stand and see the sun during the first hour
after sunrise, with nothing (terrain, buildings, trees) blocking the line of
sight, using Environment Agency LIDAR for England.

## How it works

For each candidate standing position and each time step across the hour after
sunrise, sunspot computes the sun's azimuth and apparent elevation, casts a ray
from the observer's eye along that azimuth across a Digital Surface Model, and
compares the ray's maximum obstruction angle to the sun's elevation. That gives
every candidate a clear/blocked pattern across the hour.

`sunspot find` then looks for an **unbroken run of clear time steps** at least
`min_clear_minutes` long (default 5) -- not just an overall fraction of the
hour clear, which says nothing about whether the clear moments are contiguous
or scattered across the hour. A candidate that's clear for six separate
one-minute slivers is not useful for standing and watching a sunrise; one
clear for fifteen minutes straight is. The nearest passing positions are
reported, along with the actual clock time of their longest clear window.

(`sunspot compare`, which looks for spots clear across several dates at once,
still uses the older `pass_fraction` -- overall fraction of the hour clear --
rather than the contiguous-window logic. That's a known inconsistency, not a
design decision; `find` is where the window-based logic actually lives.)

See `HANDOFF.md` for the full original design brief, including the maths and
gotchas below (some details, like the passing criterion above, have moved on
since it was written).

## Sunrise definition

Sunrise is the first minute where the sun's *apparent* (refraction-corrected)
elevation exceeds -0.833 degrees at the home coordinate -- the standard
flat-horizon definition used by almanacs. **This is not the actual local
sunrise at an obstructed site**, which will be later wherever the horizon
angle is above zero. sunspot answers "where can I see the sun during the hour
after nominal sunrise", not "when does the sun first appear at this exact
spot".

## Data

**Source:** Environment Agency, via <https://environment.data.gov.uk/>.

Two products are required, both delivered as GeoTIFF in 5 km tiles on the OS
National Grid (EPSG:27700), values in metres above Ordnance Survey Newlyn
datum, +/-15 cm vertical RMSE:

| Product | Role |
|---|---|
| LIDAR Composite DSM -- 1 m | Obstacles: last-return surface including buildings and vegetation |
| LIDAR Composite DTM -- 1 m | Bare earth, for observer standing height |

### Downloading tiles (manual step)

The portal is an interactive ESRI widget and cannot be scripted. To get the
tiles you need:

1. Work out which 5 km tiles cover your area of interest:

   ```
   uv run sunspot tiles --centre 51.4720,-2.6040 --radius 1500
   ```

2. Go to <https://environment.data.gov.uk/>, search "LIDAR", open "Download
   the Survey Data", and draw an area of interest that covers those tiles (or
   larger -- the tool only uses what's in each tile's bounding box).
3. Download **LIDAR Composite DSM - 1m** for that area, and separately
   **LIDAR Composite DTM - 1m** for the same area.
4. Unzip both downloads into `data/dsm/` and `data/dtm/` respectively.
   sunspot searches those directories recursively for `.tif` files, so the
   per-tile subdirectories the portal creates (e.g.
   `data/dtm/lidar_composite_dtm-2022-1-ST57ne/ST57ne_DTM_1m.tif`) are fine as
   they are.

`sunspot find` will fail with a clear message (not a traceback) if tiles are
missing or don't cover the requested area.

### Licence and attribution

Environment Agency LIDAR is released under the Open Government Licence.
Any exported map or report using this data must carry:

> © Environment Agency copyright and/or database right 2022. All rights
> reserved.

`--map`'s basemap tiles are Esri's (see [Map output](#map-output-map) below)
and carry their own attribution, shown automatically in the map's corner.

## Installation

Requires Python >=3.11 and [uv](https://docs.astral.sh/uv/).

```
uv sync
```

`--walk` and `--map` need their own extras (see below):

```
uv sync --extra routing --extra map
# or: uv sync --all-extras
```

## CLI

```
sunspot tiles   --centre 51.4720,-2.6040 --radius 1500
sunspot find    --config sunspot.toml
sunspot find    --centre 51.4720,-2.6040 --date 2026-12-21 --radius 1500 --min-clear-minutes 10
sunspot find    --centre 51.4720,-2.6040 --date 2026-12-21 --walk --map
sunspot compare --centre 51.4720,-2.6040 --dates 2026-12-21,2027-03-20,2027-06-21
sunspot profile-only 51.4720,-2.6040 --date 2026-12-21
```

`compare` intersects the passing sets across dates and reports the
year-round spots. `profile-only` is a debug command that dumps the full
horizon profile (obstruction angle vs azimuth, 1 degree steps, 0-360) for one
point as `horizon_profile.csv`, plus `horizon_profile.png` with the sun track
overlaid. This is the main manual sanity check: compare the plot against
[heywhatsthat.com](https://www.heywhatsthat.com/) for the same coordinate,
which computes the same thing from independent terrain data.

### Configuration

Most parameters can be set via `--config sunspot.toml` (CLI flags, where they
exist, override the file). The ones most worth knowing about:

| Key | Default | Meaning |
|---|---|---|
| `min_clear_minutes` | `5.0` | `find`'s passing bar: minimum unbroken clear window, in minutes |
| `pass_fraction` | `0.5` | `compare`'s passing bar: minimum fraction of the hour clear (see the note above) |
| `radius` | `1500.0` | Search radius around home, metres |
| `spacing` | `10.0` | Candidate grid spacing, metres |
| `step_minutes` | `5.0` | Sun-track sampling interval. **Also the resolution of reported clear windows** -- if you care about a 5-10 minute window, a 5-minute step is too coarse to resolve it reliably; try `2.0` or `1.0` |
| `window_minutes` | `60.0` | How far past nominal sunrise to track the sun |
| `max_ray` | `3000.0` | Furthest obstruction considered, metres (see Limitations) |
| `eye_height` | `1.6` | Observer eye height above bare earth, metres |
| `curvature` | `true` | Earth curvature + standard refraction in the horizon calculation |

A minimal `sunspot.toml`:

```toml
home_lat = 51.4720
home_lon = -2.6040
date = "2026-09-20"
min_clear_minutes = 5.0
step_minutes = 2.0
```

### Outputs of `find` / `compare`

- Ranked table to stdout: distance, walking distance and estimated walking
  time (with `--walk`), the clock time of the longest clear window and its
  length in minutes, lat/lon, and overall fraction of the hour clear.
  (Walking time is a rough estimate -- distance divided by an assumed 80 m/min
  pace -- not a routed travel time.)
- `clear_spots.geojson` -- all passing candidates, with `metres_from_home`,
  `walk_metres` (with `--walk`), `fraction_clear`, and (for `find`)
  `sun_visible_from`, `sun_visible_until` and `clear_window_minutes`
  properties.
- `horizon_angle.tif` -- per-candidate worst obstruction angle, EPSG:27700,
  for QGIS.
- `map.html` -- see below (with `--map`).

### Map output (`--map`)

A self-contained Leaflet map (`map.html`, one file, nothing else to keep
track of):

- A **heatmap** over the whole search grid: transparent wherever a candidate
  never sees the sun at all, coloured (pale yellow through to deep red) and
  more opaque the longer its longest unbroken clear window is, up to
  `window_minutes` (fully opaque = clear for the entire tracked hour). This
  is the fast way to see *where* to look before reading distances.
- A blue home marker, and the top 5 candidates by walking distance (or
  straight-line distance without `--walk`) as numbered red pins with a
  popup giving the clear-window time and distance.
- A layer toggle (top right) to hide/show the "Spots" pins independently of
  the heatmap, and a colour-scale legend (bottom left).

The basemap tiles are Esri's free World Street Map service. (folium's own
default OpenStreetMap tiles get blocked by OSM's automated-use policy for
this kind of thing, and CartoDB's named tiles now require an API key -- Esri's
don't, for this level of use.)

### Walking distance (optional)

`--walk` ranks candidates by walking-network distance instead of straight
line, using `osmnx`/`networkx` (install with `uv sync --extra routing`). This
also implicitly filters out points in private gardens, which straight-line
ranking cannot do. If osmnx/networkx aren't installed, sunspot warns and falls
back to straight-line distance rather than failing. osmnx's own street-network
cache is redirected to `data/cache/osmnx/` (its default is a `cache/`
directory wherever you happen to run the command from).

## Limitations

- **Survey dates vary.** The 2022 composite merges surveys flown between June
  2000 and April 2022. Buildings newer than the local survey date are
  missing from the DSM and will not obstruct the sun in this tool even though
  they do in reality.
- **Trees are shown at full summer canopy year-round.** The DSM is
  last-return, so deciduous trees appear solid at whatever height they were
  when surveyed. This is conservative (the tool under-promises rather than
  over-promises clear views), which is the right direction to be wrong in,
  but it means winter views through bare branches may be better than
  reported.
- **Tile seams.** Adjacent tiles can show seams where surveys of different
  dates or resolutions meet.
- **`max_ray` default is 3000 m.** Beyond about 3 km, obstructions rarely
  change the result in lowland England: blocking a 7-degree sun from 3 km
  away needs a 370 m tall obstacle. Override via config if you have reason to
  (e.g. a mountain on the horizon), but it costs more compute.
- **DTM, not DSM, for observer height.** The observer always stands on bare
  earth. Using the DSM for standing height would place candidates on rooftops
  and in tree canopies.
- **Clear windows are resolved to `step_minutes`, not continuously.** A
  candidate's reported window spans its first-to-last *clear sample*
  timestamp, so it's a lower bound at the sampling resolution -- see
  `step_minutes` above.
- **England only.** LIDAR coverage and the OS National Grid tile-code scheme
  used by `sunspot tiles` don't extend elsewhere.

## Development

```
uv run pytest
uv run ruff check .
uv run mypy src
```
