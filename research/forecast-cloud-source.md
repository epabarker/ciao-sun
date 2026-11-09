# Which forecast source gives a morning cloud category for Bristol?

Research for [#11](https://github.com/epabarker/daylight-viewing/issues/11). Researched 2026-11-09.

**Question.** Which weather source can supply a three-level cloud category (clear / partly cloudy / overcast) for a Bristol Morning window (Wake time to Wake time + 3 h) for today and up to about a day ahead? Which one should we use, and how should its fields map to the three categories? Architecture is still open (a static site evaluating in the browser, or a VPS API), so for each source this records whether it needs a key and whether a browser can call it directly (CORS). Later stages cover all of the UK.

## Recommendation

**Use Open-Meteo's Forecast API with `models=ukmo_seamless`.** Read hourly `cloud_cover` (total cloud, %) and `daily=sunrise` in one keyless GET.

- It serves the Met Office's own UK model (UKV 2 km, hourly, about 2 days ahead) blended with UKMO Global 10 km. The data comes as JSON for any lat/lon in the UK. [1][2]
- **No API key**, and the response carries `access-control-allow-origin: *` (tested; see [Live tests](#live-tests-2026-11-09)). A static site can call it straight from the browser, and the free-tier limits are counted per IP, so each user spends their own quota. [3]
- The cost is a **non-commercial-only** free tier, plus **CC BY-SA 4.0 share-alike** on the Met Office data. Both are covered under [Licence and attribution](#licence-and-attribution-obligations).

The Met Office DataHub needs a key. Its free cap is per key, so every user would share it, which forces a server-side cache. MET Norway's terms forbid direct calls from browsers. Neither suits a browser-only build. Both are viable behind a VPS, and they are the fallbacks.

## Per-source comparison

| | **Open-Meteo (`ukmo_seamless`)** | **Met Office DataHub: Site-specific** (Global Spot / BPF) | **Met Office DataHub: Atmospheric models** (UKV 2 km gridded) | **Met Office UKV on AWS Open Data** | **MET Norway Locationforecast 2.0** |
|---|---|---|---|---|---|
| Cloud fields | `cloud_cover` (total %), `cloud_cover_low` (<3 km), `_mid` (3–8 km), `_high` (>8 km), `cloud_cover_2m` (fog) [1][4] | Global Spot hourly: no cloud-cover field found. A third-party client lists 17 hourly channels with none for cloud [9]; the official overview gives only the count, "18 single-level parameters" [7]. Community integrations reportedly read a `significantWeatherCode` (unverified). BPF: cloud included, per the AWS mirror ("Cloud" among 33 parameters) [10] | UKV total/low/medium/high cloud (Open-Meteo derives its fields from these) [1]. Map images include "total cloud cover" [8] | As UKV (NetCDF) [11] | `cloud_area_fraction` (total %), `_low` (<2 km), `_medium` (2–5 km), `_high` (>5 km), `fog_area_fraction` (complete.json only) [13] |
| Underlying model for Bristol | UKMO UKV 2 km + UKMO Global 10 km [1]. `best_match` also selects "UKMO UK 2 km & Global 10 km" for UK & Ireland [4] | Met Office post-processed site forecasts [7] | UKV 2 km [8] | UKV 2 km, 0.018° grid [11] | Probably ECMWF ~9 km. The docs list "rest of the world" as ECMWF and don't name the UK; this is an inference [13] |
| Temporal resolution | UKV hourly. Global: hourly, then 3-hourly after 54 h [1]. `minutely_15` outside Central Europe/N. America is "interpolated hourly data" [4] | Global Spot hourly to 48 h, 3-hourly to 168 h. BPF hourly 0–129 h [7] | Hourly | Hourly 0–54 h, then 3-hourly to 120 h [11] | 1 h in the short range, 6 h in the medium range [13] |
| Horizon (covers today + 1 day?) | UKV "2 days, updated every hour". Global 7 days, every 6 h [1]. **Yes** | Global Spot 48 h hourly [7]. **Yes** | Yes | Short runs 54 h, 6×/day; nowcast 12 h, 16×/day [11]. **Yes** | About 9 days (live response ran to +9 d). **Yes** |
| UK accuracy documented? | Not found. Open-Meteo publishes no UK cloud verification | Not found for cloud | Not found for cloud | Not found | Not found for the UK |
| Licence / attribution | API data CC BY 4.0, with a link "next to any location Open-Meteo data are displayed" [5]. **UK Met Office data CC BY-SA 4.0; "derived products … should also be redistributed under the same or a compatible licence"** [1][5] | Governed by "Weather DataHub Terms and Conditions" [8] (not read) | As left | "British Crown copyright … licensed under CC BY-SA" [11] | CC BY 4.0: "give appropriate credit, provide a link to the license, and indicate if changes were made" [12] |
| Free limits | Non-commercial only: <10,000 calls/day, 5,000/h, 600/min, counted "by IP addresses and application" [3]. Live headers: `X-RateLimit-Limit: 600`, window 60 s | Free: BPF "Up to 55 calls per day", one site. Global Spot "Up to 360 calls per day". Paid from £9/month [6]. Resets 00:00 UTC [8] | Data plans in GB [8] | Free, "unsupported", not for critical business use [11] | "Keep total traffic below 20 requests per second" per application. Must honour `Expires` and use `If-Modified-Since` [12] |
| API key | **None** (live request succeeded anonymously) | **Required.** Anonymous call gets `401 … "Missing Credentials"`. Key goes in the `apikey` header [14] | Required (registration + subscription) [8] | None (S3 bucket) | None, but an identifying `User-Agent` is required [12] |
| Browser-callable (CORS) | **Yes.** `access-control-allow-origin: *`; preflight OK for GET/POST | Technically yes: ACAO `*`, and the preflight allows the `apikey` header. But the key would ship in client code, and the free cap is per key, so it is shared by all users. **Needs a server** | No (bulk GRIB/NetCDF orders) | No (bulk NetCDF; needs processing) | **No, by the terms of service:** "Browsers and mobile apps should not contact the API directly, but instead use a local proxy" [12]. ACAO `*` is served, but the ToS rule governs. Browsers also can't set `User-Agent` |
| UK-wide | Yes (UKV domain is UK & Ireland) [1] | Yes (any lat/lon point) | Yes | Yes | Yes (global) |

Not considered: **Met Office DataPoint** was decommissioned on 1 December 2025, and Weather DataHub replaces it [15].

## Live tests (2026-11-09)

Run anonymously with `curl`, an `Origin: https://example.github.io` header and `User-Agent: sunspot-research/0.1`. No credentials or email address were sent.

- **Open-Meteo:** `GET https://api.open-meteo.com/v1/forecast?latitude=51.472&longitude=-2.604&hourly=cloud_cover&models=ukmo_seamless&timezone=Europe%2FLondon&forecast_days=2` returned `200`.
  - Headers: `access-control-allow-origin: *`, `X-RateLimit-Limit: 600.0`, `X-RateLimit-Window: 60`, and `access-control-expose-headers` including the rate-limit headers.
  - `OPTIONS` preflight: `200`, `access-control-allow-methods: GET, POST, OPTIONS`.
  - It snapped to grid cell **51.464, -2.615**, elevation 80 m.
  - `best_match` and `ukmo_seamless` returned identical 06:00–11:00 values for both days, which is consistent with UKMO being the model chosen for Bristol.
  - `daily=sunrise` gave 07:17 (9 Nov) and 07:19 (10 Nov). The `is_day` flag is also available hourly.
- **Met Office DataHub:** `GET https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/hourly?latitude=51.472&longitude=-2.604` with no key returned `401`, `{"code":"900902","message":"Missing Credentials", …'ApiKey : API_KEY'}`, with `access-control-allow-origin: *`.
  - Preflight `200`: `access-control-allow-headers: authorization,…,apikey,…`.
  - The base URL and `apikey` header match the Met Office's own sample code [14].
- **MET Norway:** `GET https://api.met.no/weatherapi/locationforecast/2.0/complete?lat=51.472&lon=-2.604` returned `200`.
  - Headers: `access-control-allow-origin: *`, plus an `expires` header about 30 min ahead.
  - Fields: `cloud_area_fraction`, `_low`, `_medium` and `_high` hourly, plus `next_1_hours.summary.symbol_code`.

## Mapping Open-Meteo `cloud_cover` to the three categories

### Anchors

- **Met Office okta conventions** [16]: 0 oktas = "complete absence of cloud"; 1 okta = "1 eighth or less, but not zero"; 7 oktas = "7 eighths or more, but not full cloud cover"; 8 oktas = "full cloud cover with no breaks". 1 okta = 12.5%.
- **US National Weather Service sky-condition terms** (opaque cloud) [17]: Clear/Sunny "1/8 or less"; Mostly Clear "1/8 to 3/8"; Partly Cloudy "3/8 to 5/8"; Mostly Cloudy "5/8 to 7/8"; Cloudy "7/8 to 8/8".
- **Open-Meteo's own WMO weather-code thresholds** on cloud cover [18] (cross-check): `0..<20` clear sky (code 0), `20..<50` mainly clear (1), `50..<80` partly cloudy (2), `80...` overcast (3).

### Proposed bands

Apply these to the window aggregate `C` (%) defined below:

| Category | Rule | Oktas | Rationale |
|---|---|---|---|
| **Clear** | `C < 25` | 0–2 (none to "few") | Kept strict, because "clear" both lowers the Duration target to 10 min and turns on the clear-sky bonus. A wrong "clear" under-doses, so the cost of error is asymmetric. 25% sits between NWS "Clear" (≤1/8) and the top of "Mostly Clear" (3/8), and close to Open-Meteo's 20% clear-sky cut. |
| **Partly cloudy** | `25 ≤ C < 80` | 2–6 | Covers NWS "Mostly Clear" (upper part), "Partly Cloudy" and the lower part of "Mostly Cloudy". |
| **Overcast** | `C ≥ 80` | ≈7–8 | 80% rounds to the nearest okta as 7 or 8 (7 oktas starts at 81.25%), which matches NWS "Cloudy 7/8 to 8/8" and Open-Meteo's own overcast code. It also keeps the category consistent with the `weather_code` icon the same API returns. |

**The 5–7 okta ("mostly cloudy", 62.5–87.5%) band is split at 80%.** 5–6 oktas count as partly cloudy (20 min); 7–8 oktas count as overcast (30 min). This boundary decides between 20 and 30 minutes on many UK mornings. If later evidence says broken cloud cuts the light dose more than this assumes, lower the overcast cut to 75% (6 oktas). It is one named constant, so change it there.

### Aggregating over the Morning window

1. Fetch `hourly=cloud_cover` and `daily=sunrise` with `models=ukmo_seamless&timezone=Europe/London&forecast_days=2`. That covers today and tomorrow, and the data starts at 00:00 local today, so a Wake time that has already passed still resolves.
2. Define the **daylight window** `[max(Wake, sunrise), Wake + 3 h]`. Cloud before sunrise doesn't affect the light dose. Example: in Bristol in November, sunrise is about 07:17, so a 06:00 Wake time leaves only 07:17–09:00. Whether the window should be clipped to sunrise like this is an app-level question for the map. The clipping is recommended here.
3. `cloud_cover` is an **instantaneous** value at each hour [4]. Linearly interpolate between hourly instants and take the **time-weighted mean** over the daylight window. This handles Wake times that aren't on the hour, such as 06:40. A simpler equivalent: average the hourly instants inside the window plus the interpolated values at its two ends. `minutely_15` adds nothing in the UK, because it is "interpolated hourly data" there [4].
4. If the daylight window is empty (Wake + 3 h is before sunrise, possible near the winter solstice for very early Wake times), use the interpolated value at sunrise and flag the result as "after window".
5. Classify `C` with the bands above.

The mean estimates the average fraction of sky covered, which roughly tracks the share of the window the sun is obscured. The mean was chosen over the minimum ("any clear hour counts") because a brief forecast clear spell is the least reliable part of a cloud forecast to time correctly. The mean was chosen over the maximum because one overcast hour shouldn't cancel a clear morning.

Example (live data, 10 Nov 2026, Wake 07:00): hourly values 07:00–10:00 were all 100% → `C = 100` → **overcast**.

## Licence and attribution obligations

The UKMO model is what serves Bristol (see the identical `best_match` / `ukmo_seamless` values above). So whichever model parameter is used:

1. Show the link `Weather data by Open-Meteo.com` → https://open-meteo.com/ "next to any location Open-Meteo data are displayed" [5].
2. Credit the source: **"Source: UK Met Office"** [1].
3. Link the licences: CC BY-SA 4.0 for the Met Office data [5], and CC BY 4.0 for Open-Meteo [5].
4. Say the data has been changed, e.g. "cloud cover categorised by sunspot" (CC BY / BY-SA requirement [5][12]).
5. **Share-alike:** the derived cloud category is an adaptation of CC BY-SA data, so "derived products … should also be redistributed under the same or a compatible licence" [1]. This applies to any category data sunspot redistributes. Whether it also reaches the app's other outputs is a question for a licence check, not settled here.
6. **Non-commercial:** the free API excludes "Websites or apps that have subscriptions or display advertisements" [3]. Adding either means a paid Open-Meteo plan, which uses a key. A key would have to sit behind a proxy, which changes the architecture.

## Weak points and gaps

- **No published UK cloud-forecast verification** was found for any candidate. Accuracy is the Met Office's UKV, but there are no numbers.
- **Total cloud counts thin cirrus.** NWS sky condition counts opaque cloud only [17]; total `cloud_cover` doesn't separate them. A high, thin veil could read as "overcast" while the sun is visible. `cloud_cover_low`/`_mid`/`_high` are available if this needs fixing later; no fix is proposed now.
- **Grid-cell forecast, not a point.** One 2 km UKV cell (51.464, -2.615) stands in for all of Bristol. That is fine for a city-level category, but timing errors of an hour or two in cloud breaks are normal.
- **Free tier has no SLA**, and its terms can change [3]. The app should cache the last good response and show its age.
- **Met Office DataHub details are unconfirmed:**
  - The full Global Spot hourly parameter list wasn't found in primary docs. The "no cloud field" claim rests on a third-party client [9] and is unverified.
  - `significantWeatherCode` value meanings weren't confirmed from a DataHub source.
  - The DataHub Terms and Conditions weren't read.
- **MET Norway's UK model** (ECMWF) is inferred, not stated [13].

## Sources

1. Open-Meteo, UK Met Office API docs: https://open-meteo.com/en/docs/ukmo-api
2. Open-Meteo, Forecast API docs (`models`, `ukmo_seamless`): https://open-meteo.com/en/docs
3. Open-Meteo, Terms (free-tier limits, non-commercial definition): https://open-meteo.com/en/terms
4. Open-Meteo, Forecast API docs (variable definitions, "Instant" validity, best_match regions, minutely_15 note): https://open-meteo.com/en/docs
5. Open-Meteo, Licence (CC BY 4.0, attribution link, data-source licences incl. UK Met Office CC BY-SA): https://open-meteo.com/en/licence
6. Met Office Weather DataHub, Site-specific pricing: https://datahub.metoffice.gov.uk/pricing/site-specific
7. Met Office Weather DataHub, Site-specific overview: https://datahub.metoffice.gov.uk/docs/f/category/site-specific/overview
8. Met Office Weather DataHub, home (products, daily limits, T&Cs): https://datahub.metoffice.gov.uk/
9. openHAB Met Office DataHub binding (third-party; hourly channel list): https://www.openhab.org/addons/bindings/metofficedatahub/
10. AWS Open Data, Met Office BPF Global spot probabilities: https://registry.opendata.aws/met-office-bpf-global-spot-probabilities
11. AWS Open Data, Met Office UK Deterministic (UKV) 2 km: https://registry.opendata.aws/met-office-uk-deterministic/
12. MET Norway API Terms of Service: https://api.met.no/doc/TermsOfService
13. MET Norway Locationforecast data model: https://docs.api.met.no/doc/locationforecast/datamodel
14. Met Office sample code, `site_specific_download/ss_download.py` (base URL, `apikey` header): https://github.com/MetOffice/weather_datahub_utilities/blob/main/site_specific_download/ss_download.py
15. Met Office, DataPoint 2025 retirement FAQs: https://www.metoffice.gov.uk/services/data/datapoint/datapoint-retirement-faqs
16. Met Office, How we measure cloud (okta conventions): https://weather.metoffice.gov.uk/guides/observations/how-we-measure-cloud
17. US National Weather Service (Binghamton), Forecast terms, sky condition: https://www.weather.gov/bgm/forecast_terms
18. Open-Meteo source, `WeatherCode.swift` cloud-cover thresholds (commit-pinned): https://github.com/open-meteo/open-meteo/blob/c0d2f3eac3650203a1bf4dc515d903642852afb0/Sources/App/Helper/WeatherCode.swift#L103-L109
