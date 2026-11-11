# Site contract

What a site that serves Ciao Sun consumes from this repo, and what it must do.
This is the one page a site maintainer needs. This repo's job ends at the
GitHub release; the site (`epabarker/edbarker-dev`) syncs a release itself
(spec #27, "Out of Scope"). The reasoning is
[ADR 0002](adr/0002-data-on-r2-pinned-builds.md).

## What a release is

A GitHub release tagged `ciao-sun-v<x.y.z>` has exactly two assets:

| Asset | Holds |
|---|---|
| `ciao-sun-<x.y.z>.tar.gz` | The app bundle: `index.html`, `sw.js` and `assets/`, at the top level of the archive (no leading directory) |
| `ciao-sun-<x.y.z>.tar.gz.sha256` | One `sha256sum` line for the tarball |

A release exists only if the JS passed every golden fixture of the data build
it pins (`.github/workflows/release.yml`, `app/scripts/release.ts`). A tag with
no assets is a release that failed. Don't sync it.

## Vendoring

Check the tarball, then extract it into the directory the site serves at
`/ciao-sun/`. Replace the old contents; don't merge them:

```
sha256sum -c ciao-sun-<x.y.z>.tar.gz.sha256
rm -rf public/ciao-sun && mkdir -p public/ciao-sun
tar -xzf ciao-sun-<x.y.z>.tar.gz -C public/ciao-sun
```

The bundle is self-contained. Every file the page and the service worker
load is in it, and it needs no build step, no layout and no other file from
the site. Serve it outside the site's own layout and templates.

The tarball carries no data. The tiles, basemap and manifest are fetched at
run time from the data host the release pins (below).

## Headers

| Path | `Cache-Control` | Why |
|---|---|---|
| `/ciao-sun/assets/*` | `public, max-age=31536000, immutable` | File names are content hashes |
| `/ciao-sun/sw.js` | `no-cache` | The browser must see a new worker as soon as it is released |
| `/ciao-sun/index.html` | `no-cache` | It names the current hashed assets |

On Cloudflare Workers static assets, as a `_headers` file:

```
/ciao-sun/assets/*
  Cache-Control: public, max-age=31536000, immutable
/ciao-sun/sw.js
  Cache-Control: no-cache
/ciao-sun/index.html
  Cache-Control: no-cache
```

Also:

- **`/ciao-sun/index.html` is answered with a 200**, not a redirect to
  `/ciao-sun/`. The worker precaches it by that URL. It copes with a redirect,
  but it shouldn't have to.
- **`/ciao-sun`** (no slash) redirects to `/ciao-sun/`, which serves
  `index.html`.
- **Send no `Service-Worker-Allowed` header.**

## The service worker's scope

`/ciao-sun/sw.js` registers with scope `/ciao-sun/`. It controls only pages
under `/ciao-sun/` and never the site's other pages. Its caches are all named
`ciao-sun-…`, and it deletes only its own old ones. Don't serve another
`sw.js` with a scope that covers `/ciao-sun/`.

A new release ships a new `sw.js`, because the pinned data build is bundled
into it. Open pages pick it up on their next foreground, with no prompt.

## The data origin

The bundle reads its data host from the release config, `app/release.json`
(`{dataBase, format, build}`), which is baked in at build time. Nothing else
names a data origin. The site doesn't configure it, and the data host can
move without the site changing anything: a release with a new `dataBase` is
an ordinary release.

The data host is an R2 bucket on a custom subdomain. Its CORS policy allows
`GET` from `https://edbarker.dev` (`docs/publishing.md`). Serving the app from
another origin needs that origin added there first.

## Version numbers

| Bump | Means | Site does |
|---|---|---|
| Patch, `x.y.Z` | Data-only refresh: a new pinned build, same app | Sync; no other change |
| Minor, `x.Y.0` | App features, or a tile format bump | Sync; look at the app once |
| Major, `X.0.0` | A change to this contract: paths, headers, scope, tarball layout | Read this page's history and change the site to match before syncing |
