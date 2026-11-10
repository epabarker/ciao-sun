# PROTOTYPE results, re-scaled: far field, 60–160° band, 0.1° storage

This is the follow-up to `horizon_cost_results.md` for the wayfinder ticket *On-demand
run vs precomputed Horizon profiles: what do they cost?* (epabarker/daylight-viewing#6).
Three later decisions changed the job:

- **Band.** The Morning window's sun path is about **60–160°** for Bristol with a
  07:00 Wake time. (It was 40–140° before.)
- **Far field.** The EA 1 m DSM runs to 3 km, then **OS Terrain 50** to 50 km for
  Bristol and 100 km for GB.
- **Precision.** Profiles are stored at **0.1°**.

The script is `horizon_cost_farfield.py` and the raw output is
`horizon_cost_farfield_results.json`. It uses the same circle as before: home
51.4720,-2.6040, radius 1.5 km, 10 m spacing, **70,681 Candidates**, 7.07 km². It ran
on one core of an Apple M5. Unless a figure says otherwise, the azimuth step is 1°
(101 azimuths).

The true-vs-grid azimuth bug is not fixed here. It costs nothing extra, and both sides
of the fidelity test share it.

## Headline

1. **The far field is almost free, as long as it lives on a coarse grid.**
   - **Per Candidate** it is expensive. A far-field ray costs 9.8 µs to 50 km and
     14.6 µs to 100 km, against 5.6 µs for a near-field ray. That would make
     precompute 2.7–3.6× as costly.
   - **On a coarse grid** it is nearly free. Compute it once per 100 m or 250 m
     lattice point. Correct it for each Candidate's own eye height using the distance
     of the ridge that sets it. Then combine it as `max(near, far)`.
   - **Cost and error.** For all of England that takes **~1–5 core-hours**. The error
     is within the 0.1° target:

     | Far-field lattice | Far-set pairs off by more than 0.1° | p99 error on far-set pairs |
     |---|---|---|
     | 100 m | 0% | 0.035° |
     | 250 m | 0.6% | 0.083° |

     A far-set pair is a Candidate and azimuth where the far field sets the profile.
   - **The height correction matters.** At 250 m without it, 4.2% of far-set pairs
     are more than 0.1° off. At 500 m, 3.4% are off even with it.
2. **The azimuth step, not quantisation, now limits leave-by accuracy.** These are
   first-sun errors against exact per-minute scoring, across all Candidates, with
   linear interpolation, on 21 Dec and 10 Nov:

   | Az step | Mean abs first-sun error | First sun > 2 min late |
   |---|---|---|
   | 1° | **2.0–2.4 min** | 11–14% |
   | 0.5° | 1.3–1.4 min | 4–6% |
   | 0.25° | **0.9 min** | 3% |

   The far field fixed a 3–5 min leave-by error. At 1° the profile gives back about
   half of that through interpolation, mostly by closing narrow gaps, so first sun
   comes **late**.
3. **0.1° storage costs little if the code is piecewise.**
   - **The code.** Use 0.1° steps on −2° to 10°, then 0.5° steps up to 63.5°. That is
     228 codes, so it fits in **uint8**. Against linear 0.1°, its verdicts agree
     to within 0.08 percentage points, and first sun to within 0.2 min. The gap
     comes from obstructions above 10°.
   - **Size.** Linear 0.1° needs uint16 and is 1.36× bigger.
   - **Gain over the old code.** Against the old 0.5° uint8 code, first-sun error
     improves by 0.05–0.3 min.
4. **On-demand cost is unchanged by the far field, using the same coarse-grid
   trick.** A wake-anchored 3 h track at 1 min steps is still **~72 s per query** on
   one core for a 1.5 km radius. It also needs the DSM working set resident, about
   650 MB.
5. **Sky openness costs nothing extra on either path.** It is read off the same
   Horizon profile, or on demand off the same sun-track rays.

## Unit costs (one core)

| Ray | Samples | µs per ray |
|---|---|---|
| Near field, 1 m DSM, 0–3 km | 459 | **5.6** (5.6–7.3 measured; 5.6 on the full run) |
| Far field, Terrain 50, 3–50 km, research density (25/50/200 m) | 780 | 18.6 |
| Far field, 3–50 km, cheap density (50/100/250 m) | 420 | **9.8** |
| Far field, 3–100 km, research density | 1,030 | 24.6 |
| Far field, 3–100 km, cheap density | 620 | **14.6** |

- **Density.** The cheap density differs from the research density by p99 0.014° and
  at most 0.039°, so it is enough.
- **Reach.** In Bristol, going from 50 to 100 km raises no far horizon at all, matching
  the far-horizon research.
- **Where the far field matters.** It sets the profile on only **1.6%** of
  Candidate–azimuth pairs over 60–160°. Those are exactly the open, east-facing spots
  that rank highest.

## Precompute time

| Scope | Near field | Far field (100 m lattice, 100 km) | Total |
|---|---|---|---|
| Bristol circle, 60–160° @ 1° | 41 s measured | 1.1 s measured (to 50 km) | **~42 s** |
| Bristol circle @ 0.25° | ~165 s | ~5 s | ~170 s |
| **England**, 60–160° @ 1° (101 az) | ~208 core-h | ~5 core-h (250 m: ~0.9) | **~210 core-h** |
| England @ 0.5° (201 az) | ~415 core-h | ~10 core-h | ~425 core-h |
| England @ 0.25° (401 az) | ~830 core-h | ~20 core-h | ~850 core-h |

- **The rule of thumb.** The near field costs **~2.1 core-hours per azimuth sample**
  across England at 10 m spacing: 0.057 core-s per km² per azimuth.
- **Wider bands.** These figures assume Bristol's 07:00-wake band. A later winter Wake
  time pushes the band toward ~200°, and northern England shifts it again. Scale by
  the number of azimuth samples.
- **Not measured.** Scaling is assumed linear with cores, and multi-core runs were not
  timed. A compiled or GPU ray caster would cut both paths by the same constant.

## Storage (combined profile, 10 m, 60–160°, xz on azimuth deltas)

| Code | Az step | Per km² | Bristol circle | England |
|---|---|---|---|---|
| Piecewise uint8 (0.1° below 10°) | 1° | 0.33 MB | 2.3 MB | **~42 GB** |
| Piecewise uint8 | 0.5° | 0.49 MB | ~3.4 MB | **~63 GB** |
| Piecewise uint8 | 0.25° | 0.65 MB | ~4.6 MB | **~85 GB** |
| Linear 0.1° uint16 | 1° | 0.44 MB | 3.1 MB | ~58 GB |
| Old linear 0.5° uint8 (reference) | 1° | 0.26 MB | 1.8 MB | ~34 GB |

- **How the steps were measured.** The 0.5° and 0.25° rows were measured on the inner
  500 m disc and scaled per km². The inner disc gives 0.34 MB/km² at 1°, against 0.33
  on the full circle, so the scaling holds.
- **The far-field floor.** The combined profile never goes below **+0.06°** here,
  because of the hills. That floor costs nothing in size.
- **What a phone fetches.** For a 1.5 km neighbourhood that is **~2–5 MB**, depending on
  the azimuth step.
- **Terrain 50 itself.** It is 728 MB as int16 for GB. A crop around one location is
  8.5 MB to 50 km and 33 MB to 100 km. On-demand needs it resident, at that size.
  Precompute needs it only at build time.

## Fidelity detail (5,000 random Candidates, 3 h track from Nominal sunrise, 1 min steps)

These use the piecewise uint8 code and linear interpolation. Exact means a near-field
ray plus a per-Candidate far-field ray at every sun step.

| Date | Az step | Clear/blocked verdicts that disagree | Mean error in longest Clear window | Mean abs first-sun error | First sun > 2 min early / late |
|---|---|---|---|---|---|
| 21 Dec | 1° | 0.69% | 0.80 min | 2.39 min | 2.2% / 14.2% |
| 21 Dec | 0.5° | 0.45% | 0.47 min | 1.40 min | 0.7% / 5.6% |
| 21 Dec | 0.25° | 0.29% | 0.31 min | 0.87 min | 1.3% / 3.2% |
| 10 Nov | 1° | 0.71% | 1.03 min | 2.01 min | 2.5% / 10.6% |
| 10 Nov | 0.25° | 0.31% | 0.46 min | 0.91 min | 1.1% / 2.9% |
| 20 Mar | 1° | 0.58% | 0.87 min | 1.83 min | 2.3% / 8.2% |
| 21 Jun | 1° | 0.55% | 0.60 min | 1.05 min | 1.6% / 4.4% |

- **Conservative interpolation doesn't help.** Taking the max of the two neighbouring
  samples avoids early errors but doubles or triples the late ones (21 Dec at 1°: 35%
  late by more than 2 min). Linear is better.
- **These are all-Candidate figures.** Spots blocked nearby, which see the sun through
  narrow gaps, dominate them. The top-ranked open spots are probably better than this.
  That was not measured separately.

## Still not measured

- Client-side evaluation in JS.
- Multi-core scaling.
- A compiled ray caster.
- Whether 10 m spacing misses spots that 5 m would find.
- Whether hillier places need a finer far-field lattice than Bristol does: ridges at
  3–5 km make the far field change faster with position.
