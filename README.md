# Ciao Sun

Find places you can stand and see the sun with nothing (terrain, buildings,
trees) blocking the line of sight, using Environment Agency LIDAR for England.

This Python package is the **offline build pipeline plus a scoring reference**
(see `docs/adr/0001-static-precompute-client-evaluation.md`); the phone app
evaluates the precomputed Horizon profiles itself. Terms follow `GLOSSARY.md`.

The package is mid-way to that shape. The earlier laptop tool's `find` and
`compare` commands, walking-distance routing and GeoJSON / map / GeoTIFF
exports have been removed. What the CLI exposes today is:

- `profile-only` -- dump the Horizon profile at one coordinate, for cross-checking
  against heywhatsthat by hand.
- `fetch` -- download every build input for a coverage polygon and lock it by
  hash.
- `build` -- turn the fetched inputs into one build directory of tiles and a
  manifest.

The build's output is one binary file per 1 km square, in tile format `f1`.
`docs/tile-format-f1.md` specifies it for any language; `ciao_sun.tile_codec`
is the Python writer and reader.

## How it works

For a standing position and a true azimuth, Ciao Sun casts a ray from the
observer's eye across a Digital Surface Model and takes the ray's maximum
obstruction angle: the horizon angle on that bearing. Doing this for every
azimuth gives the position's Horizon profile. The sun is in view at a given
moment when its apparent elevation is above the horizon angle on its azimuth.

`HANDOFF.md` is the original design brief for the laptop tool. It is kept for
the maths and gotchas; its CLI and outputs sections are historical.

## Solar model

The sun track is one local day at 1 min steps: true azimuth from NREL SPA and
the apparent elevation of the disc centre, which is the SPA geometric
elevation plus one refraction model that stays continuous below 0 degrees.
Nominal sunrise and Nominal sunset are when the geometric centre crosses
-0.833 degrees, the flat-horizon definition almanacs use; they are **not**
when the sun appears or disappears at an obstructed site. Solar noon is the
upper transit. `docs/solar-model.md` specifies all of it for the JS port,
which must agree within 0.01 degrees. `profile-only` overlays the day's track,
from Nominal sunrise to Nominal sunset, on its plot.

## Data

**Source:** Environment Agency, via <https://environment.data.gov.uk/>.

The DSM and DTM are both delivered as GeoTIFF in 5 km tiles on the OS
National Grid (EPSG:27700), values in metres above Ordnance Survey Newlyn
datum, +/-15 cm vertical RMSE:

| Product | Role |
|---|---|
| LIDAR Composite DSM -- 1 m | Obstacles: last-return surface including buildings and vegetation |
| LIDAR Composite DTM -- 1 m | Bare earth, for observer standing height |

### Fetching the build inputs

```
uv run ciao-sun fetch --coverage bristol.geojson --osm-date 261110
```

`--coverage` is a GeoJSON Polygon or MultiPolygon in WGS84 longitude/latitude.
`fetch` downloads, into `data/inputs/` (`--out`):

| Input | Where it lands |
|---|---|
| EA LIDAR Composite 1 m last-return DSM, DTM and first-return DSM, every 5 km tile within 3 km of the coverage | `ea/<product>/<year>/<tile>.zip` |
| OS Terrain 50 for Great Britain | `terrain50/<version>/terr50_gagg_gb.zip` |
| The Geofabrik `.osm.pbf` extract of that date | `osm/<region>-<yymmdd>.osm.pbf` |

It also writes `fetch.lock.json` there: every input's source, version, URL,
SHA-256, size, retrieval time and path relative to the lockfile, plus the
coverage and margin. `ciao_sun.fetch.read_lockfile` reads it back.

Requests are about a second apart and back off on HTTP 403. A dropped download
resumes on the next run, and a run with everything cached makes no requests.
No upstream publishes a SHA-256, so the first fetch records each hash and any
later cached or re-downloaded file that differs is refused. EA tiles the
server does not publish (404, e.g. open sea) are recorded as `absent`.

### Building

```
uv run ciao-sun build --coverage bristol.geojson
```

`build` reads `data/inputs/` (`--inputs`) through its lockfile and writes
`data/builds/f1/<build id>/` (`--out`): `tiles/<grid ref>.bin` for every 1 km
square the coverage touches, and `manifest.json`. The build id is the UTC date
plus a letter, e.g. `20261110a`. Tiles are built in parallel (`--workers`), and
the same inputs give byte-identical tiles.

Two checks fail a build, which then leaves no build directory: tile Horizon
profiles are compared with direct ray casting at a sample of Candidates, and no
Candidate's horizon may be set by a cell inside an OSM water area.
`ciao_sun.build_checks` gives the tolerances and `ciao_sun.manifest` the
manifest's schema.

`profile-only` does not read this cache yet: it still wants unzipped GeoTIFFs
under `data/dsm/` and `data/dtm/` (searched recursively).

`ciao-sun profile-only` fails with a clear message (not a traceback) if tiles
are missing.

### Licence and attribution

Environment Agency LIDAR is released under the Open Government Licence.
Anything published from this data must carry:

> © Environment Agency copyright and/or database right 2022. All rights
> reserved.

## Installation

Requires Python >=3.11 and [uv](https://docs.astral.sh/uv/).

```
uv sync
```

## CLI

```
ciao-sun fetch --coverage bristol.geojson --osm-date 261110
ciao-sun build --coverage bristol.geojson
ciao-sun profile-only 51.4720,-2.6040 --date 2026-12-21
```

`profile-only` dumps the full Horizon profile (obstruction angle vs true
azimuth, 1 degree steps, 0-360, clockwise from true north) for one point as
`horizon_profile.csv`, plus `horizon_profile.png` with the sun track overlaid.
This is the main manual sanity check: compare the plot against
[heywhatsthat.com](https://www.heywhatsthat.com/) for the same coordinate,
which computes the same thing (also from true north) from independent terrain
data. Flags: `--max-ray`, `--eye-height`, `--curvature/--no-curvature`,
`--output-dir`.

### Configuration

`profile-only --config ciao-sun.toml` reads these keys (unknown keys are
rejected):

| Key | Default | Meaning |
|---|---|---|
| `dsm_dir` | `data/dsm` | Where the DSM tiles are |
| `dtm_dir` | `data/dtm` | Where the DTM tiles are |
| `cache_dir` | `data/cache` | Mosaic cache |
| `date` | `2026-12-21` | Date of the overlaid sun track (`--date` overrides) |
| `max_ray` | `3000.0` | Furthest obstruction considered, metres (`--max-ray` overrides) |
| `tz` | `Europe/London` | Time zone of the overlaid sun track |

The point comes from the command's argument, not the file. `--eye-height` and
`--curvature/--no-curvature` are flags only.

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
- **England only.** LIDAR coverage and the OS National Grid tile-code scheme
  used by `ciao-sun fetch` don't extend elsewhere.

## Development

```
uv run pytest
uv run ruff check .
uv run mypy src
```

CI (`.github/workflows/ci.yml`) runs the same three on every push.
