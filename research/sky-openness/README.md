# Sky openness spread near home (Bristol)

Throwaway evidence for [What does the tool show, and what question does it answer?](https://github.com/epabarker/daylight-viewing/issues/7). Never merged.

**Question:** across open-ground Candidates within 1.5 km of home (51.4720, -2.6040), does Sky openness vary enough to rank spots on?

**Answer:** no. It is a filter, not a ranker. 42% of Candidates have a sky-view fraction of 0.9 or more over 40–220°. Wide-sector SVF runs from 0.88 at p50 to 0.996 at p95. The cos² weighting cannot separate a 2° horizon from a 12° one. Openness separates terraced streets (about 0.6) from parks (about 0.99). Sun-disc visibility (Sun minutes) has to carry the ranking.

**Method:** 10 m grid with 70,681 points. 26,222 were dropped where DSM − DTM > 1 m (roofs or canopy), leaving 44,459. Horizon profiles cover 40–220° at 5° steps, with max_ray 3000 m and curvature on. Runtime was about 29 s.

**Sun paths, from Wake time 07:00 to 10:00:**
- 21 Dec: 08:14 to 10:00, azimuth 128–150°, elevation 0–10°.
- 21 Jun: azimuth 73–109°, elevation 16–44°.

**Caveats:**
- The DSM is leaf-on, so it overstates winter obstruction.
- Points next to walls see near-vertical obstruction.
- Nothing filters for access (gardens, roads and rail are included).
- The winter-sector (125–155°) figures quoted on the ticket were computed ad hoc from `profiles.npz` and are not in `results.json`.

**Reproduce:** `.venv/bin/python research/sky-openness/openness.py <outdir>` from the repo root, with the six Bristol tiles in `data/`. `profiles.npz` (5.6 MB) is not committed; it is regenerated in `<outdir>`.
