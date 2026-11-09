# PROTOTYPE: sunspot answer screen (throwaway, never merged)

Question: [What does the phone answer screen look like?](https://github.com/epabarker/daylight-viewing/issues/10)

Three structurally different phone layouts of one answer, all on real Bristol output:

- `?variant=A`, **List-first**: a hero "Leave HH:MM" card, ranked cards below, input chips at the top, the map behind a tap.
- `?variant=B`, **Map-first**: a full-screen map with every reachable point coloured by the openness cut-off, a bottom sheet holding the list, and inputs in a settings sheet.
- `?variant=C`, **Timeline-first**: inputs written as a sentence, the Morning window as a time axis, each spot as a bar showing walk, sun and leave-by.

`phone.html` shows all three side by side in 390×844 frames. Switch variants with ← / → or the bottom bar; the `state` button dumps the computed answer.

## Run

```sh
# from the main checkout root (needs data/dsm + data/dtm), ~4 min, writes fixture.js (6.5 MB, not committed)
uv run --with osmnx python <this-dir>/build_fixture.py <outdir> && cp <outdir>/fixture.js <this-dir>/
python3 -m http.server 8765 --bind 0.0.0.0   # in this dir; open /phone.html or /?variant=A
```

## What's real and what's stubbed

- **Real:**
  - 20,138 open-ground Candidates (DSM − DTM ≤ 1 m) within 12 m of the OSM walk network and 22 min walk of home (51.4720, −2.6040).
  - Horizon profiles over 40–200° at 1° (max_ray 3 km).
  - pvlib sun tracks for 365 days.
- **Computed live in the browser:** the Morning window, the taper, Sun minutes, Sky openness over the day's sun-path azimuths ±10°, ranking with a 200 m / same-name de-dupe, leave-by, the Duration target, the Protocols factor, and the fallbacks.
- **Stubbed:**
  - GPS and "Work" both use Home's walk times.
  - Cloud is a manual pick; the Open-Meteo call isn't wired.
  - Walk speed is a fixed 5 km/h, and walk distance is nearest-node network distance plus straight-line distance to the node.
