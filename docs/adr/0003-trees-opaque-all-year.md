---
status: accepted
---

# Trees are opaque all year: one crown-envelope surface, no seasonal profiles

Horizon profiles are cast against one surface on every date. Wherever there is vegetation, that surface is raised to the tree crown's outer envelope, which the EA first-return composite DSM records. Trees therefore count as fully in leaf even in December. Vegetation means first-return DSM − DTM over 2 m, outside OSM building footprints buffered by 1.5 m. On those cells the surface is the larger of the last-return and first-return DSM, whatever season the cell was surveyed in. Everywhere else it is the last-return DSM.

The reason is that the last-return DSM the tool used before is mostly leaf-off near Bristol, and its returns pass straight through bare crowns. It showed deciduous trees as absent, which made answers from May to October badly optimistic. About a quarter of the "open" spots were really enclosed by trees, and top-5 leave-by times were off by up to 72 min ([leaf-on canopy measurement](https://github.com/epabarker/daylight-viewing/issues/23)). Summer had to be corrected. The real choice was what to do in winter. A bare crown passes about half the direct beam (0.40–0.52 measured; SOLWEIG uses 0.5), so neither "open" nor "opaque" is true, and nobody has measured below about 14° sun ([bare-crown transmittance research](https://github.com/epabarker/daylight-viewing/blob/research/bare-crown-transmittance/research/bare-crown-transmittance.md)). We chose opaque because it errs conservatively, and because it barely changes what the tool recommends. On winter dates, the #1 spot ranked against opaque crowns has the same low-sun minutes (to within 3) and the same walk (to within 1 min) as the #1 ranked against open crowns, in 7 of 8 cases.

## Considered options

- **Seasonal profiles: crowns in leaf from May to October, open in winter.** Rejected. It needs a second profile set in every tile, leaf-on season dates, handling of each cell's survey season, and an under-crown Candidate filter for winter. It would also still be optimistic wherever a low sight line crosses a crown's core or several crowns.
- **Seasonal, with a crown-crossing threshold in winter (SOLWEIG-style, about 0.5 per crown).** Closest to the physics. Rejected for Stage 1 because it adds the most to the build, and its threshold is an untested product choice for 0–10° sun.
- **Raw first-return DSM everywhere, with no mask.** Rejected. First returns spill about a cell past walls and eaves, so 10–15% of open spots lost 5 min or more. Low clutter beside Candidates also moved some top-5 leave-by times by up to 136 min.
- **Caveat only.** Rejected. A caveat can't fix a #1 pick that gets no sun.

## Consequences

- **Horizon profiles stay independent of date,** and the tile format keeps one uint8 profile set.
- **Winter answers are a lower bound.** Sun through bare branches doesn't count, so a spot may get sun earlier than shown. The about/method sheet says so; spots carry no warning, because no spot is shown sunnier than it is because of trees.
- **No separate under-crown Candidate filter is needed.** The 0.75 openness cut-off removes nearly all Candidates standing under a crown: on crown-envelope profiles, 1 of 80 top-5 slots across the measured dates was still one, against 14 of 80 on the old profiles.
- **New build input.** `lidar_composite_first_return_dsm` becomes a `sunspot fetch` input and gets an entry in the manifest.
- **Clutter under 2 m beside a Candidate is ignored** (hedges, walls, cars). The copy tells people to stand clear of it.
- **Going seasonal later is a format bump,** because a second profile set changes the tile format.
- **For Stage 2, this doesn't depend on survey season**, but it does need a first-return product wherever coverage extends.
