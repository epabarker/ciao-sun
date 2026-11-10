# How much low sun gets through a bare deciduous crown?

This note answers the open input from the leaf-on canopy prototype ([#23](https://github.com/epabarker/daylight-viewing/issues/23), [README](https://github.com/epabarker/daylight-viewing/blob/prototype/leaf-on-canopy/prototype/leaf-on-canopy/README.md)), which feeds the canopy decision ([#24](https://github.com/epabarker/daylight-viewing/issues/24)). The question is how opaque a leaf-off deciduous crown is to direct sun at 0–20° elevation. The tool's Horizon profile is binary, so the choice is between treating bare crowns as open (the as-is DSM, whose leaf-off last return passes through them) and treating them as opaque (the leaf-off first-return crown envelope, the prototype's `leafy` surface). On winter dates the two differ by a mean of 9–18 min in first sun and Last sun.

**Terms** follow `GLOSSARY.md`: Candidate, Horizon profile, Last sun, Sun minutes. *Transmittance* (τ) means the fraction of the direct solar beam that passes through a crown, so τ = 1 − (fractional reduction).

**Source labels.** Each source is marked with where its text came from:
- **[full]**: full text read.
- **[abstract]**: only the abstract was read; methods and results are not inferred from it.
- **[code]**: source code read at a pinned commit.
- **[secondhand]**: a forum quote or search snippet, not verified in the original.

## TL;DR

1. **Measured bare-crown direct-beam transmittance is about 0.4–0.6 per crown.** Four of the measured species are common UK street trees: lime, horse chestnut, birch and London plane.
   - In Göteborg, single leafless street trees transmitted a mean of **0.52** (lime, horse chestnut) and **0.51** (birch) of the direct beam, with 10-min values from 0.01 (behind the trunk) to 0.93–1.0 (through gaps) [1].
   - The published paper on that dataset gives **0.40–0.52** across its four deciduous trees [2].
   - In Pennsylvania, leafless London plane, Norway maple and sugar maple cut clear-sky irradiance on a wall at the centre of their shade by **37–52%** (τ ≈ 0.48–0.63 for global radiation, which includes diffuse) [3].
2. **None of these measurements was made at 0–20° sun.** They were made with the sun at about **14–35°** (Göteborg, March) and about **18–62°** on the clear leafless days in Pennsylvania (about 24–42° for the January–March clear runs); the elevations are computed below. Anything said about 0–20° is extrapolation.
3. **Whether τ falls at low sun is contested.**
   - A forest model has beam transmission falling as exp(−P_c·secθ − P_s·tanθ), so lower sun means lower τ [4], and a telephoto study of forests found τ fell as the sun got lower [5].
   - In a leafless oak–hickory forest, attenuation coefficients were "much greater during winter leafless period because solar elevation angles are lower and the canopy consists of dark, opaque, woody biomass", and beam radiation was not attenuated exponentially [19].
   - A companion paper on the same forest [6] and a ray-traced model of deciduous street trees [7] found no elevation effect in winter.
   - All five are abstract-only. For one isolated crown, the chord through it is bounded by the crown's width, so the path at 5° is not much longer than at 30°.
4. **The number of crowns the ray crosses matters most.** At 0–10° elevation the sight line runs nearly horizontally for tens to hundreds of metres. In UK streets (rows of trees) and parks (clumps), it often crosses two or more crowns, plus trunks and big limbs.
   - At about 0.5 per crown, two crowns pass about **0.25** and three about **0.12**, assuming the crowns attenuate independently (Beer's law). This is my inference; no source tested it.
5. **Models split, and no documented default treats bare crowns as fully open.** (ENVI-met would be fully open with a winter season factor of 0.)
   - SOLWEIG hard-codes leaf-off transmissivity at **0.5**, against 0.03 in leaf [8].
   - The Solar Pathfinder manual gives zero credit, i.e. full shade, to periods shaded by bare deciduous trees for PV, and half credit for thermal collectors [9].
   - Simpson & McPherson's building-energy simulations assumed leaf-off trees block **30%** [10].
   - PV*SOL lets the user enter monthly transmittance; a quoted DGS default is τ = 0.64 in winter [secondhand].
   - ENVI-met scales shading by a monthly season factor and does not document a woody term [11].
6. **Bottom line.**
   - Behind **one** bare crown, a person is in **dappled sun**: the disc shows through tracery at roughly half strength, flickering to nothing behind trunks and major limbs. Neither binary is close; open is off by about +0.5 and opaque by about −0.5.
   - A crown's core passes about 0.34–0.43 and its fringe about 0.6–0.8, measured on crowns 6–14 m wide [3]. So the core is dappled leaning shaded and the fringe is mostly sun, at any crown size the data cover.
   - At the opaque surface's first sun or Last sun, the decisive ray grazes the top fringe of the nearest crown. The true time lies inside the bracket, where cumulative τ along the ray crosses whatever threshold counts as sun.
   - **Opaque is less wrong** where the ray behind the crown silhouette passes through two or more crowns or a crown core. **Open is less wrong** behind one crown's fringe. Which case dominates in Bristol is untested; the first-return crown mask can measure it.
   - **Better than either:** about 0.5 per crown crossed, as SOLWEIG does, with the sun counted once the cumulative τ exceeds a threshold.
   - **Confidence:** moderate for "about half per crown at 15–35°"; low to moderate for anything at 0–10°.

## 1. Measured transmittance of leafless crowns

| Source | Place, trees | Sun elevation during measurement (computed) | Leaf-off result | Text |
|---|---|---|---|---|
| Larsson 2011 [1] (MSc thesis; supervised by Lindberg) | Göteborg 57.7°N. Single street/park trees: *Aesculus hippocastanum* (8 Mar), *Tilia cordata* (16 Mar), *Betula pendula* (28 Mar), and *Pinus nigra* for comparison. Under the crown, an SPN1 sunshine pyranometer (global and diffuse) and a Kipp & Zonen CM3 at 1.1 m; on a nearby roof, an SPN1. | About 14–27°, 16–30° and 20–35° over 09–16 h on those dates. The trees shaded the sensors around midday (horse chestnut trunk at 12:10–12:40), so most data are at the upper end. | **Direct τ: horse chestnut 0.52, lime 0.52, birch 0.51** (pine 0.16). Total τ 0.57, 0.56, 0.59. 10-min direct τ ranged 0.01–0.85 (horse chestnut), 0.01–0.93 (lime) and 0.02–1.0 (birch). The lowest values were behind the trunk or "a larger branch". The author: various deciduous trees "seem to have a similar transmissivity in the winter". | **[full]** |
| Konarska et al. 2014 [2] | Göteborg. Four deciduous trees and one conifer of species common in northern European cities. Nine clear days in 2011–12. | Not stated in the abstract. | **Direct τ 0.402–0.519** leafless (0.013–0.053 in leaf). Measured values improved SOLWEIG. Larsson is a co-author, and the thesis covers at least part of the same campaign. | **[abstract]** |
| Heisler 1986 [3] | State College, PA, 40.8°N. London plane (11 m tall, 8.4 m crown), Norway maple (6.7 m, 6.4 m), sugar maples (10.4 m, 8.2 m; 15 m, 14 m). Pyranometers on a south-facing "wall". | Clear leafless days: about 18–62° (Table II windows); the January–March clear runs about 24–42°. The partly cloudy 2 Feb run reached down to about 9°. | Clear days: average reduction over the whole shade pattern **30–34%**. **Centre of shade at noon: 37–52%** (56% for the large maple on a hazy day). Leafless reductions were "about half" of in-leaf reductions. Regression for leafless trees: r = 0.39 − 0.24·DR², where DR is the diffuse fraction. These are *global* (beam + diffuse) on a vertical surface, so the beam-only reduction is larger. | **[full]** |
| Heisler 1986 [3], crown density | Same trees, photographed | n/a | Visual density of leafless crowns (share of the crown silhouette blocked): **centre 57–66%**, edge 22–41%, whole crown 34–44%. Literature cited there: sugar maple 44%, Norway maple 39%, London plane about 37%, *Betula pendula* 48% (densest found by Westergard), Modesto ash about 50%, Kentucky coffeetree about 27%, black walnut about 28%. | **[full]** |
| Wagar & Heisler 1986 [12] | 69 leafless trees, three species | n/a | Density lowest for Kentucky coffeetree, highest for Modesto ash, intermediate for London plane. **Density rose with tree size**, and **elevation angle affected it** (the abstract gives no direction or size). | **[abstract]** |
| Takács et al. 2016 [13] | Szeged, Hungary. *Tilia cordata*, *Aesculus*, *Sophora*, *Celtis*. June to late autumn. | Not stated in the abstract. | Horse chestnut median total τ rose from 0.03 in leaf to **0.47 "nearly leafless"**. | **[abstract]** |
| Federer 1971 [4] | Leafless hardwood forests (three stands) | Varied | With snow cover, about 65% of incident radiation was absorbed by stems and branches. Beam τ = exp(−P_c·secθ − P_s·tanθ), with an empirical crown term and a stem term (vertical cylinders) set by basal area, diameter and height. | **[abstract]** |
| Liakatas et al. 2002, cited in [1] | *Quercus frainetto* stand near Athens | Year-round | Global τ about 0.40 just before budburst, 0.15 in leaf. | **[secondhand]**, via [1] |
| de Abreu & Labaki 2008, cited in [1] | *Tabebuia chrysotricha*, Brazil | Tropical | Direct τ 0.539 leafless, 0.183 in leaf. | **[secondhand]**, via [1] |

**Woody area.** For leafless canopies, what blocks the beam is the woody area index (WAI): one-sided silhouette area of stems, branches and twigs per unit ground area. A maple–aspen forest in Ontario gave **WAI ≈ 0.5** from photographs against litter collection [14] **[abstract]**. Optical leaf area index (LAI) methods are known to read about one WAI high in deciduous forests, because they count wood [15] **[abstract]**. TLS, photography and LAI-2000 disagree on leaf-off effective WAI, with relative SD up to about 28–30% for photography, in a deciduous woodland [16] **[abstract]**. I found no measured woody area *density* (m²/m³) for isolated urban crowns. So the crown-level τ values above are the usable evidence, not a forest WAI and an extinction coefficient.

**Core and fringe of a single crown.** Heisler's visual densities give centre τ ≈ 0.34–0.43 and edge τ ≈ 0.6–0.8 [3]. The crowns were 6.4–14 m wide, and centre density showed no clear trend with size: 57–66% for the 6.4–8.4 m crowns and 64% for the 14 m sugar maple. A constant-density Beer's-law scaling would predict much lower τ (about 0.13–0.21) at the core of a 15 m crown. The measured large crown does not support that, so no size scaling is applied here. Wagar & Heisler did find that whole-crown density rises with tree size [12] **[abstract]**, but they give no figures.

## 2. What changes at low sun

**Path length through one crown.** In a forest, the vertical depth of canopy the beam crosses scales with secθ, so at 10° elevation it is about 2.9× the path at 30° [4]. An isolated crown is different: the longest chord is its width W, whatever the elevation. For a UK street tree with a crown about as wide as it is deep, the chord at 5° is about W and at 30° somewhat less. **So for one isolated crown the low-sun path is only modestly longer**, on the order of 1–1.5× (geometry, my inference). That fits the two studies that found no elevation effect in winter:
- In a leafless oak–hickory forest, "solar elevation did not influence the attenuation of insolation … under the conditions studied" [6] **[abstract]**.
- In ray-traced CG models of four Japanese street-tree species, "in winter, solar shading ratio of tree was constant any solar attitude" [7] **[abstract]**.

Against that, the companion paper on the same oak–hickory forest reports leafless-period attenuation coefficients "much greater during winter leafless period because solar elevation angles are lower and the canopy consists of dark, opaque, woody biomass", with beam radiation not attenuated exponentially [19] **[abstract]**. Both are forest results; neither gives an isolated-crown figure.

**Stems and limbs.** Federer's stem term grows with tanθ [4]. At 5° elevation tanθ is about 11, against 1.7 at 30°. Near the horizon the beam is blocked by trunks and major limbs as well as twigs. The 0.01 minima in [1] were exactly that: the trunk or a large branch.

**More than one crown.** This is the biggest change. From a Candidate at 1.6 m eye height, a ray at 3° climbs only about 5 m in 100 m. So the sight line to a low sun passes through every crown in that direction out to some hundreds of metres. A ray at 30° clears a 15 m tree within about 25 m. In a street with a tree row, or across a park, a ray at 0–10° commonly crosses several crowns. If each passes about 0.5, two pass about 0.25 and three about 0.12. The telephoto study of forest canopies found average beam τ fell with decreasing solar altitude, and in the two broadleaved canopies it departed "markedly" from Beer's law at low altitudes [5] **[abstract; three warm-temperate Japanese forests, leaf state not stated]**.

**Hours of the day this covers.** In Bristol the noon sun is about 15° on 21 December, 22° on 5 February and 38° on 20 March (computed). From November to January the whole day is inside the 0–20° band, not just first sun and Last sun. The Göteborg March data, at about 14–35°, sit just above the band and overlap its top.

## 3. Species

- **Measured:** lime, horse chestnut and birch, all about 0.51–0.52 direct τ in Göteborg, with no material difference [1]. London plane was slightly less blocking than the maples in Pennsylvania [3]. In the density survey cited by [3], birch was the densest leafless species found (48%) and plane intermediate (about 37%) [3][12].
- **Not found:** no leaf-off τ for **oak, beech, sycamore or *Fraxinus excelsior* ash**. The only ash value is Modesto ash (*F. velutina*), which was the densest of three species [12]. That does not transfer to the open, thick-twigged crown of UK ash. The Mendoza permeabilities for plane and ash (about 21%) [17] are not stated to be leaf-off values, so they are not used here.
- **Marcescence:** "several deciduous species retain all or some senesced leaves on branches through much of winter" [18] **[abstract]**. In the UK this is typically beech, hornbeam and young oak, often on lower or juvenile branches; that detail is general knowledge, not from [18]. Where it happens, the crown is closer to opaque than to 0.5. I found no transmittance figure for marcescent crowns.
- **Pollarded and epicormic limes:** UK street limes often carry dense epicormic shoots and pollard knuckles. No measurement was found. Expect lower τ than the open Göteborg lime.

## 4. How tools and models treat bare deciduous trees

| Tool | Leaf-off treatment | Text |
|---|---|---|
| **SOLWEIG** (UMEP) | Shadow = sh − (1 − vegsh)·(1 − ψ). In leaf ψ = `Transmissivity`, default **0.03**. Leaf-off ψ is hard-coded: `psi[leafon == 0] = 0.5`. Leaf-on runs from day 97 to day 300 by default. The crown base sits at 25% of tree height by default (`Trunk_ratio` 0.25); the shadow routine itself was not read. Conifers stay leaf-on all year. [8] | **[code]** UMEP-dev/UMEP-processing @ a7798db, `functions/SOLWEIGpython/Solweig_run.py`, `processor/parametersforsolweig.json` |
| SOLWEIG 2.2 (2011) | One vegetation transmissivity, default **0.2**, with no season switch at the time [1]. | **[full]**, via [1] |
| **Solar Pathfinder** manual | Evergreens: never count shaded half-hours. Deciduous: in leaf, don't count; **leaf-off, count at half value for thermal collectors; for PV "assigned a value of zero, unless the manufacturer can support a better figure."** Partial shade from deciduous trees is "nearly the same as total shade for older panels." [9] | **[full]** |
| Solar Pathfinder Assistant (software) | Demo report: "Transparency: 50%", leafless October to April. | **[secondhand]** (search snippet; PDF returned 403) |
| **PV\*SOL** | Per-tree monthly transmittance, 0–100%, set by the user. A forum post quotes the DGS installer guide (2007): τ = 0.64 for deciduous trees in winter, 0.23 in summer, 0.30 for conifers. Valentin staff did not confirm these as defaults. | **[secondhand]** |
| PVsyst | No primary documentation found on tree transparency. | Not found |
| **ENVI-met** | A monthly "Season Profile" factor scales "vegetation activity (photosynthesis, shading, transpiration)". No woody term is documented, and no deciduous winter default is given. [11] | **[full]** help page |
| **EnergyPlus** | `Shading:Site:Detailed` takes a user transmittance schedule; without one the surface is opaque. A user schedule citing McPherson: shading 0.7 summer, 0.175 winter (τ ≈ 0.825). | **[secondhand]** (onebuilding.org, unmethours) |
| Simpson & McPherson 1996 (building-energy simulation) | Trees "blocked 85 percent … when in leaf … and 30 percent during the December to March leaf-off period", citing McPherson 1984 [10]. | **[full]** |

The planning-tool values (τ 0.64–0.83) are higher than the measured 0.4–0.6. They come from older design guides and were not measured at low sun. The measurement group's own model, SOLWEIG, uses 0.5. The PV rule of thumb treats bare trees as shade, but for an electrical reason: partial shading of one cell drags a whole string down. That reason does not apply to a person, so it is not physical evidence about τ.

## 5. What a person behind a bare crown sees

This section is geometric reasoning of mine, not from a source. The sun's disc is about 0.53° across. A 1 cm twig 20 m away subtends about 0.03°, so twigs never hide the disc. They dim and fragment it, and the beam arrives as fine dapple at about the crown's τ. A 20 cm limb at 20 m subtends about 0.6°, enough to eclipse the disc, and a trunk eclipses it for minutes as the sun moves (the 0.01 minima in [1]). So behind one crown, the experience is sun through branches: glare is visible, irradiance is roughly halved, and it drops to full shade behind major wood. Behind two or more crowns at low sun, it is mostly shade with occasional flecks.

## 6. Bottom line for the binary

- **One isolated crown, sun at 15–35°:** τ ≈ 0.5, measured on lime, horse chestnut and birch [1][2] and on plane and maples [3]. The honest label is dappled. Open overstates the sun by about half the beam, and opaque understates it by the same.
- **Sun at 0–20°, as it is all day from November to January:** τ per crown is probably similar, or somewhat lower because of trunks and limbs. The evidence is contested and abstract-only. The beam crosses more crowns as the sun gets lower, so the cumulative τ along a horizon ray is usually well below 0.5.
- **Which binary is less wrong for first sun and Last sun depends on what the ray crosses.** At the opaque surface's first sun or Last sun, the decisive ray grazes the top fringe of the nearest crown; farther crowns of similar height sit below it. The true time is where cumulative τ along the ray crosses the threshold for "sun", which is inside the bracket, not at either end.
  - **Opaque is less wrong** where the ray, once past the nearest silhouette, still passes through two or more crowns or a crown core (τ ≈ 0.34–0.43 per core [3]; about 0.25 or less for two crowns).
  - **Open is less wrong** where the ray crosses only one crown's fringe (edge visual density 22–41% [3], so τ ≈ 0.6–0.8).
  - Which case dominates at Bristol Candidates is untested. The first-return crown mask can measure it by counting crown cells along the decisive rays.
- **Do the tool's opaque and open surfaces bracket the truth?** Yes. Opaque uses the leaf-off first-return envelope, open the leaf-off last return. The true first sun and Last sun lie between them, nearer opaque where a ray crosses two or more crowns.
- **Cheap improvement over either binary:** give each crown crossing a transmittance of about 0.5, the SOLWEIG value and the middle of the measurements. Multiply along the ray, and count the sun as visible when the product is at least a threshold. A threshold of 0.5 would mean "at most one bare crown in the way"; that cut-off is a product decision. This needs the crown mask (first return − DTM > 2 m, from the prototype) in the profile build, plus a crossing count per azimuth and elevation step.
- **Species-specific values are not justified** by this evidence: lime, horse chestnut and birch all measured about 0.5. The exceptions are marcescent beech, hornbeam and young oak, and dense pollarded or epicormic limes. Both are closer to opaque, but neither is quantified.

**Confidence.**
- Moderate that one bare crown passes about 0.4–0.6 of the direct beam at 15–35° elevation (three full-text or abstract sources, five species, two countries).
- Low to moderate for 0–10°, where no measurement exists.
- The conditional verdict rests on geometry and should be checked against the tool's own profiles: count how many first-return crown cells, and how many separate crowns, the decisive rays cross at the Candidates that shift by 5 min or more.

## References

1. Larsson, A. (2011). *Stadsträds transmissivitet av direkt solstrålning: En studie i fyra stadsträds optiska vinteregenskaper för en del av en hållbar klimatplanering.* Degree project, SLU (Swedish University of Agricultural Sciences). <https://stud.epsilon.slu.se/3175/1/larsson_a_110830.pdf> **[full]** Results §5.1 and Table 4, p. 29–36; SOLWEIG 2.2 default p. 22; literature p. 15.
2. Konarska, J., Lindberg, F., Larsson, A., Thorsson, S., Holmer, B. (2014). Transmissivity of solar radiation through crowns of single urban trees: application for outdoor thermal comfort modelling. *Theoretical and Applied Climatology*. doi:10.1007/s00704-013-1000-3. **[abstract]** (closed access; OpenAlex lists no OA copy).
3. Heisler, G.M. (1986). Effects of individual trees on the solar radiation climate of small buildings. *Urban Ecology* 9, 337–359. <https://research.fs.usda.gov/treesearch/34772> **[full]** Table I, Table II, p. 345–352.
4. Federer, C.A. (1971). Solar radiation absorption by leafless hardwood forests. *Agricultural Meteorology*. **[abstract]**
5. Takenaka, A. (1987). Analysis of light transmissivity of forest canopies with a telephoto method. *Agricultural and Forest Meteorology*. **[abstract]**
6. Baldocchi, D., et al. (1984). Seasonal variations in the radiation regime within an oak–hickory forest. *Agricultural and Forest Meteorology*. **[abstract]**
7. Kumakura, E., et al. (2011). Numerical analysis of solar shading ratio of a deciduous tree for seasonal change. Conference paper; venue not confirmed. **[abstract]**
8. UMEP-dev/UMEP-processing, commit a7798db1698c29fa5ba667e082e7ad564c20e8e8: `functions/SOLWEIGpython/Solweig_run.py` (lines about 500–521: leaf-on window, `psi = leafon * transVeg`, `psi[leafon == 0] = 0.5`) and `processor/parametersforsolweig.json` (`Tree_settings`: Transmissivity 0.03, Trunk_ratio 0.25, First_day_leaf 97, Last_day_leaf 300). **[code]**
9. Solar Pathfinder. *Instruction Manual for the Solar Pathfinder*, "Thumb rules" and "Specific aspects of PV system siting and sizing". Copy at <https://blogs.uoregon.edu/bakerlightinglab/files/2014/12/Solar-Pathfinder-manual-177xzf8.pdf> **[full]**
10. Simpson, J.R., McPherson, E.G. (1996). Potential of tree shade for reducing residential energy use in California. *Journal of Arboriculture* 22(1). <https://research.fs.usda.gov/download/treesearch/61736.pdf> **[full]** Citing McPherson, E.G. (1984), Planting design for solar control, in *Energy Conserving Site Design*, ASLA, 141–164.
11. ENVI-met help centre, "Simple vegetation". <https://help.envi-met.com/en/articles/378942-simple-vegetation> **[full]**
12. Wagar, J.A., Heisler, G.M. (1986). Rating winter crown density of deciduous trees: a photographic procedure. *Landscape Journal* 5(1), 9–18. <https://lj.uwpress.org/content/5/1/9> **[abstract]**
13. Takács, Á., et al. (2016). Solar permeability of different tree species in Szeged, Hungary. *Geographica Pannonica* 20. **[abstract]**
14. Neumann, H.H., et al. (1989). Leaf area measurements based on hemispheric photographs and leaf-litter collection in a deciduous forest during autumn leaf-fall. *Agricultural and Forest Meteorology*. **[abstract]**
15. Dufrêne, E., et al. (1995). Estimation of deciduous forest leaf area index using direct and indirect methods. *Oecologia*. **[abstract]**
16. Calders, K., et al. (2018). Variability and bias in active and passive ground-based measurements of effective plant, wood and leaf area index. *Agricultural and Forest Meteorology*. doi:10.1016/j.agrformet.2018.01.029. **[abstract]** (the OA copy on ScienceDirect refused automated fetches).
17. Cantón, M.A., et al. (1994). Solar permeability of urban trees in cities of western Argentina. *Energy and Buildings*. Values via a secondary article only. **[secondhand]**; not used for leaf-off figures.
18. Heberling, J.M., et al. (2023). Not all temperate deciduous trees are leafless in winter: the curious case of marcescence. *Ecosphere*. doi:10.1002/ecs2.4410. **[abstract]**
19. Baldocchi, D., et al. (1984). Solar radiation within an oak–hickory forest: an evaluation of the extinction coefficients for several radiation components during fully-leafed and leafless periods. *Agricultural and Forest Meteorology*. **[abstract]** No coefficient values in the abstract.

Secondhand items in §4: the PV\*SOL/DGS values come from forum.valentin-software.com topic 243; the EnergyPlus/McPherson schedule from unmethours.com question 23896; the Solar Pathfinder Assistant 50% from a search snippet of solarpathfinder.com/pdf/Assistant_Eco_demo_report.pdf.

Elevations in §1 and §2 were computed with the NOAA approximation for the stated dates and time windows (Göteborg 57.69°N 11.97°E, 2011, CET; State College 40.8°N 77.86°W, solar time; Bristol 51.46°N 2.6°W, 2026).
