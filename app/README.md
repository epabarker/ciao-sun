# Ciao Sun app

The client: a self-contained static bundle, served under `/ciao-sun/`. It is
the canonical scorer (ADR 0001); the Python package beside it is the build
pipeline and the reference. Terms follow `GLOSSARY.md`; the spec is #27.

## Stack

TypeScript (strict), Vite for the bundle, Vitest for tests, npm. No framework
and no runtime dependencies yet; views are plain DOM built with `src/ui/dom.ts`'s
`h()`. happy-dom (dev only) is the DOM for rendering tests. Node is pinned in `.nvmrc`, and every
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
src/settings/store.ts   settings store: Wake time, max walk; browser storage with a memory fallback
src/query/query.ts      the sentence's inputs -> Query; each window's next date; the tab the app opens on
src/query/origin.ts     the typed origin "lat, lon"
src/ui/                 the answer screen (below)
src/contract.ts         the Query and Answer types, as fixture JSON holds them
src/tile/decode.ts      tile decoder: f1 bytes -> Tile (docs/tile-format-f1.md)
src/solar/sun-track.ts  solar model: sunTrack(), refraction, the three events (docs/solar-model.md)
src/solar/spa.ts        NREL SPA geometric position
src/solar/spa-tables.ts SPA periodic terms, generated from pvlib; not edited by hand
src/solar/local-day.ts  local civil days and ISO times in a time zone, via Intl
src/router/world.ts     router: tiles joined into one walk graph; origin snap and Dijkstra walk
src/scorer/answer.ts    scorer: (Query, tiles, coverage) -> Answer; its rules beside it (see its header)
src/forecast/forecast.ts forecast adapter: forecastSky() -> the sky slot's category or "unavailable" (fixtures/cloud/cases.json)
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
| `ui/screen.ts` | the frame: `header.top` (tabs, sentence), `main.sheet` (result), `footer.foot`; the `Result` kinds (loading, unreadable data, data unavailable, ...) | #47 makes `.sheet` a bottom sheet over the map; #51 an About link in the footer |
| `ui/tabs.ts` | the Morning/Evening tabs; the fixed copy per tab (`SAFETY_COPY` on both, `DIM_LIGHTS` on Evening) | |
| `ui/sentence.ts` | the sentence editor; its words per window in `WORDING` | #49 saved places in `OriginSlot`; #50 the sky slot's forecast and credit |
| `ui/answer-view.ts` | an Answer by status, from `STATUS_VIEWS`, with an `AnswerContext` (the Query, read for its date and `now`; the message actions); the lamp notice | #47 links rows (`data-spot` is the candidateId) to markers |
| `ui/timeline.ts` | the timeline bar and its axis; the fallback `stay` block; a leave-by before the axis start is marked `data-off-axis="before"` | |
| `ui/format.ts`, `ui/dom.ts`, `ui/style.css` | clock and walk labels; the element builder; styles on colour tokens | |

The app opens on whichever window comes next (`chooseWindow` in
`query/query.ts`): today's Morning until Wake time + 3 h, then today's Evening
until Nominal sunset, then tomorrow's Morning. Nominal sunset for that choice
and for the Evening tab's date is read at `PLANNING_POINT` (central Bristol),
so it is made before GPS answers and a late fix never flips the tab. A tab tap
plans that tab's next window. A `lamp-only` Answer whose Query shows the
Morning window already over (`morningWindowOver`: `now` on the query date at
or after Wake time + 3 h) shows "Morning window has ended" with no lamp advice;
otherwise it is a morning with no daylight, and gets the lamp message.

`AppDeps` (in `app.ts`) is every outside dependency: the pin, `fetch`, the
storage accessor, the clock and GPS. `test/app/` runs the whole screen through
it over the synthetic build. The scorer is called in one place, `score()` in
`app.ts`, with the manifest's coverage polygon: the scorer decides
`not-covered` (`scorer/coverage.ts`, which the loader also uses to skip
fetching tiles for an origin outside it).

The settings store (`openSettings(() => localStorage)`) has `read()`,
`update(change)` and `persistent`; a new setting is a field of `Settings` with
a reader in `FIELDS`. Wake time edited in the sentence is an override for one
query; "Make HH:MM my usual Wake time" saves it. Max walk saves on change.

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
