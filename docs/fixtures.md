# Golden fixtures

A golden fixture is one Query, the reference scorer's Answer to it over one
build, and what a second implementation needs to check itself against that
Answer. The JS scorer is canonical (ADR 0001); fixtures are what stop it and
the Python reference drifting apart. Terms follow `GLOSSARY.md`; the Query and
Answer shapes are `ciao_sun.reference.contract`.

`ciao_sun.reference.fixtures` writes them. `ciao-sun reference` prints one.

## Where they are

Every build directory carries the fixtures generated from its own tiles:

```
<dataBase>/f1/<build>/manifest.json
<dataBase>/f1/<build>/tiles/<grid ref>.bin
<dataBase>/f1/<build>/fixtures/index.json
<dataBase>/f1/<build>/fixtures/<id>.json
```

`ciao-sun build` writes `fixtures/` before the directory takes its build id,
so a build directory always has them. `--queries` names the query set; the
default is the committed Bristol query set.

There are two sets:

| Set | Query set | Build | Used |
|---|---|---|---|
| Bristol | `src/ciao_sun/reference/bristol_queries.json` | each real build, on R2 | at release: CI reads the pinned build's `fixtures/index.json`, downloads the fixtures and the tiles they name |
| Synthetic | `fixtures/synthetic/queries.json` | `fixtures/synthetic/f1/20261111a/`, committed | on every push, with no Python and no network |

## The committed synthetic set

`fixtures/synthetic/` is a whole build directory in the hosted layout, so a
data loader pointed at it as `dataBase`, with the pin `{format: 1, build:
"20261111a"}`, reads it like a real build:

```
fixtures/synthetic/queries.json
fixtures/synthetic/decoded-tiles.json
fixtures/synthetic/f1/20261111a/manifest.json
fixtures/synthetic/f1/20261111a/tiles/ST5773.bin
fixtures/synthetic/f1/20261111a/tiles/ST5873.bin
fixtures/synthetic/f1/20261111a/fixtures/index.json
fixtures/synthetic/f1/20261111a/fixtures/<id>.json      15 fixtures, about 26 kB each
fixtures/synthetic/f1/20261111a/basemap/{z}/{x}/{y}.mvt  7 placeholder files
```

The `basemap/` files are a few bytes of text each (`mvt 15/16146/10903`), from
the synthetic Protomaps build of `tests/basemap_world.py`. They are not vector
tiles and will not render.

It is the real `build` run on the synthetic world of `tests/build_world.py`:
one 300 m east-west street astride two 1 km squares, its three edges named West
Row, Ridge Road and East Street, with 95 Candidates, a wall due true east, a row
of posts to the south and a far ridge to the north. The manifest's inputs point
at a fake web; nothing in it can be fetched.

Regenerate it with one command, and commit the result:

```
uv run python -m tests.synthetic_fixtures
```

Do so whenever the build, the tile format, the reference, the synthetic world
or the query set changes. `tests/test_fixtures.py` fails while the committed
set is stale, and checks that every query gets the status it is in the set
for. On one machine the command is byte-reproducible.

What the set exercises:

| Fixture | Case |
|---|---|
| `morning-winter-solstice`, `morning-summer-solstice`, `morning-march-equinox` | ranked Morning answers; BST and GMT |
| `morning-september-equinox-now`, `evening-march-equinox-now` | `now` clips the window |
| `morning-deep-winter-lamp` | ranked, with the lamp message; two spots with different Low-sun minutes |
| `morning-overcast-fallback`, `evening-deep-winter-overcast` | overcast fallback, "stay 30 min" |
| `morning-no-sun-in-reach` | no-sun fallback with `nearestSunBeyondLimit`; a near-boundary minute inside the window |
| `morning-lamp-only` | lamp-only, with `nextOutdoorLight` |
| `morning-not-covered` | origin outside the coverage polygon |
| `evening-winter-solstice`, `evening-summer-solstice`, `evening-september-equinox` | ranked Evening answers, with Last sun and split sun intervals |
| `evening-no-window` | no Evening window |

### What the Python reader decodes

`fixtures/synthetic/decoded-tiles.json` is outside the build directory and is
not part of a build. It holds, per grid ref, what `ciao_sun.tile_codec` reads
from each committed tile, so the JS tile decoder is checked against the Python
reader with no Python:

| Member | Holds |
|---|---|
| `names` | The Spot names, in order |
| `candidates` | The columns `latE7`, `lonE7`, `nodeIndex`, `offsetCm`, `nameIndex`, whole; `spotNames`, the Spot name of each Candidate |
| `candidates.profileCodesSha256` | SHA-256 of every Candidate's 1,440 storage codes, one byte each, in Candidate order, with the azimuth delta undone |
| `candidates.profileDegreesSha256` | SHA-256 of the same profiles as angles: little-endian float64 degrees |
| `candidates.firstProfileCodes` | Candidate 0's storage codes, to chase a wrong digest with |
| `walkGraph` | The columns `nodeId`, `nodeLatE7`, `nodeLonE7`, `edgeFrom`, `edgeTo`, `edgeLengthCm`, whole |

The same command writes it, and `tests/test_fixtures.py` fails while it is
stale.

The world is 320 m long, so no Answer lists more than two spots. Long ranked
lists, and saturated ties among thousands of Candidates, are only in the
Bristol set.

## `fixtures/index.json`

```json
{
  "format": 1,
  "build": "20261111a",
  "fixtures": [
    {
      "id": "morning-winter-solstice",
      "file": "morning-winter-solstice.json",
      "status": "ranked",
      "tiles": ["ST5773", "ST5873"]
    }
  ]
}
```

One line per fixture, in query set order. `file` is relative to `fixtures/`.
`status` is the Answer's status and `tiles` the fixture's `tiles`, repeated so
that a harness can fetch what it needs from the index alone.

## A fixture

`fixtures/<id>.json` is one line of compact JSON with five members:

```json
{
  "query": {"window": "morning", "date": "2026-03-20", "wakeTime": "03:20",
            "origin": {"lat": 51.4589122, "lon": -2.6051884},
            "maxWalkMin": 0.1, "sky": "clear"},
  "tiles": ["ST5773", "ST5873"],
  "answer": {"status": "fallback", "window": {"start": "2026-03-20T06:13:00+00:00", "…": "…"},
             "spots": [{"candidateId": "ST5873/21", "…": "…"}],
             "nearestSunBeyondLimit": {"candidateId": "ST5873/5", "…": "…"}},
  "sunTrack": {"start": "2026-03-20T00:00:00+00:00", "stepMin": 1,
               "azimuth": [354.2335, 354.5531, "…"],
               "apparentElevation": [-37.9009, -37.9159, "…"]},
  "nearBoundary": {"toleranceDeg": 0.01,
                   "candidates": {"ST5773/0": [375], "ST5873/5": [375]},
                   "lowSunBand": [375]}
}
```

| Member | Meaning |
|---|---|
| `query` | The Query, as `Query.to_json` writes it. `now` is present only when the query has one. |
| `tiles` | Grid refs, sorted: the tiles the Answer was computed over. The scorer under test must be given exactly these tiles. Empty when the Answer has no window. |
| `answer` | The Answer, as `Answer.to_json` writes it: unset fields are omitted, `spots` is always present. Every time is an ISO 8601 string with the Europe/London offset, on a whole minute. |
| `sunTrack` | The query date's sun track at the origin (`docs/solar-model.md`). |
| `nearBoundary` | The minutes at which a 0.01° difference in the sun's position could change the Answer. |

### `tiles`

A query touches the tiles of the manifest's tile index whose 1 km square lies
within 1,600 m of the origin, measured on the National Grid: 1,600 m is the
20 min walk cap at 80 m/min, and no Answer names a spot further than that. The
fixture's Answer is the Answer over those tiles and no others. An origin
outside the manifest's coverage polygon is `not-covered` and touches none.

The JS data loader may choose its tiles some other way; the fixture harness
must not, or its walk graph could differ from the reference's.

### `sunTrack`

| Field | Meaning |
|---|---|
| `start` | The instant of sample 0: local midnight of the query date |
| `stepMin` | Minutes between samples: always 1 |
| `azimuth` | True azimuth in degrees, one per minute of the local day |
| `apparentElevation` | Apparent elevation of the disc centre in degrees, one per minute |

Sample `i` is the instant `start + i` minutes. A day has 1,440 samples, or
1,380 and 1,500 on the days the clocks change. Values are rounded to 4 decimal
places. Every fixture has a sun track, whatever its status.

### `nearBoundary`

| Field | Meaning |
|---|---|
| `toleranceDeg` | 0.01 |
| `candidates` | Per `candidateId`, the minutes at which \|apparent elevation − Horizon profile at the sun's azimuth\| < 0.01°. The profile is interpolated as the scorer does. |
| `lowSunBand` | The minutes at which the apparent elevation is within 0.01° of 0° or of 30°, the ends of the low-sun band |

Minutes are indexes into the sun track, so they cover the whole local day, not
only the window: an Evening spot's Last sun is looked for over the whole day.
Intersect them with the Answer's window when judging Sun minutes.

`candidates` covers every Candidate within the 20 min walk cap of the origin,
listed in the Answer or not, because a flip at an unlisted Candidate can move
it into the list. A Candidate with no such minute is left out. It is empty
when the Answer has no window.

## Parity: what the JS scorer is held to

For each fixture the harness decodes the tiles in `tiles`, takes the coverage
polygon from the manifest, and runs the JS scorer on `query`.

**Solar.** At every minute of the JS sun track, true azimuth and apparent
elevation are within **0.01°** of `sunTrack` (compare azimuths modulo 360°),
and the track has the same `start` and number of samples. The stored values'
rounding, at most 0.00005°, is inside that. Nominal sunrise, Nominal sunset
and solar noon are the same minute (`docs/solar-model.md`).

**Answer.** The JS Answer equals `answer` member for member, with these
tolerances and no others:

| Fields | Tolerance |
|---|---|
| Strings, booleans, integers, every time, the order of `spots` and of intervals | Exact |
| `lat`, `lon`, `walkMin`, `lowSunMinutes`, `stayMin` | 1e-9: each is an integer divided by a constant (1e7, 80 m/min, 100) |
| `skyOpenness` | 0.001: it is rounded half up to 3 decimal places |
| A member absent from one Answer | Must be absent from the other |

**Near-boundary minutes.** A sun position 0.01° different may legitimately put
the sun on the other side of a Horizon profile, or of an end of the low-sun
band, for one minute. So at a minute listed in `nearBoundary`, and only there:

- for a Candidate in `candidates`, sun in view may differ between the JS and
  the reference at that Candidate's listed minutes;
- at a `lowSunBand` minute, whether the sun counts as low may differ, for
  every Candidate.

Everything that follows from such a flip may differ with it: that spot's sun
intervals, Sun minutes, Low-sun minutes, Last sun, Leave-by and `targetMet`,
and through them the ranking and the status. Precisely, the harness judges a
JS Answer that differs like this:

1. Only the minutes that can bear on the Answer count: a Candidate's listed
   minutes inside the window (for an Evening window, also those outside it,
   which bear on Last sun) and the `lowSunBand` minutes inside the window.
   With none, the Answer must match exactly.
2. The harness takes the reference's side at each such minute. For a
   Candidate the reference's Answer shows (in `spots` or as
   `nearestSunBeyondLimit`), sun in view in the window is whether the minute
   is in its `sunIntervals`; outside it, the minute is out of view after its
   `lastSun`, in view at it, and has no bearing before it. Low sun is whether
   the minute is in the `lowSunIntervals` of any shown spot with the sun in
   view then, or else from `sunTrack` against 0° and 30°, failing and naming
   the minute if the track's rounding to 4 decimal places could change it.
   A Candidate the Answer does not show is held out of view at its listed
   minutes in the window. That can only keep it out of the list, the set of
   spots with sun and `nearestSunBeyondLimit`, so if any flips reach the
   reference's Answer, these do. Its side is not read from `sunTrack`: next
   to a wall, the track's rounding alone can span the 0.01° tolerance.
3. The JS scorer answers the Query again with those sides forced, and
   nowhere else. That Answer must equal the reference's exactly, with the
   tolerances above.

So a flip can reorder or change the list, or turn `fallback` into `ranked`,
only when the JS, given the reference's side at listed minutes, would have
done the same. Any other difference still fails: a member no flip can move,
or a minute that is not listed.

A fixture whose `candidates` is empty and whose `lowSunBand` holds no minute
of its window has no such freedom: its Answer must match exactly. Ten of the
fifteen synthetic fixtures are like that. `morning-no-sun-in-reach` has a
listed minute inside its window, at Candidates beyond its 0.1 min max walk:
there a flip could change `nearestSunBeyondLimit` but not the status, since
its one reachable Candidate has no listed minute.

Not listed: the minutes at which the sun's azimuth is within 0.01° of a
profile sample at the edge of the Sky openness sector. A flip there adds or
drops one sample of a few hundred from the mean. If the JS meets one, list those
minutes here rather than loosen the harness.

## Query sets

A query set is a JSON file:

```json
{
  "about": "free text",
  "queries": [
    {
      "id": "morning-winter-solstice",
      "expect": "ranked",
      "note": "free text",
      "query": {"window": "morning", "date": "2026-12-21", "wakeTime": "07:30",
                "origin": {"lat": 51.4589122, "lon": -2.6051884},
                "maxWalkMin": 15, "sky": "clear"}
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `id` | Names the fixture file. Lower-case words joined by hyphens, unique in the set, not `index`. |
| `query` | The Query |
| `expect` | Optional. The status the query is in the set to exercise. |
| `about`, `note` | Optional, ignored |

A malformed query set stops `ciao-sun build` before it builds anything. A
query whose Answer does not have its `expect` status is reported by the build
and its fixture is still written: the fixture is what the reference answers,
and `index.json` records the status it got.

The Bristol query set covers five origins across the city, both solstices,
both equinoxes and a deep-winter date in both windows, and one query per
status case. Three of its cases are decided by the sun alone and hold on any
build: `morning-lamp-only`, `evening-no-window` and the lamp message of
`morning-winter-solstice-lamp`. The rest depend on the build. In particular
`morning-no-sun-in-reach` expects a fallback because nothing within a 2 min
walk of a terraced street sees the sun in the 10 min after Nominal sunrise;
whether it also gets a `nearestSunBeyondLimit` is up to the terrain. Check the
build's report, and `fixtures/index.json`, on the first real build.

## Debugging one query

```
uv run ciao-sun reference fixtures/synthetic/f1/20261111a/fixtures/morning-winter-solstice.json \
    --build fixtures/synthetic/f1/20261111a | jq .answer
```

`ciao-sun reference <query> --build <build dir>` prints exactly the bytes of
the fixture file the generator writes for that Query over that build. `<query>`
is a JSON file or the JSON itself; a fixture file stands for its own query.
