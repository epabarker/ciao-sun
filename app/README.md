# Ciao Sun app

The client: a self-contained static bundle, served under `/ciao-sun/`. It is
the canonical scorer (ADR 0001); the Python package beside it is the build
pipeline and the reference. Terms follow `GLOSSARY.md`; the spec is #27.

## Stack

TypeScript (strict), Vite for the bundle, Vitest for tests, npm. No framework;
views are plain DOM built with `src/ui/dom.ts`'s `h()`. The runtime
dependencies are the map's: `maplibre-gl` and `@protomaps/basemaps` (its
style), loaded as their own chunk (see "The map"). happy-dom (dev only) is the DOM for rendering tests. Node is pinned in `.nvmrc`, and every
dependency is pinned exactly in `package.json` with `package-lock.json`
committed.

## Commands

Run from `app/`. CI (`.github/workflows/ci.yml`, job `js`) runs the last four
on every push.

| Command | Does |
|---|---|
| `npm ci` | Clean install from the lockfile |
| `npm run typecheck` | `tsc --noEmit` over `src/`, `test/` and the config |
| `npm test` | Every test, once (`npm run test:watch` to keep it running) |
| `npm run build` | The bundle, into `dist/`: `index.html` and hashed files under `assets/` |
| `npm run dev` | Vite dev server at `/ciao-sun/`, serving the synthetic build at `/ciao-sun/synthetic-data/` (so does `vite preview`) |

## Layout

```
index.html              the page; Vite's entry
vite.config.ts          Vite and Vitest config; base is /ciao-sun/
release.json            the pin: {dataBase, format, build} (below)
src/main.ts             entry: the browser's dependencies, handed to startApp
src/app.ts              the app: release config + data loader + settings + GPS + scorer -> screen
src/config/release.ts   the release config, read from release.json at build time
src/loader/loader.ts    data loader: openBuild(pin) checks the manifest format; Build.area(origin) -> tiles
src/loader/grid.ts      WGS84 -> National Grid, and the 1 km tiles in reach of an origin
src/scorer/coverage.ts  whether an origin is inside the manifest's coverage polygon (the scorer's not-covered; the loader uses it too)
src/settings/store.ts   settings store: Wake time, max walk, saved places; browser storage with a memory fallback
src/query/query.ts      the sentence's inputs -> Query; the next Morning window's date
src/query/origin.ts     the typed origin "lat, lon"
src/ui/                 the answer screen (below)
src/map/                the map under the sheet (below): its interface, MapLibre adapter and basemap style
src/about/about.ts      the About sheet's content: credits, survey years, licence from the manifest; the fixed caveats
src/contract.ts         the Query and Answer types, as fixture JSON holds them
src/tile/decode.ts      tile decoder: f1 bytes -> Tile (docs/tile-format-f1.md)
src/solar/sun-track.ts  solar model: sunTrack(), refraction, the three events (docs/solar-model.md)
src/solar/spa.ts        NREL SPA geometric position
src/solar/spa-tables.ts SPA periodic terms, generated from pvlib; not edited by hand
src/solar/local-day.ts  local civil days and ISO times in a time zone, via Intl
src/router/world.ts     router: tiles joined into one walk graph; origin snap and Dijkstra walk
src/scorer/answer.ts    scorer: (Query, tiles, coverage) -> Answer; its rules beside it (see its header)
src/forecast/forecast.ts forecast adapter: forecastSky() -> the sky slot's category or "unavailable" (fixtures/cloud/cases.json)
src/forecast/span.ts    the span C is averaged over, from a Query and the scorer's window plans
test/parity/            the golden-fixture harness (below)
```

A module is a directory under `src/` named for the spec's module (data
loader, router, scorer, forecast adapter, settings store, ...). Never name one
`data/`: the repo's `.gitignore` ignores every `data/` directory. Static files
that must keep their name, such as `sw.js`, go in `public/`.

## The release config

`release.json` is the committed pin file of spec #27 ("Release and CI"):
`{dataBase, format, build}`. `src/config/release.ts` validates it and the
bundle carries it; nothing else in `src/` names a data origin. A relative
`dataBase` resolves against the page. Until the first Bristol build (#55) it
pins the synthetic build at `synthetic-data/`, which only the dev and preview
servers serve: #55 sets the R2 data subdomain and the build id, and #54's
release job reads the same file.

## The data loader

`openBuild(pin, {fetch, baseUrl})` fetches the manifest and refuses a format
other than f1 with `UnsupportedFormatError` before any tile is requested.
`Build.area(origin)` returns `{covered: false}` outside the coverage polygon,
else the decoded tiles within `TILE_REACH_M` (the 20 min cap at 80 m/min, as
the reference's `tiles_touched`), each fetched once per Build.

## The answer screen

`src/app.ts` holds the state and wires everything; `src/ui/` renders it. Views
are pure functions of state that report through callbacks, and the screen is
re-rendered on every change. The UI shows Answer fields only, never scores.

| File | Does | Extended by |
|---|---|---|
| `ui/screen.ts` | the frame: the persistent `.map`, then `header.top` (sentence) and `main.sheet` (result, then `footer.foot`) over it, and the About sheet while open; the `Result` kinds (loading, unreadable data, data unavailable, ...) | #48 puts tabs in the header and safety copy in the footer |
| `ui/sheet.ts` | the bottom sheet: stops `peek`/`half`/`full` (heights in `style.css`'s `--sheet-h`), drag and tap on its handle | |
| `ui/about-view.ts` | the footer's "About the data" link (in the frame, so on both tabs) and the sheet. Every credit, year and licence is from the loaded manifest's `attribution`, `lidarSurveyYears` and `licence`, rendered in order with none named in code; only `CAVEATS` in `about/about.ts` is fixed copy. Open is app state (`aboutOpen`), so a re-render keeps it open | |
| `ui/sentence.ts` | the sentence editor; its words per window in `WORDING`; the origin slot (`OriginSlot`: locating, GPS, typed or a saved place) | #48 Evening wording |
| `ui/sky-slot.ts` | where the sky slot's value came from (`SkySource`, on the select as `data-sky-source`); the line under the sentence with the fetch time and `SKY_CREDIT`, shown only when the forecast filled the slot | |
| `ui/places.ts` | saved places: the toggle under the sentence, rename, delete, save the origin in use | |
| `ui/answer-view.ts` | an Answer by status, from `STATUS_VIEWS`; a row's head (`data-action="select-spot"`) highlights it, and the highlighted row (`aria-current`) shows its sun times | #48 replaces the `fallback`, `lamp-only` and `no-evening-window` entries and adds the lamp notice |
| `ui/timeline.ts` | the timeline bar and its axis | #48 the "stay N min" segment (`SegmentKind` has `stay`) |
| `ui/format.ts`, `ui/dom.ts`, `ui/style.css` | clock and walk labels; the element builder; styles on colour tokens | |

`AppDeps` (in `app.ts`) is every outside dependency: the pin, `fetch`, the
storage accessor, the clock, GPS and the map. `test/app/` runs the whole screen through
it over the synthetic build. The scorer is called in one place, `score()` in
`app.ts`, with the manifest's coverage polygon: the scorer decides
`not-covered` (`scorer/coverage.ts`, which the loader also uses to skip
fetching tiles for an origin outside it).

The sky slot is pre-filled from the forecast (`askForecast()` in `app.ts`):
`forecast/span.ts` turns the Query into the span (from the scorer's window
plans), and `forecastSky()` asks Open-Meteo through the same `fetch` with only
the 0.05° coordinate (`test/app/forecast-sky.test.ts` checks no request carries
more). The query never waits for it. A slot set by hand stays so, whatever
arrives, until the window, date or place changes; offline, a failed or slow
request, or a date past the horizon leaves the slot for manual entry.

The settings store (`openSettings(() => localStorage)`) has `read()`,
`update(change)` and `persistent`; a new setting is a field of `Settings` with
a reader in `FIELDS`. Wake time edited in the sentence is an override for one
query; "Make HH:MM my usual Wake time" saves it. Max walk saves on change.

Saved places (#49) are `Settings.places`, a list of `SavedPlace`
`{id, name, lat, lon}` in saving order; `id` is a decimal string, unique on
the phone. They are only ever written to the settings store: the one network
dependency, `fetch`, is called by the data loader with the pinned build's file
paths, and by the forecast adapter with only the origin's 0.05° cell, never a
place's position or name. The origin in use is `state.origin`, an `OriginSlot`, and
`origin()` in `app.ts` turns it into the Query's `{lat, lon}`; saving takes the
position from the origin in use (GPS or typed). Once a place is saved the
origin slot is a select of "here", each place and "a position…", so a denied
GPS offers them. `test/app/saved-places.test.ts` covers it through `AppDeps`.

## The map

The screen talks to the map through `MapSurface` (`src/map/map.ts`):
`show(markers)` puts the origin and the numbered spots on it and frames them,
`highlight(id)` marks one and brings it into view, and the factory's
`onSelect` reports a tap on a marker. `AppDeps.map` is the factory: `main.ts`
passes the MapLibre one (`src/map/maplibre.ts`, imported on demand, so it is a
separate chunk), tests pass a fake (`test/app/map.test.ts`), and without one
the screen is the list alone. `src/map/link.ts` asks the map to change only
what changed on each draw; the map is made once, when the build opens, and a
factory that fails (no WebGL) leaves the list working.

- **Basemap:** `basemapOf` (`src/map/manifest.ts`) reads the manifest's
  `basemap` section into `<build>/basemap/{z}/{x}/{y}.mvt`, bounds and zooms;
  `basemapStyle` (`src/map/style.ts`) is Protomaps' v4 `light` flavour over it,
  with the source's `bounds`, `minzoom` and `maxzoom` set so no tile outside
  them is requested. The style has no label or icon layers, so it needs no
  glyphs or sprite, and the map fetches nothing but the build's tiles (itself,
  from its worker, not through `AppDeps.fetch`). The
  camera is kept at or above `minZoom` and within the bounds plus a margin
  (`cameraBounds`). A tile that fails to load or parse is logged once and the
  map shows its plain ground under the markers (the synthetic build's tiles
  are text placeholders, so `npm run dev` looks like that).
- **Markers** are HTML (`.marker-spot`, `.marker-origin`), so the numbers need
  no glyphs.
- **Credits:** the corner ⓘ is MapLibre's compact attribution, carrying the
  manifest's `attribution` text for the sources in `MAP_CREDIT_SOURCES`
  (OpenStreetMap, Protomaps); it rides on the sheet's top edge.
- **Worker:** MapLibre's worker is its own file
  (`assets/maplibre-gl-worker-<hash>.mjs`), set with `setWorkerUrl`; the shell
  includes it.

## Conventions

- Unit tests sit beside the module as `*.test.ts`. Tests that span modules go
  under `test/`.
- A test asserts behaviour through a module's exports, against values from an
  independent source: a document's worked example, the Python reference's
  output, a fixture. Tests run in Node; a rendering test opts into happy-dom with
  `// @vitest-environment happy-dom` on its first line.
- `src/` never imports from `test/` or from `node:`; only tests read files.
- Angles are degrees, azimuths true and clockwise from north. Instants are
  milliseconds since the Unix epoch; a time in an Answer is written with
  `toLocalIso`. Positions from a tile stay integers (`latE7`) until shown.
- The reference's numbers are ported with the reference's own expressions,
  so that both give the same double where that is possible.

## The golden-fixture harness

`test/parity/fixtures.test.ts` loads every fixture of one build directory and
holds the JS to the parity rules of `docs/fixtures.md`:

| Check | State |
|---|---|
| The fixture's tiles decode; its spots are Candidates of them | on |
| Sun track within 0.01° of the reference at every minute | on |
| Nominal sunrise, Nominal sunset and solar noon on the same minute | on |
| The Answer equals the reference's | on for every fixture and status |

- **The scorer** is plugged in at `test/parity/scorer.ts`. The harness gives
  it the Query, exactly the fixture's tiles and the manifest's coverage
  polygon, and compares with `answerDifferences` (`test/parity/parity.ts`),
  which applies the stated tolerances.
- **Near-boundary minutes** (docs/fixtures.md): when the Answers differ,
  `unexplainedDifferences` answers the Query again with the reference's side
  of each listed minute forced (`referenceSight`, through the scorer's
  internal `answerWith`), and whatever still differs fails. A flip may so
  reorder the list or change the status, but only as the JS itself would.
- **Which build:** the committed synthetic one, `fixtures/synthetic` as
  `dataBase` with the pin `{format: 1, build: "20261111a"}`. To run the same
  tests over another build directory in the hosted layout (the release job,
  #54), set `CIAO_SUN_FIXTURES_DATA_BASE` and `CIAO_SUN_FIXTURES_BUILD`.
- **Tile decoding** is also checked value for value against the Python reader
  in `src/tile/decode.test.ts`, from `fixtures/synthetic/decoded-tiles.json`.
