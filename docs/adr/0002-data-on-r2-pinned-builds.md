---
status: accepted
---

# Data on R2 behind a data base URL, with app releases pinning an immutable data build

The sunspot app shell is vendored into the website (`epabarker/edbarker-dev`) at `/sunspot/`, the way the site vendors its other apps. The data is not vendored. The tile bundle and the basemap live in an R2 bucket on a subdomain, and the client reaches them only through a configured **data base URL**. Data is published as immutable builds, at `<dataBase>/f<format>/<build>/…`, and every app release pins exactly one `{format, build}`. A data refresh reaches users only through a new app release synced into the site.

This departs from the site's convention of committing everything into git. That convention works for a small app shell. It doesn't work for about 150 binary tiles that would be re-added to git history on every rebuild. It also can't scale: England at 1 km tiles is over the 100k-file cap on Workers static assets, even on the Paid plan, and R2 is where Stage 2 has to go anyway. Pinning keeps the [ADR 0001](0001-static-precompute-client-evaluation.md) guarantee: CI checks the canonical JS against golden fixtures from the very build it ships with, so no untested app and data pair can reach a phone.

## Considered options

- **Commit the data into the site repo.** Same origin and no new infrastructure. Rejected for permanent git bloat and the Stage 2 file cap.
- **Fetch the data during the site's Workers Build.** Git stays clean. Rejected because the Stage 2 cap still applies and site builds would come to depend on this repo.
- **A mutable `current.json` pointer instead of pins.** A data refresh would need no site commit. Rejected because a build could then go live without the app's CI ever running against it, which is too high a price for refreshes this rare.
- **A single `.pmtiles` basemap archive.** Rejected. Workers static assets answer a Range request with `200` and the full body (measured on edbarker.dev, 2026-11-10), and the Cache API won't store `206` responses, so the service worker couldn't cache it for offline use. The basemap is served as a `z/x/y` tile directory instead.

## Consequences

- **Never rewrite a published build.** Builds are immutable and cached for a year, so a fix is always a new build plus a new app release.
- **Keep old builds while any cached app might still pin them.** In Stage 1, nothing is deleted.
- **The data host needs CORS** for `https://edbarker.dev` (plus `localhost` for development). The app checks the manifest's `format` before reading any tile.
