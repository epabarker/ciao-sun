# How far must Horizon profiles reach when the sun is near 0°?

Research for [How far must Horizon profiles reach when the sun is near 0°?](https://github.com/epabarker/daylight-viewing/issues/13). Checked 2026-11-09.

Labels:

- **[measured]**: computed here, by the scripts in this folder, on the data named.
- **[verified]**: I ran the request shown, from this machine, on 2026-11-09.
- **[metadata]**: stated in an official page or record, but not tested end to end.
- **[secondary]**: from a catalogue record or a third-party summary; the primary source still needs checking.

## Answer

1. **Reach.** A ray that stops at 3 km is too short for open views.
   - **Bristol:** reach 30 km and no open-view Horizon profile is off by more than 0.1°. At 50 km nothing is missed at all. **[measured]**
   - **Stage 2/3 (GB):** reach 100 km. That gets 99.99% of low-horizon Candidate–azimuth pairs to within 0.1°. **[measured]**
2. **Data split.** Keep the 1 m DSM out to 3 km for the near field. Use **OS Terrain 50** beyond that.
   - The split is sound: Terrain 50 gives the same far horizon as EA LIDAR to within about 0.02° (90th percentile). **[measured]**
   - What Terrain 50 lacks is buildings and trees ("surface clutter"). That adds about 0.05–0.15° between 3 and 10 km, and almost nothing beyond 10 km. **[measured]**
   - Moving that clutter band onto the DSM (1 m DSM to 10 km) is a small refinement, not a requirement.
3. **Why Terrain 50.** It covers all of GB in a single 162 MB zip, under the OGL. It uses the same grid as the EA tiles (EPSG:27700) with heights in metres above Ordnance Datum Newlyn (ODN), and needs no key. It does not cover Northern Ireland.
4. **Bristol impact.** Leave-by times are wrong. The spots shown change a lot, but the sun at those spots barely does.
   - **Which mornings.** The effect only appears on mornings when the Morning window starts at Nominal sunrise. For a 07:00 Wake time that is 156 days a year: 10 Nov–27 Feb and 25 Sep–9 Nov.
   - **First-sun times.** The 3 km model puts first sun (and so leave-by) at the top 5 spots **3.0 min early on average, and up to 6 min**. Sun minutes are overstated by the same amount. If the sun only counts once it is above 0° (`el > 0`, as the prototype does), the error is the 3.0 min above. If it counts once it clears the Horizon profile, even when that is below 0°, the error is **4.9 min, up to 11 min**.
   - **Ranking.** Which spots are shown changes a lot: the 3 km #1 differs from the true #1 on 134 of those 156 days, and on average only 1.5 of the top 5 match. But the sun at the 3 km #1 is nearly as good: on average 1.2 weighted Sun minutes less than the true best, and at most 3. That is about 1.7% of its weighted Sun minutes. This is mostly reshuffling among near-ties. The walk-time tie-break here is only a proxy, so treat the overlap figures as indicative.
   - **The ticket's Candidate on 10 Nov.** First sun moves from **07:22 to 07:26**. The ridge that blocks it is Lansdown, above Bath: 14.7 km away, 234 m, +0.59°.
5. **Precision limit.** 0.1° is a modelling target, not a real-world accuracy. Day-to-day refraction near the horizon scatters by about 0.2° (1 SD), which is about ±1.5 min of first sun in Bristol.
6. **A separate bug found on the way.** `src/` and the prototype pass pvlib's true azimuth to a ray caster that expects grid azimuth. That is a 0.47° error at Bristol and about 4° in west Scotland. At Bristol it moves first sun at top spots by up to 10 min (0.3 min on average). **[measured]** See Caveats.

## 1. How far must the ray reach? (Bristol)

**Setup.** **[measured]** `profiles.py` builds Horizon profiles for the open-ground Candidates near home:

- **Candidates:** 15,990, on a 20 m grid within 1.8 km of home, kept where DSM − DTM ≤ 1 m (as in the prototype). The ticket's Candidate (51.472184, −2.603139) is included.
- **Azimuths:** 45–165° true, every 0.5°.
- **Near field:** the prototype's own geometry, `ray_samples(3000)` on the EA 1 m DSM.
- **Far field:** 3–200 km on Terrain 50 (bilinear), plus 3–25 km on EA LIDAR wherever we have it.
- **Truth:** the maximum of the near field and the far field (LIDAR DSM to 25 km, then Terrain 50 to 200 km).

**Missed horizon by reach.** The table counts open views only, meaning a 3 km horizon below 2° (312,749 Candidate–azimuth pairs). Source: `results/reach.csv`.

| Reach | Share of open-view pairs > 0.1° below truth | 99th percentile shortfall | Largest shortfall |
|---|---|---|---|
| 3 km (prototype) | 21% | 1.09° | 2.05° |
| 10 km | 14% | 0.39° | 0.69° |
| 15 km | 7.7% | 0.24° | 0.48° |
| 20 km | 0.97% | 0.10° | 0.29° |
| 25 km | 0.06% | 0.00° | 0.26° |
| 30 km | 0 | 0.00° | 0.096° |
| 50 km+ | 0 | 0 | 0 |

**What sets the far horizon.** The far field alone gives a horizon of **+0.2° to +0.55°** (median over Candidates) on every azimuth. It is set by terrain 10–20 km away (`results/far_by_sector.csv`):

- **105–125°, the November sun:** Lansdown and the hills above Bath, at about +0.4° to +0.6°.
- **Elsewhere:** higher ground 15–20 km away. Toward 45–95° that is probably the Cotswold edge; I only checked the place name for Lansdown.

Its minimum over all 15,990 Candidates and azimuths is +0.06°. So under the prototype's `el > 0` rule, no Candidate near home has a clear 0° horizon. The first 2–4 minutes after the sun reaches 0° are always behind hills.

**Analytic check.** Terrain at distance d rises above 0° only if it stands higher than the observer by d²/2R_eff, where R_eff = 1.13 × 6,371 km.

- For an observer at about 75 m, and the highest ground in this sector at about 300 m, that gives d ≤ √(2 · 7.2e6 · 225) ≈ **57 km**.
- This matches the measured cut-off. Nothing beyond about 60 km can matter under `el > 0`, and nothing beyond 30 km did.

**Does the rule matter?** **[measured]** The cut-off is the same under both visibility rules:

- **The prototype's rule (`el > 0 && el > horizon`):** far terrain only matters where it lifts the horizon above max(0, near).
- **The glossary's rule (sun above the Horizon profile, even below 0°):** far terrain matters wherever it beats a negative near horizon.

The far field is always above 0° here, so the cut-off is the same. The glossary's rule just shows a bigger effect, because the 3 km model also lets the sun appear "through" a negative horizon in the first minute after sunrise.

## 2. Far-field data options

| Dataset | Resolution and type | Licence | CRS and heights | Programmatic access | Size |
|---|---|---|---|---|---|
| **OS Terrain 50** (recommended) | 50 m grid, DTM ("removed all protruding features (such as buildings and trees)") **[metadata]** | OGL v3 **[verified]** | EPSG:27700, ODN (EPSG:5701) **[metadata]** | OS Downloads API, no key **[verified]** | 161.7 MB zip for all of GB **[verified]**. That unpacks to 2,858 10 km tiles, 625 MB as ASCII; I store it as a 728 MB int16 grid |
| **EA LIDAR Composite DTM/DSM, 2 m** | 2 m, DTM and last-return DSM | OGL v3 (see [lidar-access](https://github.com/epabarker/daylight-viewing/blob/research/lidar-access/research/lidar-access.md)) | EPSG:27700 | `/tiles/collections/survey/{product}/2022/2/{TILE}` **[verified]** | 15–22 MB per 5 km tile, per product **[verified]** |
| **EA LIDAR Composite, 1 m** | 1 m | OGL v3 | EPSG:27700 | Same, `/1/` | About 50 MB per tile per product. A 50 km radius is about 300 tiles ≈ 15 GB per product: too big for far field |
| **Copernicus GLO-30** | 30 m DSM (includes buildings and vegetation) | Free Copernicus DEM licence, attribution required **[metadata]** | Geographic lat/lon grid (not BNG), so it would need reprojecting and a height-datum shift; exact datum not checked **[secondary]** | Public S3 bucket `copernicus-dem-30m`, 1° COG tiles **[verified: HTTP 200]** | Not downloaded |
| **OSNI Open Data 50 m DTM** (Northern Ireland) | 50 m DTM | OGL / LPS OGD licence (listings differ) **[secondary]** | Probably Irish Grid, not checked | ArcGIS service only; no bulk file found **[secondary]** | Not downloaded |

**Terrain 50 against EA LIDAR.** **[measured]** I compared Terrain 50 with the six local 1 m DTM tiles, block-averaged to 50 m (60,000 cells):

- **Agreement:** bias −0.07 m, RMSE 1.25 m, 95th percentile |difference| 2.0 m.
- **Registration:** shifting Terrain 50 by half a cell roughly doubles the RMSE. So its `xllcorner` grid is registered as cell centres at +25 m, and the mosaic is correct (`validate_terr50.py`).

**Is a near 1 m DSM + far coarse DTM split sound?** **[measured]** I compared the far horizon from three sources over 3–25 km (`results/clutter.csv`). The comparison uses only distance bands where both the EA DSM and the EA DTM exist:

- the local 1 m tiles, and
- the 2 m tiles I fetched over E 365–375 km.

| Band | EA DTM − Terrain 50 (median / p90) | EA DSM − EA DTM, i.e. clutter (median / p90) |
|---|---|---|
| 3–5 km | 0.004° / 0.018° | 0.072° / 0.157° |
| 5–7 km | 0.003° / 0.011° | 0.054° / 0.100° |
| 7–10 km | 0.002° / 0.009° | 0.024° / 0.061° |
| 10–15 km | 0.001° / 0.005° | 0.000° / 0.023° |
| 15–20 km | 0.001° / 0.005° | 0.000° / 0.010° |

What the table shows:

- **Resolution doesn't matter beyond 3 km.** 50 m bare earth gives the same terrain horizon as LIDAR.
- **Clutter matters out to about 10 km.** Buildings and trees at 3–10 km add 0.02–0.16°.
- **Little of that reaches the final horizon.** It changes the final Horizon profile by more than 0.1° on only 1% of open-view pairs, because the near field or the 10–20 km hills usually dominate. In first-sun terms, see §3: DSM to 10 km is 0.18 min mean error, Terrain 50 alone 0.19 min.

## 3. Bristol impact on first sun, Sun minutes and ranking

**Method.** **[measured]** `analyse.py` follows the prototype's logic:

- **Window:** Wake time 07:00. The Morning window runs from the later of Wake and Nominal sunrise to Wake + 180 min.
- **Weighting:** full weight to Wake + 60 min, then a linear taper.
- **Ranking:** by rounded weighted Sun minutes, with a 200 m de-dupe.
- **Sun track:** pvlib apparent elevation at home, at **1-minute** steps, for 365 days from 2026-11-10.

Each profile variant is compared against the truth profile from §1. Results are in `results/sun_season_summary.csv`, with key dates in `results/sun_dates.csv` and every day in `results/sun_by_day.csv`.

**What the 3 km model gets wrong.** The table covers the 156 days when the Morning window starts at Nominal sunrise. Its columns describe that model's own top 5:

- **First sun too early:** how much too early its first-sun time is (mean, and the worst day).
- **Regret:** how many weighted Sun minutes its #1 spot loses against the true #1.

| Profile | First sun too early (gate rule) | First sun too early (glossary rule) | Days #1 differs from truth (gate) | Regret, mean / worst (gate) | Top-5 overlap with truth (gate) |
|---|---|---|---|---|---|
| 3 km (prototype) | 3.0 min / 6 min | 4.9 min / 11 min | 134 | 1.2 / 3.0 | 1.5 of 5 |
| 3 km, quantised to 0.5° as the fixture ships | 3.1 min / 6 min | 4.9 min / 11 min | 131 | 1.2 / 3.0 | 1.4 |
| + Terrain 50 to 10 km | 2.7 min / 6 min | 3.5 min / 7 min | 134 | 0.9 / 3.0 | 1.5 |
| + Terrain 50 to 20 km | 0.6 min / 2 min | 0.8 min / 3 min | 73 | 0.16 / 1.2 | 3.3 |
| + Terrain 50 to 30 or 50 km | 0.19 min / 1 min | 0.19 min / 1 min | 43 | 0.15 / 1.0 | 4.0 |
| + DSM to 10 km, then Terrain 50 to 50 km | 0.18 min / 1 min | 0.18 min / 1 min | 38 | 0.12 / 1.0 | 4.1 |

How to read this:

- **The #1 spot changes, but its sun barely does.** The #1 spot changes on most sunrise-start days, mostly between near-ties under rounded weighted Sun minutes plus the walk tie-break. The 3 km pick's true weighted Sun minutes average 98.3% of the best. Walk time here is a proxy (1.3 × straight line, no OSM, de-dupe without names), so the overlap figures are indicative.
- **The real cost is leave-by.** The person is sent out about 3–5 min too early, and each top spot's Sun minutes are overstated by the same amount.
- **The other 209 days are unaffected.** When the sun is already up at Wake time, the top-5 error averages 0.05 min.
- **Most Candidates don't move at all.** On a given sunrise-start morning, only about 5% of Candidates change first-sun time; the rest are blocked by nearby buildings or trees. The ones that move are exactly the open, east-facing spots that rank highest.
- **Plausibility check.** The sun climbs at about 0.117°/min on 10 Nov and 0.103°/min on 21 Dec. So a +0.45° far-field lift should delay first sun by about 4 min, which matches what was measured.

**The ticket's Candidate** (`results/ticket_candidate.csv`):

| Date | 3 km first sun (gate / glossary rule) | Truth first sun | Sun minutes |
|---|---|---|---|
| 10 Nov 2026 (Nominal sunrise 07:20) | 07:22 / 07:20 | 07:26 | 158 → 154 |
| 1 Feb 2027 (Nominal sunrise 07:49) | 07:51 / 07:49 | 07:55 | 129 → 125 |
| 21 Dec 2026 (Nominal sunrise 08:14) | 08:29 | 08:29 (blocked nearby until then) | 36 → 36 |

- **The ridge.** At azimuths 113–116° the far horizon peaks at **+0.59°, 14.5–14.7 km away, at 234–236 m (51.415, −2.416): Lansdown, north-west of Bath**. This confirms the ticket's suspicion: the Bath hills, at about 13 km and +0.5°.
- **It reproduces the prototype.** The prototype's 07:22 comes back exactly from the 3 km profile under the `el > 0` gate. Without the gate it would be 07:20.

**The fixture's 0.5° quantisation** is a separate error, of the same size as the target.

- It changes first sun for about 40% of Candidates. **[measured]**
- On open views the angle error averages +0.005°, with SD 0.14° and a maximum of 0.25°. **[measured]** At 0.117°/min that is about ±1.2 min, typically. **[estimate]**
- It hardly changes the top-5 error (3.08 vs 3.01 min), because it is essentially unbiased.
- For a 0.1° target, store profiles at 0.1°. A uint8 at 0.1° spans 25.5°, for example −5° to +20.5° with everything above clipped, which is all low sun needs.
- The prototype also uses 2-minute sun steps, which add up to 1 min of first-sun granularity.

## 4. Generalising to Stage 2/3 terrain

**Setup.** **[measured]** `gb_reach.py`:

- **Observers:** 2,261 on a 10 km lattice over GB land, at ground + 1.6 m.
- **Azimuths:** 35–165° (northern summer sunrise is about 40°).
- **Rays:** 50 m to 250 km, Terrain 50 only.
- **Conservative by construction:** a bare-earth near field is always lower than a real street with buildings, so the far field wins more often than it would with a DSM.

For each pair, "required reach" is the shortest R whose horizon is within 0.1° of the 250 km horizon. Full results are in `results/gb_reach.csv`, and per-point worst cases in `results/gb_points.csv`.

| Pairs with a final horizon of 0–2° | Points | Median | p90 | p99 | p99.9 | Share needing > 50 km | > 100 km |
|---|---|---|---|---|---|---|---|
| All GB | 2,261 | 3 km | 20 km | 50 km | 100 km | 0.56% | 0.006% |
| Local relief < 100 m | 611 | 3 km | 10 km | 50 km | 100 km | 0.58% | 0.009% |
| Relief ≥ 300 m (uplands) | 749 | 10 km | 30 km | 50 km | 100 km | 0.75% | 0.003% |
| North of N 560 km (Scotland, N England) | 828 | 5 km | 30 km | 75 km | 100 km | 1.3% | 0.02% |
| South of N 560 km | 1,433 | 3 km | 15 km | 50 km | 75 km | 0.31% | 0 |

**Negative horizons.** Allowing horizons down to −∞, as the glossary rule does (horizon < 2°), the p99 reach is 75 km and 0.09% of pairs need more than 100 km. These are hilltops and islands looking at distant mountains, for example the Outer Hebrides seeing the mainland 100–150 km away.

**General bound.** Under the `el > 0` rule, terrain can only rise above 0° within d ≤ √(2 · R_eff · ΔH), where ΔH is how much higher the highest ground in that direction stands than the observer. That bound is:

- about **57 km** for Bristol (ΔH ≈ 225 m), and
- about **136 km** in the worst case for GB (ΔH ≈ 1,300 m: a sea-level observer looking at the Cairngorms or Ben Nevis).

**Recommendation for Stage 2/3:**

- **Far field:** Terrain 50 to **100 km**.
- **Larger cap:** optionally lift it to the per-site bound √(2·R_eff·ΔH) for coastal and Highland Candidates.
- **Northern Ireland:** needs another source. OSNI 50 m DTM is not verified. Copernicus GLO-30 is a DSM on EPSG:4326 with EGM2008 heights.

## Caveats and precision limits

- **Atmospheric refraction is the real limit.**
  - Sunrise/sunset timings in Edmonton (244 sunrises) gave a standard deviation of **0.175°** in horizon refraction, with a range of 0.40–2.08° **[secondary: Peterson, Lozowski, Hube & Sampson 2003, PASP 115:1256, abstract via catalogue record]**.
  - Young (SDSU) puts the variations at "a few tenths of a degree ordinarily, and sometimes ... a few degrees" **[metadata]**.
  - At Bristol's 0.10–0.12°/min climb, 0.175° is ±1.5 min. So first-sun times are good to about ±2 min at best, whatever the reach.
- **Terrestrial refraction.** The far-field rays use k = 0.13 (`R_EFF = 1.13 R`). Dawn temperature inversions raise k. Going from k = 0 to k = 0.5 moves a 15 km ridge by about 0.03°, and a 50 km ridge by about 0.11°.
- **Which part of the sun counts.** The prototype and this analysis use the apparent centre. "First sliver" (upper limb, +0.27°) would be about 2.3 min earlier, which is the same size as the far-field effect.
  - pvlib applies refraction only above −0.833°. So at the Nominal sunrise minute, the apparent elevation jumps to about −0.21°. That is why the glossary rule can show sun at the sunrise minute.
- **Grid vs true azimuth.** **[measured]**
  - `sunspot.horizon.horizon_angle` takes grid azimuth, and `search.py` passes pvlib's true azimuth straight in. The answer-screen fixture does the same.
  - At Bristol, grid azimuth = true + 0.47° (verified with pyproj). In the west of Scotland it is about 3.8° (Lewis) to 4.6° (at −7.5°).
  - This analysis corrects for it; `src/` does not.
  - **Effect at Bristol, measured** (`truth_no_convergence_fix` in `results/sun_season_summary.csv`, run on the full-reach profile). On sunrise-start days it:
    - changes first sun for 76% of Candidates;
    - shifts first sun at the top 5 by 0.3 min on average, and up to 10 min;
    - costs the #1 spot 0.8 weighted Sun minutes on average, and up to 10.
  - That is a smaller mean error than the far field, but a comparable worst case. It needs fixing before Stage 1 is trusted, not just before Stage 2.
- **What the clutter test covered.** Clutter was only tested where both EA DSM and DTM were fetched: the local tiles plus E 365–375 km.
  - The EA tile endpoint returned **HTTP 403 from "Microsoft-Azure-Application-Gateway/v2" after about 23 back-to-back requests**. It cleared within about 10 min. This contradicts "no throttling seen" in the earlier lidar-access research.
  - The missing tiles: the DTM for the ST75xx tiles and ST80xx, and the DSM for ST7575 and ST80xx. The analysis used Terrain 50 there.
- **Simplifications against the prototype.** Candidates are open ground within 1.8 km of home, with no OSM walk filter. Walk time is 1.3 × straight-line distance at 5 km/h. The de-dupe ignores place names.
- **Terrain 50 is bare earth** and was last revised against imagery on varying dates. Woodland on far ridges adds at most about 0.02° (p90) beyond 10 km in the one sector tested.

## Implementation notes (for whoever builds it)

- **Cost.** Far-field rays on Terrain 50 are cheap. With 25/50/200 m steps from 3 to 200 km, about 1,500 samples per ray, all 15,990 Candidates × 241 azimuths ran in about 3 min on 8 processes, including two LIDAR variants. A cap at 50 km needs about 780 samples per ray.
- **Sharing work.** The far field changes slowly across neighbouring Candidates, but it depends on observer height (Δz/d). Any reuse across Candidates must adjust for each Candidate's height. I did not measure this.
- **Storage.** Precompute a GB Terrain 50 grid once: 728 MB as int16 decimetres, or less as a compressed COG. The tool reads only windows of it.

## Reproduce

All data goes outside git, in the main checkout's gitignored `data/farfield/`.

```sh
bash fetch_farfield.sh /path/to/main/data/farfield   # Terrain 50 (161.7 MB) + up to 40 EA 2 m tiles (~15-22 MB each, ~0.8 GB if none are throttled)
# unzip terr50_gagg_gb.zip, then each inner data/*/*.zip, into data/farfield/terr50/asc
# and unzip the EA *.tif into data/farfield/ea2m/tif/{dsm,dtm}
uv run python -I build_terr50.py data/farfield/terr50/asc data/farfield/terr50/gb_terr50_dm.npy
uv run python -I validate_terr50.py
uv run python -I profiles.py /tmp/prof20.npz 20      # ~3 min
uv run python -I analyse.py /tmp/prof20.npz results  # ~2 min
uv run python -I gb_reach.py results                 # ~10 s
```

What was actually downloaded:

- Terrain 50: 161,706,566 B (MD5 `feba9008db55cdcb5c5e5b7896e3428b`, which matches the API's listed value).
- EA 2 m: 23 tile zips, 458 MB (13 DSM, 10 DTM).
- One 22 MB re-test, discarded.
- **Total about 642 MB.**

## Sources

- **OS Downloads API, Terrain 50** (product record, downloads list, sizes, MD5): https://api.os.uk/downloads/v1/products/Terrain50 and https://api.os.uk/downloads/v1/products/Terrain50/downloads
- **OS Terrain 50 technical specification:** https://docs.os.uk/os-downloads/products/land-and-terrain-portfolio/os-terrain-50/os-terrain-50-technical-specification
  - Metadata page: …/os-terrain-50-technical-specification/metadata (BNG EPSG:27700, ODN EPSG:5701).
- **OS OpenData licence:** https://www.ordnancesurvey.co.uk/opendata/licence returns a 301 to OGL v3, https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/.
  - The `licence.txt` in the zip reads "© Crown copyright and database right 2026". Attribution: "Contains OS data © Crown copyright and database right 2026".
- **EA LIDAR tiles API:** `https://environment.data.gov.uk/tiles/collections/survey/{lidar_composite_last_return_dsm|lidar_composite_dtm}/2022/2/{TILE}`. Prior research: [lidar-access](https://github.com/epabarker/daylight-viewing/blob/research/lidar-access/research/lidar-access.md).
- **Copernicus DEM on AWS:** https://registry.opendata.aws/copernicus-dem/ (DSM, bucket `copernicus-dem-30m`, free licence).
- **OSNI Open Data 50 m DTM:** https://www.data.gov.uk/dataset/c5b734b1-b6f4-46a2-bc82-3fb9525db04a/osni-open-data-50m-dtm1 **[secondary]**
- **A. T. Young, "Why we can't predict sunset times exactly":** https://aty.sdsu.edu/explain/sunset_time.html
- **Peterson, Lozowski, Hube & Sampson (2003)**, "Variability in the Astronomical Refraction of the Rising and Setting Sun", *PASP* 115:1256–1261 **[secondary: abstract via catalogue]**
- **Answer-screen prototype** (fixture geometry, visibility rule, ranking): branch `prototype/answer-screen`, `prototype/answer-screen/{build_fixture.py,index.html}`.
