# Handoff: `ciao-sun` — nearest unobstructed sunrise viewpoint finder

You are implementing a small, well-tested Python tool. A working prototype exists at
`prototype/find_sunrise_spots.py`. Treat it as a reference for the maths, **not** as
code to keep — it is a single-file sketch with no tests, no CLI, and no caching.

Read this whole document before writing code. Ask before deviating from the
acceptance criteria in §8.

---

## 1. Problem

Given a home location in England, find the nearest places you can stand and see the
sun during the first hour after sunrise on a given date, with nothing (terrain,
buildings, trees) blocking the line of sight.

The user is in Bristol (BS6). The tool should be general across England, since that
is the extent of the input data.

## 2. Approach

For each candidate standing position, and for each time step across the hour after
sunrise:

1. Compute the sun's azimuth and apparent elevation at that instant.
2. Cast a ray from the observer along that azimuth across a Digital Surface Model.
3. Take the maximum obstruction angle along the ray.
4. The position passes that time step if the obstruction angle is below the sun's
   elevation.

A position "works" if it passes at least `pass_fraction` of the time steps. Report
the passing positions nearest to home.

### Core maths

Observer eye elevation:

```
z_obs = DTM(x, y) + eye_height      # DTM, not DSM — you stand on bare earth
```

Obstruction angle at distance `d` along azimuth `theta` (degrees clockwise from
grid north):

```
x_s = x + d * sin(radians(theta))
y_s = y + d * cos(radians(theta))
drop = d**2 / (2 * R_eff)           # earth curvature + standard refraction
angle = degrees(atan2(DSM(x_s, y_s) - z_obs - drop, d))
```

with `R_eff = 6371000 * 1.13`. Horizon angle for that azimuth is `max(angle)` over
all sampled `d`.

Ray sampling should be variable-density — 1 m steps out to 200 m, 5 m to 1 km, then
20 m to `max_ray`. Uniform 1 m sampling to 8 km is ~14x the work for no accuracy gain.

## 3. Data

**Source:** Environment Agency, via <https://environment.data.gov.uk/> (search
"LIDAR", then "Download the Survey Data" and draw an area of interest).

Two products are required:

| Product | Role |
|---|---|
| LIDAR Composite DSM — 1m | Obstacles: last-return surface including buildings and vegetation |
| LIDAR Composite DTM — 1m | Bare earth, for observer standing height |

Both arrive as GeoTIFF in 5 km tiles on the OS National Grid, EPSG:27700, values in
metres above Ordnance Survey Newlyn datum, ±15 cm vertical RMSE. Licence is OGL;
carry the attribution string `© Environment Agency copyright and/or database right
2022. All rights reserved.` in the README and in any exported map.

**Downloading is a manual user step.** Do not attempt to script the portal — it is
an interactive ESRI widget. Instead:

- Document the download steps in the README.
- Provide `ciao-sun tiles --centre LAT,LON --radius M` which prints the list of OS
  5 km tile codes the user needs (e.g. `ST5575, ST5580, ST6075, ST6080`), so they
  know what to select. Derive tile codes arithmetically from BNG eastings/northings;
  do not hardcode a lookup table.
- Fail with a clear, actionable message if tiles are missing for the requested AOI.

## 4. Deliverables

```
ciao-sun/
├── pyproject.toml            # uv or hatch; Python >=3.11
├── README.md
├── HANDOFF.md                # this file
├── src/ciao_sun/
│   ├── __init__.py
│   ├── cli.py                # typer
│   ├── config.py             # pydantic settings model, TOML-backed
│   ├── raster.py             # mosaic, clip, align, sample
│   ├── solar.py              # sunrise detection, sun track
│   ├── horizon.py            # ray casting, vectorised
│   ├── search.py             # candidate generation, scoring, ranking
│   ├── routing.py            # optional walking distance via osmnx
│   └── export.py             # GeoJSON, GeoTIFF, folium map
├── tests/
└── data/                     # gitignored
    ├── dsm/
    └── dtm/
```

### CLI

```
ciao-sun tiles   --centre 51.4720,-2.6040 --radius 1500
ciao-sun find    --config ciao-sun.toml
ciao-sun find    --centre 51.4720,-2.6040 --date 2026-12-21 --radius 1500
ciao-sun compare --centre ... --dates 2026-12-21,2027-03-20,2027-06-21
```

`compare` intersects the passing sets across dates and reports year-round spots.

### Outputs

- Ranked table to stdout: distance, lat/lon, fraction of the hour clear.
- `clear_spots.geojson` — all passing candidates, with `metres_from_home`,
  `walk_metres` (if routing enabled) and `fraction_clear` properties.
- `horizon_angle.tif` — per-candidate worst obstruction angle, EPSG:27700, for QGIS.
- `map.html` — folium map, home marker plus passing points, optional.

## 5. Implementation notes

**Raster handling.** Mosaic the tiles once, clip both DSM and DTM to a common
envelope (home ± `radius + max_ray`), assert identical transform and shape, and
cache the result to `data/cache/`. EA nodata is typically -9999 — mask anything
below -100 to NaN and use `np.nanmax`. Do not load full 5 km tiles into memory
per query.

**Solar position.** Use `pvlib.solarposition.get_solarposition`. Use
`apparent_elevation` (refracted) throughout, and define sunrise as the first minute
where apparent elevation exceeds -0.833°. Note this is the *flat-horizon* sunrise —
the actual local sunrise at an obstructed site is later. That is intentional and
should be stated in the README; the tool answers "where can I see the sun during the
hour after nominal sunrise", not "when does the sun appear here".

**Vectorisation.** Score candidates in chunks of a few thousand, with the inner loop
over time steps and the ray samples fully vectorised across the chunk. Expect
`(n_chunk, n_samples)` float32 arrays. Chunk size should be configurable and default
to something that stays under ~1 GB.

**Candidate positions.** Regular grid at `spacing` metres within `radius`, masked to
a circle, with positions dropped where DTM is NaN.

**Routing (feature-flagged, off by default).** With `--walk`, build a walking graph
via `osmnx.graph_from_point(network_type="walk")`, snap candidates to the nearest
node, and rank by `networkx.shortest_path_length` rather than Euclidean distance.
This also implicitly filters out private gardens, which straight-line ranking does
not. Degrade gracefully with a warning if osmnx is absent.

## 6. Correctness — this matters more than features

Neither you nor the user can eyeball a horizon angle. Everything must be verified
against synthetic ground truth or an independent source.

Required tests in `tests/`:

1. **Flat plane.** Synthetic DSM at constant elevation. Horizon angle at every
   azimuth must be `atan2(-eye_height - drop, d)` maximised, i.e. slightly negative
   and within 0.01° of the analytic value.
2. **Single wall.** A 10 m rise at exactly 100 m along azimuth 90°, flat elsewhere.
   Observer eye at 1.6 m. Expected angle `degrees(atan2(10 - 1.6 - drop, 100))`
   ≈ 4.80°. Assert within 0.02°. Assert azimuth 270° is unaffected.
3. **Curvature sign.** With curvature enabled, a distant obstacle's angle must be
   strictly less than with it disabled. Guards against a sign error.
4. **CRS round trip.** WGS84 → EPSG:27700 → WGS84 for a set of English coordinates,
   within 1e-7 degrees. Assert `always_xy=True` is used — lon/lat ordering is the
   single most likely bug here.
5. **Raster sampling.** Known-value array; assert `sample()` returns the right cell
   for points at cell centres, at cell edges, and outside the grid (NaN).
6. **Solar position.** Cross-check azimuth and elevation for Bristol on 2026-12-21
   and 2026-06-21 against published values (NOAA solar calculator or
   timeanddate.com) to within 0.2°. Hardcode the reference values in the test with
   a comment naming the source.
7. **Tile codes.** Known BNG coordinates → known OS 5 km tile codes, including cases
   either side of a 100 km grid square boundary.
8. **End to end.** A small synthetic DSM/DTM pair where the answer is obvious by
   construction (a flat plain with a single ridge to the southeast); assert the tool
   returns positions on the correct side of the ridge and none behind it.

Also add a `--profile-only LAT,LON` debug command that dumps the full horizon
profile (angle vs azimuth, 1° steps, 0–360) for one point as CSV plus a plot with
the sun track overlaid. This is the main manual sanity check — the user can compare
it against heywhatsthat.com for the same coordinate, which computes the same thing
from terrain data.

## 7. Gotchas already identified

- The 2022 composite merges surveys flown between June 2000 and April 2022. Buildings
  newer than the local survey date are missing. Surface the survey date per AOI if
  the metadata index catalogue makes that cheap; otherwise document the limitation.
- DSM is last-return, so deciduous trees appear solid at full summer height
  year-round. Conservative, which is the right direction, but note it.
- Tile boundaries can show seams where adjacent surveys differ in date/resolution.
- `max_ray` beyond ~3 km rarely changes results in lowland England: blocking a 7° sun
  from 3 km needs a 370 m obstacle. Default to 3000 m, allow override, and document
  why.
- Do not use DSM for the observer height. It will place the observer on rooftops and
  in tree canopies and return nonsense.

## 8. Acceptance criteria

- [ ] `uv run pytest` passes; all eight test groups above present and meaningful.
- [ ] `ciao-sun tiles` prints correct OS tile codes for the Bristol example.
- [ ] `ciao-sun find` runs end to end on real Bristol tiles in under 2 minutes for
      radius 1500 m, spacing 10 m, `max_ray` 3000 m, on a laptop CPU.
- [ ] Missing or misaligned tiles produce an actionable error, not a traceback.
- [ ] `--profile-only` output for the home coordinate is visually consistent with
      heywhatsthat.com for the same point.
- [ ] README documents the manual data download, the OGL attribution, the sunrise
      definition, and every limitation in §7.
- [ ] Type hints throughout; `ruff` and `mypy` clean.

## 9. Out of scope

Do not build: a web UI, a tile-download scraper, cloud/weather forecasting, a
database, or support for anywhere outside England. Do not add dependencies beyond
numpy, rasterio, pyproj, pvlib, pandas, typer, pydantic (plus osmnx/networkx/folium
behind feature flags) without asking.
