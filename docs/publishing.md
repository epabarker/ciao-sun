# Publishing a build

`ciao-sun publish <build directory>` uploads one build to the data bucket and
archives the inputs it was made from. The rules it keeps are in
`src/ciao_sun/publish.py`; the decision behind them is
[ADR 0002](adr/0002-data-on-r2-pinned-builds.md). This page is the setup that
has to exist first, done once by hand in the Cloudflare dashboard, and the
command to run afterwards.

This page was first run for real on 2026-11-12 (#55): build `20261111b` to
`ciao-sun-data`, served at `https://ciao-sun-data.edbarker.dev`, with its inputs
in `ciao-sun-inputs`. Every step below worked as written.

## One-time setup

### 1. Two R2 buckets

| Bucket | Access | Holds |
|---|---|---|
| data bucket | public, through a custom domain only | `f<format>/<build>/…`, what the app fetches |
| inputs bucket | private: no custom domain, no `r2.dev` URL | `f<format>/<build>/…`, each build's OSM `.pbf` and Terrain 50 zip |

They must be two buckets. `publish` refuses to run with one name for both,
because everything in the data bucket is public.

### 2. The data bucket's custom domain

Connect the data bucket to a subdomain (R2 > the bucket > Settings > Custom
Domains). The site's zone must be in the same Cloudflare account. Keep the
subdomain one level deep (`ciao-sun-data.edbarker.dev`, not
`ciao-sun.data.edbarker.dev`): the free Universal SSL certificate covers only
first-level subdomains. That URL is the app's **data base URL**: the object with key
`f1/20261110a/manifest.json` is served at `<dataBase>/f1/20261110a/manifest.json`.
Leave the bucket's `r2.dev` public URL disabled, so the custom domain is the
only way in.

Do not add a Cache Rule or Transform Rule that rewrites `Cache-Control` or
strips `Content-Encoding` on that hostname: `publish` sets both per object.

### 3. CORS on the data bucket

The app is served from `https://edbarker.dev` and fetches the data from another
origin, so the data bucket needs a CORS policy (R2 > the bucket > Settings >
CORS Policy):

```json
[
  {
    "AllowedOrigins": [
      "https://edbarker.dev",
      "http://localhost:5173",
      "http://localhost:4173"
    ],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 86400
  }
]
```

An origin includes its port, so list every `http://localhost:<port>` used in
development; the two above are placeholders for the dev and preview servers.
The inputs bucket gets no CORS policy.

### 4. An API token for publishing

Create an R2 API token (R2 > Manage API Tokens) with **Object Read & Write**,
scoped to the two buckets. `publish` only lists and puts; it has no delete.
Cloudflare shows the token's S3 credentials once: an Access Key ID and a Secret
Access Key. The S3 endpoint is `https://<account id>.r2.cloudflarestorage.com`.

## Publishing

Keep the token's keys in a file outside the repo that only you can read,
`~/.config/ciao-sun/r2.env` (`chmod 600`), never in the shell history:

```
AWS_ACCESS_KEY_ID=…            # the token's Access Key ID
AWS_SECRET_ACCESS_KEY=…        # the token's Secret Access Key
CIAO_SUN_R2_ENDPOINT=https://<account id>.r2.cloudflarestorage.com
CIAO_SUN_DATA_BUCKET=ciao-sun-data
CIAO_SUN_INPUTS_BUCKET=ciao-sun-inputs
```

and load it for the one command:

```
(set -a; . ~/.config/ciao-sun/r2.env; set +a
 uv run ciao-sun publish data/builds/f1/20261111b --inputs data/inputs)
```

`--inputs` must be the inputs directory the build read. `publish` checks the
OSM extract and Terrain 50 zip there against the SHA-256s in the build's
manifest, and refuses if `fetch` has replaced them since.

What is stored:

| Files | Stored as | Headers besides `Cache-Control` |
|---|---|---|
| `tiles/<window>/*.bin` | the gzip file on disk, byte for byte | `Content-Type: application/octet-stream`, no `Content-Encoding` |
| `basemap/{z}/{x}/{y}.mvt` | gzipped on upload | `Content-Type: application/vnd.mapbox-vector-tile`, `Content-Encoding: gzip` |
| `manifest.json`, other `*.json` | as on disk | `Content-Type: application/json` |

Every data object has `Cache-Control: public, max-age=31536000, immutable`.

### A build is published once

- If either bucket already holds any object under `f<format>/<build>/`,
  `publish` uploads nothing. A fix is a new build with a new build id.
- `manifest.json` is uploaded last. A prefix with a manifest is a whole build;
  a prefix without one is an interrupted publish that no app can pin.
- `--resume` finishes an interrupted publish of the same build directory. It
  uploads only the missing objects and never replaces one. It is refused once
  the manifest is there, or if the prefix holds a key the build does not have.
- Nothing is deleted, by `publish` or by hand, in Stage 1: a cached app may
  still pin any published build.

### After the first publish, check by hand

```
curl -sI -H 'Origin: https://edbarker.dev' <dataBase>/f1/<build>/manifest.json
curl -sI -H 'Accept-Encoding: gzip' <dataBase>/f1/<build>/basemap/10/<x>/<y>.mvt
curl -sI <dataBase>/f1/<build>/tiles/morning/<grid ref>.bin
```

Expect `access-control-allow-origin: https://edbarker.dev` and the immutable
`cache-control` on the first; `content-encoding: gzip` on the second; and no
`content-encoding` on the third, with a body that starts with the gzip magic
bytes `1f 8b`.
