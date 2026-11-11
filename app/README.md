# Ciao Sun app

The client: a self-contained static bundle, served under `/ciao-sun/`. It is
the canonical scorer (ADR 0001); the Python package beside it is the build
pipeline and the reference. Terms follow `GLOSSARY.md`; the spec is #27.

## Stack

TypeScript (strict), Vite for the bundle, Vitest for tests, npm. No framework
and no runtime dependencies yet. Node is pinned in `.nvmrc`, and every
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
| `npm run dev` | Vite dev server at `/ciao-sun/` |

## Layout

```
index.html              the page; Vite's entry
vite.config.ts          Vite and Vitest config; base is /ciao-sun/
src/main.ts             entry script (a placeholder until the answer screen)
src/contract.ts         the Query and Answer types, as fixture JSON holds them
src/tile/decode.ts      tile decoder: f1 bytes -> Tile (docs/tile-format-f1.md)
src/solar/sun-track.ts  solar model: sunTrack(), refraction, the three events (docs/solar-model.md)
src/solar/spa.ts        NREL SPA geometric position
src/solar/spa-tables.ts SPA periodic terms, generated from pvlib; not edited by hand
src/solar/local-day.ts  local civil days and ISO times in a time zone, via Intl
src/router/world.ts     router: tiles joined into one walk graph; origin snap and Dijkstra walk
src/scorer/answer.ts    scorer: (Query, tiles) -> Answer; its rules beside it (see its header)
test/parity/            the golden-fixture harness (below)
```

A module is a directory under `src/` named for the spec's module (data
loader, router, scorer, forecast adapter, settings store, ...). Static files
that must keep their name, such as `sw.js`, go in `public/`.

## Conventions

- Unit tests sit beside the module as `*.test.ts`. Tests that span modules go
  under `test/`.
- A test asserts behaviour through a module's exports, against values from an
  independent source: a document's worked example, the Python reference's
  output, a fixture. Tests run in Node, so a module that needs the DOM takes
  it as an argument or gets its own Vitest environment.
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
| The Answer equals the reference's | on for Morning `ranked`; the rest skipped as pending #44 |

- **The scorer** is plugged in at `test/parity/scorer.ts`. The harness gives
  it the Query, exactly the fixture's tiles and the manifest's coverage
  polygon, and compares with `answerDifferences` (`test/parity/parity.ts`),
  which applies the stated tolerances. `answerParityPending` there names the
  fixtures whose Answers are not written yet (#44 deletes it).
- **Near-boundary minutes:** `unexplainedDifferences` drops only the
  differences a flip at a listed minute explains (`effectiveFreedom`: in the
  window, or all day for an Evening window), and only in that Spot's
  flip-dependent members. A flip that reorders the list or changes the status
  still fails.
- **Which build:** the committed synthetic one, `fixtures/synthetic` as
  `dataBase` with the pin `{format: 1, build: "20261111a"}`. To run the same
  tests over another build directory in the hosted layout (the release job,
  #54), set `CIAO_SUN_FIXTURES_DATA_BASE` and `CIAO_SUN_FIXTURES_BUILD`.
- **Tile decoding** is also checked value for value against the Python reader
  in `src/tile/decode.test.ts`, from `fixtures/synthetic/decoded-tiles.json`.
