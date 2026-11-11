# Solar model

This is the reference solar model. `ciao_sun.solar` implements it in Python,
and the JS client ports it. **The JS must agree with the reference within
0.01° in both true azimuth and apparent elevation at every minute of a sun
track** (ADR 0001). Nominal sunrise, Nominal sunset and solar noon must be the
same minute. Terms follow `GLOSSARY.md`.

## Sun track

A sun track covers one local civil day at one place: every whole minute from
00:00 to 23:59 in the query's time zone (1,440 samples, or 1,380 and 1,500 on
the days the clocks change). Each sample holds:

| Value | Meaning |
|---|---|
| True azimuth | Degrees clockwise from true north, 0 ≤ azimuth < 360 |
| Geometric elevation | Topocentric elevation of the disc centre with no refraction, degrees |
| Apparent elevation | Geometric elevation + refraction (below), degrees |

The sun is compared with a Horizon profile by its apparent elevation. No
refraction margin is added or subtracted anywhere.

## Geometric position

NREL SPA: Reda and Andreas, *Solar Position Algorithm for Solar Radiation
Applications*, NREL/TP-560-34302 (revised 2008), as implemented by pvlib's
`spa_python(..., how="numpy")`. The outputs used are the topocentric azimuth
(eastward from north) and the topocentric elevation without atmosphere.

Fixed inputs, the same for every query:

| Input | Value |
|---|---|
| ΔT (TT − UT1) | 67.0 s |
| Observer altitude | 0 m |
| Time | The sample's UTC instant, taken as UT1 |

SPA's pressure, temperature and `atmos_refract` inputs only feed its own
refraction and rise/set routines, which are not used.

## Refraction

One formula at every elevation. With `h` the geometric elevation in degrees:

```
h_floor = sqrt(10.3) − 5.11                      (≈ −1.900639°)
h'      = max(h, h_floor)
R       = 1.02 / tan(h' + 10.3 / (h' + 5.11))    arcminutes, tan of an angle in degrees
apparent elevation = h + R / 60
```

| Parameter | Value |
|---|---|
| Scale | 1.02 arcminutes |
| A | 10.3 deg² |
| B | 5.11° |
| Floor | `sqrt(A) − B` |
| Pressure and temperature factor | 1, that is 1010 hPa and 10 °C; not adjusted for weather or height |

This is the refraction formula SPA itself uses (Sæmundsson's, for a true
elevation), with two changes:

- **No switch-on.** SPA, and so pvlib, applies it only when `h ≥ −0.833°` and
  adds nothing below, which makes apparent elevation jump by more than half a
  degree at that level. Here it applies at every elevation.
- **A floor.** The formula's refraction peaks at `h_floor`, where its
  derivative is zero, and misbehaves below (it diverges at −5.11°). Below the
  floor the refraction is held at its peak, 0.744129°. The join is continuous
  and smooth.

So refraction never increases with elevation, and apparent elevation rises
strictly with geometric elevation. Above −0.833° the result equals pvlib's
`apparent_elevation` at 1010 hPa and 10 °C.

Check values:

| `h` (°) | `R / 60` (°) |
|---|---|
| −5 | 0.744129 |
| −0.833 | 0.618185 |
| −0.5667 | 0.572663 |
| 0 | 0.483032 |
| 1 | 0.362398 |
| 5 | 0.161235 |
| 30 | 0.029100 |

## Nominal sunrise, Nominal sunset and solar noon

All three are read off the day's sun track and are whole minutes.

A **crossing** of a quantity `v` upward through zero lies between consecutive
samples `i` and `i + 1` with `v[i] < 0 ≤ v[i + 1]`. Its minute is

```
i + floor(−v[i] / (v[i + 1] − v[i]) + 0.5)
```

which is the sample nearest the linearly interpolated crossing, with ties
going to the later one. This is the rounding almanacs use.

`GLOSSARY.md` words Nominal sunrise as the first minute at −0.833° and Nominal
sunset as the last minute at or above it. Read literally on whole minutes
those land up to a minute after and before the almanac's figures; the nearest
minute is what matches an almanac, so the nearest minute is the rule.

| Event | Crossing of | Which one |
|---|---|---|
| Nominal sunrise | `geometric elevation + 0.833` | First of the day |
| Nominal sunset | `−(geometric elevation + 0.833)` | Last of the day |
| Solar noon | `−sin(true azimuth)` | First of the day |

- Nominal sunrise and sunset use the **geometric** centre at −0.833° (34′ of
  standard refraction plus a 16′ semi-diameter). The refraction model above
  plays no part in them.
- Solar noon is the upper transit: the sun passing from the eastern half of
  the sky to the western. `sin(azimuth)` falls through zero only there, in
  either hemisphere.
- A day with no upward crossing has no Nominal sunrise, and one with no
  downward crossing has no Nominal sunset.

## Worked example

Bristol, 51.45° N, 2.60° W, 2026-12-21, UTC:

| Time | True azimuth (°) | Geometric elevation (°) | Apparent elevation (°) |
|---|---|---|---|
| 07:00 | 114.5324 | −10.5646 | −9.8205 |
| 08:13 (Nominal sunrise) | 128.2538 | −0.8762 | −0.2506 |
| 12:08 (solar noon) | 179.8890 | 15.1106 | 15.1714 |
| 16:04 (Nominal sunset) | 231.7584 | −0.8850 | −0.2579 |

`tests/test_solar.py` checks the model against US Naval Observatory rise, set,
transit and altitude/azimuth values for Bristol on the solstices and equinoxes.
