# Can LIDAR DSM/DTM be fetched programmatically?

Research for [#4](https://github.com/epabarker/daylight-viewing/issues/4) (map: #2). Checked 2026-11-09.

Labels used below:

- **[verified]** means I ran the exact request shown, from this machine, on 2026-11-09.
- **[metadata]** means the claim is stated in an official metadata record or API response, but I did not test it end to end.
- **[secondary]** means the claim comes from search summaries or third-party pages, and the primary source still needs checking.

## Answer

**Yes, for England.** Two routes work, both anonymous: no key, no login, no cookies.

1. **Whole 5 km tiles over HTTP (undocumented but used by the portal).** These are the same zips the portal produces. A tile ID like `ST5575` is exactly what `sunspot.tiles.bng_to_tile_code` already outputs. **[verified]**
2. **OGC WCS 2.0.1 (documented: linked from the dataset page).** Use it to cut out any bounding box as a float32 GeoTIFF. The values are bit-identical to the tile zips. **[verified]**

Survey-date metadata is also available programmatically, through an OGC API Features endpoint and a GeoPackage shipped inside every tile zip. **[verified]**

The licence is OGL v3. It allows automated download and public re-serving of derived products, provided you include the attribution statement. **[metadata]**

No rate limits are published, and I saw no rate-limit headers.

**Wales**, **Scotland** and (partly) **Northern Ireland** all publish OGL LiDAR as plain files on public cloud storage, which is easy to script. Wales and Scotland use EPSG:27700 GeoTIFFs. Scotland is 50 cm for most recent phases. Northern Ireland coverage is patchy and older.

## England (Environment Agency, Defra Data Services Platform)

### Route 1: tile zips (recommended for precompute)

**Discovery.** POST a GeoJSON polygon in WGS84 to the catalog search. It returns every product, year and resolution available for the 5 km tiles that intersect it. **[verified]**

```
curl -s -X POST -H "Content-Type: application/geo+json" \
  -d '{"type":"Polygon","coordinates":[[[-2.62,51.46],[-2.58,51.46],[-2.58,51.48],[-2.62,51.48],[-2.62,51.46]]]}' \
  https://environment.data.gov.uk/backend/catalog/api/tiles/collections/survey/search
```

The response has the shape `{"count":59,"results":[{"product":{"id":"lidar_composite_last_return_dsm",...},"year":{"id":"2022"},"resolution":{"id":"1"},"tile":{"id":"ST5570","label":"ST57se"},"uri":"https://environment.data.gov.uk/tiles/collections/survey/lidar_composite_last_return_dsm/2022/1/ST5570"}, ...]}`.

For the Bristol box above it lists tiles ST57ne and ST57se, with these products:

| Product | Years and resolutions listed |
|---|---|
| `lidar_composite_dtm` | 2022, 1 m and 2 m |
| `lidar_composite_last_return_dsm` | 2022, 1 m and 2 m |
| `lidar_composite_first_return_dsm` | 2022, 1 m and 2 m |
| `lidar_tiles_dsm` / `lidar_tiles_dtm` (per-survey, not composite) | 2003 to 2021 |
| `national_lidar_programme_*` (DSM, DTM, first-return DSM, VOM, intensity, point cloud) | 2018, 2019 |
| `lidar_point_cloud` | up to **2024**, newer than the 2022 composite |

**Download.** The URI pattern is:

```
https://environment.data.gov.uk/tiles/collections/survey/{product}/{year}/{resolution}/{tile}
```

Here `{tile}` is the full numeric form (`ST5575`), not the quadrant label (`ST57ne`). **[verified]**

```
curl -fL -o ST57ne_dsm.zip https://environment.data.gov.uk/tiles/collections/survey/lidar_composite_last_return_dsm/2022/1/ST5575
curl -fL -o ST57ne_dtm.zip https://environment.data.gov.uk/tiles/collections/survey/lidar_composite_dtm/2022/1/ST5575
```

What these requests return:

- **Response headers.** HTTP 200, `content-type: application/zip`, `content-disposition: attachment; filename="lidar_composite_last_return_dsm-2022-1-ST57ne.zip"`.
- **Size and speed.** The DSM zip is 52.7 MB. The DTM zip is 47.6 MB and took 4.5 s.
- **`HEAD` does not work.** It returns 405, so use GET.
- **`Range` is ignored.** The whole file always comes back.
- **Zip contents:**
  - `ST57ne_LZ_DSM_1m.tif` (5000×5000, float32, LZW, EPSG:27700, nodata −3.4028235e38)
  - `.tfw`
  - `.tif.xml`
  - `.aux.xml`
  - `ST57ne_LZ_DSM_1m_Metadata.gpkg`
- **The product slug matters.** `lidar_composite_last_return_dsm` is the "LIDAR Composite DSM" that the README describes (last return, `LZ_DSM`). `lidar_composite_first_return_dsm` is the separate `FZ_DSM` product.

**Stability caveat.** This catalog/tiles API is not documented anywhere official. It is the backend that the portal's own "Download the Survey Data" page calls. Third-party tools describe it as reverse-engineered, and the QGIS "LIDAR Downloader UK" plugin also uses the EA services. It works anonymously today; earlier third-party scripts mention a subscription key, but none was needed. Treat it as liable to change, and put it behind one small fetch function.

### Route 2: WCS (documented)

The DSP dataset page for *LIDAR Composite Digital Surface Model (DSM) - 1m* (`https://environment.data.gov.uk/dataset/9ba4d5ac-d596-445a-9056-dae3ddec0178`) links to these services:

- DSM WCS: `https://environment.data.gov.uk/spatialdata/lidar-composite-digital-surface-model-last-return-dsm-1m/wcs`
  - Coverage `9ba4d5ac-d596-445a-9056-dae3ddec0178__Lidar_Composite_Elevation_LZ_DSM_1m`
- DTM WCS: `https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs`
  - Coverage `13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m`
- WMS: matching `/wms` endpoints for display.

Both are GeoServer ImageMosaic/pyramid coverages. They are native 1 m on EPSG:27700, with an envelope of E 80000–656000, N 4000–665000. GetCapabilities reports `Fees: NONE` and `AccessConstraints: NONE`. **[verified]**

```
curl -o dsm.tif "https://environment.data.gov.uk/spatialdata/lidar-composite-digital-surface-model-last-return-dsm-1m/wcs?service=WCS&version=2.0.1&request=GetCoverage&coverageId=9ba4d5ac-d596-445a-9056-dae3ddec0178__Lidar_Composite_Elevation_LZ_DSM_1m&subset=E(357000,357200)&subset=N(177000,177200)&format=image/tiff"
```

Results:

- **Small subset.** Returns a 200×200 float32 GeoTIFF (173 KB) with origin 357000/177200, a 1 m pixel and EPSG:27700. Values are 31.9 to 64.5 m. This window is **bit-identical** to the same window of `ST57ne_LZ_DSM_1m.tif` from Route 1 (max abs diff 0.0).
- **Whole tile.** A full 5 km square (`subset=E(355000,360000)&subset=N(175000,180000)`) returned HTTP 200 with 104.9 MB of uncompressed float32 in 14 s. That is the size of the complete 5000×5000 grid, so no server size cap was hit at this size.

WCS suits on-demand cut-outs of arbitrary areas, and it avoids zip handling. Its downside is that responses are uncompressed, about twice the size of the zips.

### Survey-date metadata

There are two programmatic sources. **[verified]**

**1. OGC API Features.** This is linked from the dataset page as "survey index files".

```
https://environment.data.gov.uk/spatialdata/survey-index-files/ogc/features/v1/collections/LIDAR_Composite_1m_Last_Return_DSM_2022_extents/items?f=json&bbox=-2.62,51.46,-2.58,51.48
```

It returns polygons with `sd_flown`, `ed_flown`, `year`, `resolution`, `polygon_id` and `filename`. For central Bristol there are 6 polygons, flown on 2018-04-19, 2019-01-17, 2019-01-23 and so on.

Collections also exist for:

- the composite DTM and first-return DSM, at 1 m and 2 m
- `LIDAR_DSM_Time_Stamped_Extents` and `LIDAR_DTM_Time_Stamped_Extents`; a bbox query on the DSM one returned a non-JSON response, which I didn't investigate
- the NLP and point-cloud catalogues

**2. The GeoPackage inside each tile zip.** In `*_Metadata.gpkg`, the table `lidar_used_in_merging_process` holds MULTIPOLYGONs with `SD_FLOWN`, `ED_FLOWN`, `RESOLUTION`, `SRVY_YEAR` and `POLYGON_ID`. For ST57ne it has 8 rows, flown 2018-04-19 to 2021-09-21.

This means the tool could show a per-location "surveyed on" date, which addresses the README's "survey dates vary" limitation.

### Licence

From the DSP dataset record (JSON embedded in the dataset page): **[metadata]**

- `"licence": {"text": "Open Government Licence", "url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"}`
- `"attributionStatement": "© Environment Agency copyright and/or database right 2022. All rights reserved."`
- `"useLimitationStatement": "There are no public access constraints to this data. Use of this data is subject to the licence identified."`
- `accrualPeriodicity: "annually"`. Coverage is about 99% of England.

OGL v3 lets you copy, publish, distribute and adapt the information, commercially or not, if you include the attribution statement. That covers both automated download and publicly re-serving derived products (horizon rasters, clear-window maps) from a public web tool.

### Rate limits

None are published on the dataset page or in GetCapabilities. Responses carried no `RateLimit`, `Retry-After` or `X-RateLimit` headers. I made about 10 requests and none were throttled.

That is an absence of evidence, not a guarantee. Don't invent a limit, but be polite: fetch serially, set a descriptive User-Agent, and cache.

### Dead ends and negatives

- **STAC:** no catalogue found for EA LIDAR.
- **ESRI ImageServer:** `https://environment.data.gov.uk/image/rest/services/SURVEY?f=json` returns `{"error":{"code":400,"message":"Invalid URL"}}`. The old ImageServer path is gone.
- **Old download portal:** the `DefraDataDownload/?Mode=survey` URL is still linked, but it is the interactive portal.
- **Catalog GET:** a GET on `.../backend/catalog/api/tiles/collections/survey` returns 404. Only the `/search` POST works.

### Volume estimate (estimate, not measured)

England has roughly 5,200 5 km tiles, and a DSM+DTM pair is about 100 MB zipped. That puts all of England at 1 m at around 0.5 TB.

Bristol, from the CLI's own tile list, is a handful of tiles, i.e. hundreds of MB.

## Wales (DataMapWales, Welsh Government LiDAR 2020–2023)

- **Coverage and resolution:** all of Wales at 1 m. The tile catalogue has 22,473 1 km tiles, from surveys in 2020–2023. **[verified]**
- **Programmatic access:** query the WFS tile catalogue, then download the GeoTIFF directly from Azure Blob storage. **[verified]**

  ```
  https://datamap.gov.wales/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typenames=geonode:welsh_government_lidar_tile_catalogue_2020_2023&outputFormat=application/json
  ```

  - Each feature has `british_gr` (for example `SH2281`) and the flight `date`, `start_time` and `end_time`.
  - `dsm_link` and `dtm_link` look like `dmwproductionblob.blob.core.windows.net/lidar-zips/2020-22/dsm/wg_del_1_222381_20200322dsm.tif`. **They have no scheme, so prefix `https://`.**
- **Tile format:** a 1 km DSM tile is 2.1 MB, float32, deflate-compressed, EPSG:27700, 1 m, nodata −9999. Values are in metres (32.9 to 77.2 m, with no scale or offset). It drops straight into `raster.py` alongside EA tiles. **[verified]**
- **Other routes:** whole-Wales COG mosaics are also listed. The DataMapWales WCS GetCapabilities exposes no LiDAR elevation coverages.
- **Licence:** OGL per the DataMapWales layer records. Copyright is listed as "None" or "Not applicable", and I found no specific attribution string for the WG 2020–23 data. **[secondary: confirm on the record before launch]**

## Scotland (Scottish Remote Sensing Portal)

- **Programmatic access:** a public, listable S3 bucket, `https://srsp-open-data.s3.eu-west-2.amazonaws.com/`. It needs no auth and supports standard S3 `list-type=2` listing. **[verified]**
- **Bucket layout:**
  - Prefixes under `lidar/`: `phase-1` to `phase-6`, `national-lidar-programme`, `coastal`, `hes`, `orkney-islands-council-23` and `outer-hebrides`.
  - The layout is `lidar/{survey}/{dsm|dtm|laz}/27700/gridded/{TILE}_{RES}_{DSM|DTM}_{SURVEY}.tif`, for example `NS16NE_50CM_DSM_PHASE3.tif` or `NG2004_50cm_DSM_ScotlandNationalLiDAR.tif`.
- **Resolution, from the filenames:** **[verified]**

  | Survey | Resolution |
  |---|---|
  | Phase 1 | 1 m |
  | Phase 2 | 1 m |
  | Phase 3 | 50 cm |
  | Phase 4 | 50 cm |
  | Phase 5 | 50 cm |
  | Phase 6 | 50 cm |
  | National LiDAR Programme | 50 cm |

- **Tile sizes vary.** Tile schemes vary between surveys, and files range from about 5 MB to 400 MB.
- **Coverage:** patchy. The phases are separate survey blocks; for example, Phase 1 covers 10 sites totalling 11,845 km², flown 2011–12. **[metadata]** The Scottish Land LiDAR Programme (Bluesky) is capturing 2025–2027 at 10 pts/m², with DSM/DTM GeoTIFFs. **[secondary]**
- **Licence:** OGL per the SpatialData.gov.scot records. **Attribution differs per phase.** Phase 1's is "Crown copyright Scottish Government, SEPA and Scottish Water (2012)". **[metadata]**
- **Older copies are gone.** The EA DSP's older "Scotland 1 m DSM/DTM" copies are no longer available.

## Northern Ireland

- **Source:** OpenDataNI "OSNI Open Data: River Basin LIDAR {2004, 2007–2010, 2012–2014} – DTMs and DSMs". **[metadata, via the data.gov.uk CKAN mirror]**

  ```
  https://ckan.publishing.service.gov.uk/api/action/package_search?q=river%20basin%20lidar
  ```

- **Licence:** `license_id: uk-ogl` (OGL).
- **Format:** one zip per survey area on Azure Blob, for example `https://opendatani.blob.core.windows.net/lpslidar/Newtownards_10_06_2008.zip`. That file is 237 MB per HEAD. **[verified]**
- **Coverage:** only about 14–17% of NI land area, all from 2004–2014. Files are 1 km tiles on a 1 m grid; Belfast's are 0.5 m ESRI ASCII grids. **[secondary]**
- **CRS: not checked.** NI data is normally on Irish Grid (EPSG:29902/29903) or ITM (EPSG:2157), not BNG, so `tiles.py`'s BNG scheme won't apply. **[unverified]**
- A 2021 NI 3D Coastal Survey also exists, covering the coastline only.
- **There is no open full-coverage NI DSM/DTM.**

## Implications for architecture

1. **No manual step is needed.** For England, a `sunspot fetch` command can turn `tile_codes_for_aoi` output into downloads with no new tile logic. The README's "cannot be scripted" claim is out of date.
2. **Precompute and cache; don't proxy.** All four sources are static files or stateless OGC services with no published fair-use terms. A phone web tool should fetch once into its own store, convert to COG (or precomputed horizon products), and serve from there. It should not forward each user request to EA's WCS.
3. **Use WCS for odd areas and tiles for bulk.** The two give identical pixels, so the choice is purely operational.
4. **Attribution must be per source.** EA, Welsh Government and each Scottish phase have different statements. Store the source with each tile and render the attribution dynamically. A single hard-coded EA string won't survive the move beyond England.
5. **Survey dates are available for every source.** For EA they come from Features or the GeoPackage, for Wales from tile attributes, and for Scotland from per-phase metadata. The "surveyed on" information can be shown per spot.
6. **Plan for mixed grids.**
   - **England:** 5 km tiles, 1 m.
   - **Wales:** 1 km tiles, 1 m.
   - **Scotland:** variable tiles, mostly 50 cm, with patchy coverage.
   - **NI:** probably a different CRS, with about 15% coverage.

   The raster layer should mosaic arbitrary EPSG:27700 GeoTIFFs at mixed resolution, which `raster.py` mostly already does via `rglob`. "UK" should be scoped as England + Wales + LiDAR-covered Scotland. NI isn't viable from open data today.
7. **Storage estimate.** At 1 m, England is about 0.5 TB of zips (estimate). That points to either precomputing only the areas users ask for, or doing a regional precompute on a VPS/batch job and serving derived low-volume products.

## Sources

**England**

- EA DSP dataset record: https://environment.data.gov.uk/dataset/9ba4d5ac-d596-445a-9056-dae3ddec0178
- EA WCS GetCapabilities (DSM): https://environment.data.gov.uk/spatialdata/lidar-composite-digital-surface-model-last-return-dsm-1m/wcs?service=WCS&request=GetCapabilities
- EA WCS GetCapabilities (DTM): https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs?service=WCS&request=GetCapabilities
- EA survey index OGC API Features: https://environment.data.gov.uk/spatialdata/survey-index-files/ogc/features/v1/collections
- EA catalog search (undocumented): `POST https://environment.data.gov.uk/backend/catalog/api/tiles/collections/survey/search`

**Licence**

- OGL v3: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/

**Wales**

- DataMapWales tile catalogue: https://datamap.gov.wales/layers/geonode:welsh_government_lidar_tile_catalogue_2020_2023

**Scotland**

- SRSP open-data bucket: https://srsp-open-data.s3.eu-west-2.amazonaws.com/?list-type=2&prefix=lidar/&delimiter=/
- Scotland Phase 1 DSM record: https://www.spatialdata.gov.scot/geonetwork/srv/api/records/92367c84-74d3-4426-8b0f-6f4a8096f593
- Scottish Land LiDAR Programme 2025: https://www.data.gov.uk/dataset/scottish-land-lidar-programme-2025-capture-dsm

**Northern Ireland**

- NI via data.gov.uk CKAN: https://ckan.publishing.service.gov.uk/api/action/package_search?q=river%20basin%20lidar
