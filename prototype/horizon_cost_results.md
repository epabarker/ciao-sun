# PROTOTYPE results: on-demand vs precomputed Horizon profiles

Throwaway cost benchmark for the wayfinder ticket *On-demand run vs precomputed
Horizon profiles: what do they cost?* (epabarker/daylight-viewing#6).
Branch `prototype/horizon-cost`, never merged. Neither the logic branch nor the
UI branch of the prototype skill fits this question, so this is a cost
benchmark. The rough numbers are the asset. The script is `horizon_cost_bench.py`
and the raw output is `horizon_cost_results.json`.

**Setup.** The run used the six Bristol tiles. Home was 51.4720,-2.6040, with
radius 1500 m and spacing 10 m. That gives **70,681 Candidates** over
**7.07 km²**. Each ray takes 459 samples out to 3 km. The machine was an
Apple M5 with 10 cores and 24 GB of memory. Everything ran on **one core**,
because the numpy ray casting is single-threaded.

## Unit cost

The basic unit is one ray: one Candidate at one azimuth. A ray costs
**≈ 5.6 µs** on a single core. That figure holds for on-demand and precompute
alike, and stays flat from 4k to 70k candidates, measured at 5.52–5.70 µs.
Everything below follows from it:

- on-demand rays = candidates × sun-track steps
- precompute rays = candidates × azimuth samples
- candidates per km² = 10⁴ at 10 m spacing, 2.5×10³ at 20 m, 4×10⁴ at 5 m

## (a) On-demand `find`, Bristol, one location and date (2026-12-21)

| Track | Steps | Scoring | Whole CLI run | Peak RSS |
|---|---|---|---|---|
| Default: 60 min after sunrise, 5 min step | 13 | 5.1 s | **7.6 s** warm cache, **26 s** cold from GeoTIFFs | 1.0 GB warm, 1.9 GB cold |
| Wake-anchored, 2 h at 2 min | 61 | 23.8 s | ~26 s | ~1 GB (dominated by the mosaics) |
| Wake-anchored, 3 h at 1 min (extrapolated) | 181 | ~72 s | ~75 s | ~1 GB |

- The default config understates the real job. The Morning light research
  anchors the window to wake time and tapers it over 2–3 h, which means
  **5–14× the rays** of the default.
- Cost scales with radius². A 1 km radius costs about 0.44× the figures above.
- The LIDAR has to be resident or on local disk. The Bristol pair is
  2 × 9000² float32, which is 648 MB in RAM. The cold run spends ~20 s building
  the npz cache.

## (b) Precompute Horizon profiles over the same circle

What azimuth band do we need? It depends on the time window, not on sunrise
alone:

| Date | Sunrise az | +1 h | +2 h | +3 h | +4 h |
|---|---|---|---|---|---|
| 21 Dec | 128° | 141° | 153° | 167° | 181° |
| 20 Mar | 89° | 101° | 114° | 127° | 143° |
| 21 Jun | 49° | 61° | 72° | 83° | 94° |

The ticket's 40°–140° band covers only about the first hour after sunrise in
winter. A wake-anchored 2–3 h window from a late winter wake runs to
**~180–200°**. That is why the band here was computed as **40°–200°**, and why
the costs below are quoted per degree.

Measured: the 40°–200° band at 0.5° steps (321 azimuths) took **129 s** on one
core.

| Basis | 10 m spacing |
|---|---|
| per km², per azimuth sample | 0.057 core-s |
| Bristol, 40–140° @ 1° (101 az) | ~41 core-s |
| Bristol, 40–200° @ 1° (161 az) | ~65 core-s |
| **England** (~130,300 km²), 40–200° @ 1° | **~330 core-hours**, so ~33 h on 10 cores (linear scaling assumed, not measured) |
| England at 20 m / 5 m spacing | ~85 / ~1,330 core-hours |

## Fidelity: precomputed profile vs exact on-demand

The test took 15k random Candidates and three dates. For each one it ran a 3 h
track after sunrise at 1 min steps. The profile was linearly interpolated in
azimuth and then quantised. Angles were clamped to [−2°, 64°] first: below −2°
always clears, and above the highest sun always blocks.

| Az step | Quantisation | Clear/blocked verdicts that disagree | Mean error in longest Clear window | Candidates off by >5 min |
|---|---|---|---|---|
| 0.5° | none / 0.1° / 0.25° / 0.5° | 0.29–0.56% | 0.4–0.7 min | 0.9–1.8% |
| **1°** | none / 0.1° / 0.25° / 0.5° | **0.52–0.78%** | **0.8–1.0 min** | **1.9–2.6%** |
| 2° | any | 0.88–1.22% | 1.4–1.7 min | **5.3–7.1%** |

These ranges cover all three dates (Dec, Mar and Jun behave alike).

- **Azimuth step dominates the error. Quantisation hardly matters:** 0.5°
  quantisation adds only ~0.1 percentage points.
- 2° is visibly worse.
- Even 0.5° isn't exact. Narrow obstructions such as poles, chimneys and gaps
  between buildings fall between the sampled azimuths.
- About 45–55% of all Candidates see the sun at some point in the 3 h.

## Storage: band 40°–200°, compressed with xz on azimuth-delta codes

| Spacing | Az step | Quantisation | Raw | Compressed: Bristol | Compressed: per km² | England |
|---|---|---|---|---|---|---|
| 10 m | 1° | 0.5° (uint8) | 11.4 MB | **2.9 MB** | **0.42 MB** | **~54 GB** |
| 10 m | 1° | 0.25° | 22.8 MB* | 4.0 MB | 0.57 MB | ~74 GB |
| 10 m | 0.5° | 0.5° | 22.7 MB | 4.1 MB | 0.58 MB | ~75 GB |
| 20 m | 1° | 0.5° | 2.8 MB | 0.74 MB | 0.11 MB | ~14 GB |
| 20 m | 2° | 0.5° | 1.4 MB | 0.50 MB | 0.07 MB | ~9 GB |

\* The 0.25° quantisation spilled into uint16 because the clamp ran to 64°.
Clamping to 61.75° fits it in uint8, which halves the raw size. The compressed
size barely changes.

- zlib, which is gzip-class, comes out ~1.2–1.3× bigger than xz. Delta coding
  along azimuth saves ~10–12%.
- A narrower 40–140° band is ~0.63× these sizes.
- Raw size is n_candidates × n_az × bytes, so it is linear in band width and
  quadratic in 1/spacing.
- What a phone fetches for a 1.5 km neighbourhood at 10 m / 1° / 0.5° is
  **~3–4 MB** compressed.

## For comparison: LIDAR input volume

The input is **~5 MB/km²** for DSM+DTM, whether zipped or unpacked. That is
760 MB zipped and 734 MB unpacked for 150 km². For England it comes to
**~650 GB**. On-demand anywhere needs that volume on disk, plus ~650 MB of RAM
per 9 km² working set.

## Not measured

- **Client-side evaluation in JS.** Interpolating 70k profiles × 181 steps is
  expected to be cheap, but it wasn't timed in a browser.
- **Multi-core scaling.**
- **Compiled or GPU ray casting.** Numba or similar would likely give a large
  constant-factor win on both paths alike.
- **Whether 10 m spacing misses spots that 5 m would find.**
