---
status: accepted
---

# Static precomputed Horizon profiles, evaluated on the phone

Ciao Sun has no server. Horizon profiles are precomputed offline and served as static 1 km tiles. Each tile also holds the walk graph and Candidates. The phone does all of the date-dependent work: the sun track, the Morning window, Sun minutes, Sky openness, ranking and walk routing. So the JS client is the canonical scorer. The Python code is the build pipeline, plus a reference that generates parity fixtures for the JS to match. The JS solar model must agree with pvlib within 0.01°.

Profiles don't depend on the date, so precomputing them loses nothing except a small interpolation error: about 0.5 min of first sun at 0.25° steps. On-demand evaluation costs about 72 core-seconds per query, against about 12 ms on the client. Static tiles also keep GPS on the phone and cost nothing per query. They also scale to Stage 3 on a CDN.

## Considered options

- **A VPS running the Python on demand.** It has no interpolation error and needs no precompute. It was rejected for latency, for running a server, and for per-query cost at public scale.
- **A hybrid: static profiles plus a VPS for evaluation or routing.** It was rejected because the phone can do both. Routing a 1.6 km walk graph takes milliseconds.

## Consequences

- **Two implementations of the scoring rules exist on purpose.** Python is the reference and JS is canonical. CI parity fixtures are what stop them drifting, so don't "simplify" by deleting either side without replacing those fixtures.
- **The tile format is the boundary between build and client.** It is language-neutral and versioned, and it is built tile by tile in parallel. The builder can therefore be rewritten later (compiled, GPU) for England or UK coverage without touching the client.
- **Rule changes don't need a recompute.** That covers the taper, the ranking key, the openness cut-off and any window rule that keeps the sun inside its window's sector. Only a change to the horizon algorithm, the LIDAR, or a window reaching past its sector does: each window's tiles hold only the azimuths its sun path can reach, with the Morning window ending by solar noon ([#62](https://github.com/epabarker/ciao-sun/issues/62)).
- **What a phone fetches, measured on the first Bristol build ([#55](https://github.com/epabarker/ciao-sun/issues/55)).** A query loads its window's tiles within a 20 min walk (1,600 m) of the origin: 15–16 squares. With full-circle profiles that was 13.9 MB at the median (p90 20 MB), against a 6–7 MB estimate, because Horizon profiles are 95% of a tile. So each square has a morning and an evening tile holding only that window's sector of azimuths, and a query fetches 6.5 MB (morning) or 6.4 MB (evening) at the median, about 9.3 MB at p90, once: tiles are cached. A whole Bristol build is about 115 MB of tiles, 147 squares × 2.
- **The data host sees roughly where a query is.** The GPS position never leaves the phone, but the 1 km tiles and high-zoom basemap tiles a query loads show the data host which area is being looked at, to about a tile. The About sheet says so in one fixed line ([Ed's ruling on #27](https://github.com/epabarker/ciao-sun/issues/27#issuecomment-6801240295)).
