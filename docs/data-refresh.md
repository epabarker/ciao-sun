# Data refresh and release runbook

How a new data build reaches the site: fetch, build, publish, pin, tag.
Refreshes are manual in Stage 1, with no scheduled staleness checks. Do one
on purpose, when a trigger below fires. Terms follow `GLOSSARY.md`. The
decision behind pinned builds is
[ADR 0002](adr/0002-data-on-r2-pinned-builds.md). What the site does with a
release is [the site contract](site-contract.md).

## When to refresh

- [ ] **A new EA composite year.** The LIDAR Composite DSM or DTM has a new
      survey year over the coverage.
- [ ] **An OSM change to walk edges or Spot names.** A path opened or closed,
      or a street renamed, inside the coverage.
- [ ] **A basemap refresh.** A newer Protomaps basemap version to pin
      (`--protomaps-build`).
- [ ] **A horizon or scoring algorithm change.** The precompute, the build
      checks, the reference scorer or the query set changed. Regenerate the
      synthetic set too (`README.md`, "Development").
- [ ] **A format bump.** The tile or manifest format changed: a new
      `docs/tile-format-f<n>.md`, a loader that reads it, and `format` in the
      pin.

## Which version to release

| Change | Bump | Example |
|---|---|---|
| Data only: a new pinned build, the same app | patch | 0.1.0 → 0.1.1 |
| App features, or a format bump | minor | 0.1.1 → 0.2.0 |
| A change the site must react to: anything in [the site contract](site-contract.md) | major | 0.2.0 → 1.0.0 |

## Steps

1. **Fetch** the inputs:

   ```
   uv run ciao-sun fetch --coverage bristol.geojson --osm-date <yymmdd>
   ```

   This writes `data/inputs/` and its `fetch.lock.json` (`README.md`,
   "Fetching the build inputs").

2. **Build:**

   ```
   uv run ciao-sun build --coverage bristol.geojson
   ```

   This writes `data/builds/f1/<build id>/`. The build fails, and writes no
   directory, if the direct-ray profile check or the water guard fails.
   Read the report. Any query whose Answer lacks its `expect` status is
   listed there, and its fixture's status is in `fixtures/index.json`
   (`docs/fixtures.md`). To debug one Answer, use `uv run ciao-sun reference
   <fixture> --build <build dir>`.

3. **Publish:**

   ```
   uv run ciao-sun publish data/builds/f1/<build id> --inputs data/inputs
   ```

   It needs the R2 credentials of `docs/publishing.md`. Then run that page's
   `curl` checks.

4. **Pin.** In `app/release.json`, set `build` to the new build id (and
   `format` on a format bump). `dataBase` is the data subdomain's https URL.
   The release job refuses a relative or non-https `dataBase`.

5. **Bump the version** by the table above, from `app/`:

   ```
   npm version --no-git-tag-version <x.y.z>
   ```

   This updates `package.json` and `package-lock.json`. The shell cache is
   named for this version, so a release without a bump would land in the old
   cache.

6. **Rehearse** the release job locally, from `app/`. The data host is a
   public read, so this fetches the real pinned build:

   ```
   node scripts/release.ts --tag ciao-sun-v<x.y.z> --out /tmp/ciao-sun-release
   ```

   It prints `release ready` and the SHA-256, or `release refused: …` with
   the reason. To rehearse before publishing, add `--mirror ../data/builds`.
   The pin must still be https, but its files are read from the local build
   directory, resolved from `app/`.

7. **Commit** the pin and the version, push, and wait for CI to pass.

8. **Tag** that commit and push the tag:

   ```
   git tag ciao-sun-v<x.y.z>
   git push origin ciao-sun-v<x.y.z>
   ```

   `.github/workflows/release.yml` runs `app/scripts/release.ts`, in this
   order:
   - check the tag against `package.json`'s version;
   - check the pin;
   - download the pinned build's manifest, `fixtures/index.json`, every
     fixture and the tiles they name;
   - run the golden-fixture harness over them;
   - build the bundle and check that it carries the pin and the version;
   - create the GitHub release with the tarball and its SHA-256.

   Any refusal fails the job before the release is created. Push the tag and
   let the job create the release. Don't create one in the GitHub UI: if a
   release already exists for the tag, `gh release create` fails and no
   assets are attached.

9. **The site syncs the release.** That happens in the website repo, not this
   one ([the site contract](site-contract.md)).

A failed tag can't be retried as is. Fix the problem, then release the next
patch version. Don't move a pushed tag.

## The first real build (#55): check by eye

Earlier tickets left these unverified. Check each on the first Bristol build,
and correct the doc named if it is wrong.

- [ ] **The EA zip and Terrain 50 layouts.** `fetch` and `build` read the real
      archives: the file names inside the zips, and the CRS and nodata of the
      GeoTIFFs (`src/ciao_sun/fetch.py`, `README.md`).
- [ ] **The build-check tolerances on steep far skylines.** The direct-ray
      profile check passes without being loosened where the far ridge is
      steep (`ciao_sun.build_checks`).
- [ ] **The water guard over open water.** The Avon and the docks set no
      Candidate's horizon, and the guard does not fail on them.
- [ ] **The real R2 client and CORS.** `publish` against real buckets; the
      `curl` checks in `docs/publishing.md`; the app on `localhost` and on
      `https://edbarker.dev` fetching the manifest cross-origin.
- [ ] **The data host from a GitHub runner.** The release job's download
      succeeds from Actions, not only from a laptop. Bot Fight Mode or a WAF
      rule on the data subdomain must not answer the runner with a 403.
- [ ] **The basemap.** Our v4 style renders against the 4.15.1 tiles: roads,
      water, labels.
- [ ] **Safari offline.** On an iPhone, open the app once online, then in
      airplane mode. The shell, the map and an Answer still load (`app/README.md`,
      "The service worker").
- [ ] **The Bristol fixture `expect` statuses.** In the build report, every
      Bristol query gets the status it is in the set for. Pay particular
      attention to `morning-no-sun-in-reach` (`docs/fixtures.md`).
