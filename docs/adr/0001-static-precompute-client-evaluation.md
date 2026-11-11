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
- **Rule changes don't need a recompute.** That covers the Morning window, the taper, the ranking key and the openness cut-off. Only a change to the horizon algorithm or the LIDAR does.
