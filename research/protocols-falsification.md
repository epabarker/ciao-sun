# Do full texts falsify Protocols' morning-light claims?

Research for [#9](https://github.com/epabarker/daylight-viewing/issues/9) (map [#2](https://github.com/epabarker/daylight-viewing/issues/2)). It re-examines the *Protocols* cross-check in the earlier [morning-light research](https://github.com/epabarker/daylight-viewing/blob/research/morning-light/research/morning-light.md) ([#3](https://github.com/epabarker/daylight-viewing/issues/3)) under a different standard.

**Terms.** `GLOSSARY.md` is not in the repo, so terms follow `README.md` / `HANDOFF.md` and #3: **Morning light**, **Nominal sunrise**, **Candidate**, **Horizon profile**, **Clear window**.

**Copyright.** The book is paraphrased throughout. No book text is reproduced. Claims are located by protocol name and endnote key only.

## The standard

The user treats Andrew Huberman's *Protocols* as the source of truth. A claim **stands unless full-text primary evidence falsifies it**.

- Speculative support counts if nothing contradicts it. That includes animal studies, retinal circuitry, modelling and mechanism.
- Being unproven, untested in humans, or poorly cited is **not** a reason to downgrade a claim.
- A null result falsifies a claim only when two things are true: the study tested the claim directly (same population, timing, setting, stimulus and outcome), and it had the power to detect the effect.

Verdicts:

- **Falsified**: a specific full-text result contradicts the claim.
- **Not falsified, supported**: full-text evidence is consistent with the claim. Each row marks the support as *strong* (replicated, or direct measurement) or *speculative* (animal, anatomy, modelling, mechanism or indirect).
- **Not falsified, untested**: no full text tests the claim either way.
- **Not assessable**: the full text that would decide the claim could not be obtained.

## TL;DR

1. **No morning-light claim in scope is falsified by a full text.** 18 sub-claims were assessed: 17 have verdicts based on full texts, and 1 is not assessable.
2. **Low sun and light quality: #3's "not supported" verdict does not hold under this standard.**
   - The human tests used against the book are both evening or night studies, at room-level light, with about 16 people each. Their primary outcomes were inconclusive by their own Bayes-factor criteria: Spitschan 2019 BF 0.71, Blume 2024 BF 0.3.
   - Blume 2024 explicitly leaves twilight and morning untested.
   - Brown 2020 says its melanopic-only conclusion "awaits definitive confirmation" for morning light. Its phase-shift data even leave a residual that it attributes to a possible L/M-cone or blue–yellow effect.
   - The claim is **not falsified, with speculative support**. That support comes from primate wiring, a mouse colour-entrainment study and sunlight modelling.
3. **#3's "spectral correction" is reversed.** #3 said whole-sky light around sunrise is blue-enriched (Spitschan 2016). On full reading, that blue shift mainly happens in twilight, below the horizon, and was measured with an upward-facing horizontal sensor. Woelders 2018 measured from all directions, which is closer to what an eye receives. It found clear-sky light at low sun (0–30°) is relatively **yellow**, because the direct beam dominates. Cloud shifts it bluer. That is what the book says.
4. **#3 conflated two windows.**
   - The book's "closes after the first hour" claim is about **cortisol**, not phase advance.
   - On cortisol, the full texts are consistent with the book. Light raises cortisol near waking and in the early morning, and has no effect or lowers it later in the morning. The exact 60-minute cut-off is untested.
   - The "+50%" figure is phrased as an upper bound ("as much as"). It is consistent with the bright-versus-dim differences of about 40–50% summarised in the book's own systematic-review citation.
5. **Implications for the tool.**
   - Keep the melanopic dose as the backbone.
   - **Add back** low sun with the sun disc in view on a clear morning as a "book quality" bonus, labelled as untested.
   - Use the book's 10/20/30-minute targets by cloud class.
   - Weight the first hour after waking most heavily.
   - Count only outdoor minutes.

## Claims, verdicts and evidence

Locations are protocol names. SP = Sleep Protocol, LP = Light Protocol, SCP = Stress Control Protocol, Ch5 intro = the Chapter 5 introduction. "Notes" are the endnote keys in the user's copy.

### A. Low sun angle and light quality

| # | Claim (paraphrased) | Location; notes | Verdict | Full-text evidence |
|---|---|---|---|---|
| A1 | The sun's direct beam looks yellow or orange at low elevation because the atmosphere scatters out short wavelengths. | SP1 "Your Eyes"; Ch5 intro; LP2. Uncited | **Not falsified, supported (strong, physics)** | Woelders 2018: the high-intensity direct beam "causes a long-wavelength shift" in the spectrum just after sunrise. The shift reverses as the sun climbs. |
| A2 | On a clear morning with the sun low, light reaching the eyes is long-wavelength-weighted. Dense cloud removes much of the longer-wavelength light and reduces yellow–blue contrast. | Ch5 intro; SP1 Q&A ("What if it's cloudy"). Uncited | **Not falsified, supported (strong, direct measurement)** | Woelders 2018 (sensor that collects light from all directions, 100 days, Groningen): clear skies are relatively yellow compared with overcast ones, especially at 0–30°. More cloud means bluer light, most strongly at 0–12°. Shorter wavelengths are less attenuated by cloud than longer ones. The authors warn that horizontal sensors underestimate low-sun yellowness. Spitschan 2016 used such a sensor, and its strongest blue shift is in twilight (bluest at −6° to −12°). **This reverses #3's "spectral correction".** |
| A3 | The ipRGCs that set the clock carry a blue-versus-yellow colour-opponent cone signal. | SP1 "Your Eyes"; Ch5 intro. ch01en_35, ch01en_40 (Patterson 2022; Rivera & Huberman 2020) | **Not falsified, supported (strong anatomy, macaque)** | Patterson 2020: primate ipRGCs are "yellow-ON, blue-OFF", and the paper identifies the S-cone amacrine cell that inverts the S-cone signal. Patterson 2022 suggests the orange sky at sunrise gives "strong decrements" in short wavelengths that this S-OFF input could detect. Rivera & Huberman 2020 call M1 ipRGCs detectors of yellow–blue contrast. #3 said the book "merges opposite-signed signals". The cited sources describe the cell the same way the book does, so **that critique is withdrawn.** |
| A4 | The ipRGC-to-clock circuit is tuned to low-solar-angle sunlight. Its best stimulus is bright blue/green light contrasted with yellow/orange, so sunrise and sunset colour contrast tells the clock the time. | SP1 "Your Eyes"; SP1 "How it works"; Ch5 intro. ch01en_34, ch01en_35, ch01en_40 | **Not falsified, supported (speculative)** | **Support.** Patterson 2020/2022 propose this function. Woelders 2018 shows that colour plus intensity predicts solar angle better than intensity alone, especially at 0–20°, and under cloud. Walmsley 2015 (mice): SCN neurons are colour-opponent, and simulated twilight colour changes were needed for normal alignment. Brown 2020: in the only multi-intensity spectral phase-shift dataset (Gooley 2010), melanopic illuminance did *not* fully account for the shifts. Brown attributes the gap to L/M cones, or to S-cones inhibiting the response at low intensities, or to a blue–yellow effect. **Counter-tests fail the falsification bar.** Spitschan 2019: n=15, evening, about 170 lux, S-cone-only modulation, melatonin BF 0.71 (inconclusive). Blume 2024: n=16, starting 30 min after habitual bedtime, about 94 lux, 1 Hz blue–yellow flicker. Its primary phase-shift BF was 0.3, which is inconclusive by its own ≥10 criterion. Its design analysis gave only 62% power for a large effect. Its melatonin-suppression BF of 0.09 is strong evidence against an effect *at night at room light*. That is a different timing, intensity and outcome from sunrise entrainment, and the authors call for tests "during the twilight hours". Brown 2020 says its melanopic conclusion for morning light "awaits definitive confirmation". **Untested in humans in the morning or outdoors. #3's "not supported" verdict changes.** |

### B. Timing: the first hour after waking and cortisol

| # | Claim (paraphrased) | Location; notes | Verdict | Full-text evidence |
|---|---|---|---|---|
| B1 | Get sunlight as soon as possible after waking, ideally within 30–60 minutes. Seeing sunrise isn't needed. If you wake before sunrise, wait for it. | SP1; LP1. ch01en_51 (Wright 2013) | **Not falsified, supported (strong for direction)** | Khalsa 2003 (n=21, 6.7 h at about 10,000 lux) found advances once light was centred after the core body temperature minimum, which falls before habitual waking. It found "no evidence" of a dead zone. St Hilaire 2012 found the same shape for 1 h pulses at about 8,300 lux (n=18). Wright 2013 describes the first 2 h after waking as the period of greatest sensitivity to advancing light. These are lab-lamp studies. Whether the *first* hour is the most effective has not been tested directly, and nothing contradicts it. |
| B2 | Morning light amplifies the cortisol rise after waking (the cortisol awakening response). | SP1; LP1; SCP5. ch01en_59, ch01en_60, ch03en_122, ch03en_124, ch05en_21 | **Not falsified, supported (moderate)** | Robertson-Dixon 2023 (systematic review, 12 studies, cited at ch03en_124): bright light of any colour significantly raised cortisol relative to dim light only when measured between 21:00 and 09:00. Mekschrat 2024, a sleep-lab study from Petrowski's group (n=71 men, woken at 05:00, 60 min of light), found the CAR under both red and blue light. Total cortisol output was higher under blue, but mean cortisol did not differ. The book's primary sources, Petrowski 2019 and Leproult 2001, could not be obtained (see method note). |
| B3 | Morning light can boost the cortisol peak by up to about 50%. | SP1; SCP5. ch01en_60 (Leproult 2001) | **Not falsified, supported (moderate)** | Robertson-Dixon 2023: bright-versus-dim cortisol ranged from 114% to 174%, typically about 140–150%. Leproult's full text was unobtainable. #3's objection (the study used 3 h of light in sleep-deprived men) rests on the abstract. "As much as" is an upper bound, which a smaller mean does not falsify. |
| B4 | The light-driven cortisol boost happens only in about the first 60 minutes after waking. If you miss it, it's gone for the day. | LP1 "Natural cortisol cycle"; Ch5 intro. ch05en_28 (mechanism: SCN–sympathetic–adrenal, including mouse data) | **Not falsified, supported (speculative/indirect)**; exact cut-off untested | **Indirect support for a narrow early window.** Robertson-Dixon 2023: brief light exposures had no significant cortisol effect from late morning to evening. Choi 2019 (n=15, 500 lux, 10:00–11:00): cortisol fell under both lights, and the authors say the light came "too late" to induce a cortisol response. Jung 2010 (n=20, 6.7 h at 10,000 lux): prolonged light during the falling phase *lowered* cortisol from about 1 h after onset. Jung also reports that Scheer & Buijs 1999 saw a rise in the first 40 min of light at habitual wake time, back to baseline by 1 h. Scheer & Buijs is cited second-hand only. No full text compares light starting at waking with light starting 60–90 min later. **#3 argued against this with phase-advance data (Khalsa and St Hilaire). That is the wrong outcome, so its objection is withdrawn.** |
| B5 | The cortisol peak comes about an hour after waking (SP1), or somewhere between 30 min and 3 h (LP1). | SP1; LP1. ch01en_58 | **Not falsified** (approximate) | The full texts that state it put the CAR peak at about 30–45 min after waking, citing others (Robertson-Dixon 2023; Mekschrat 2024). That lies inside LP1's range. SP1's "about an hour" is at the late end. |

### C. Duration and cloud

| # | Claim (paraphrased) | Location; notes | Verdict | Full-text evidence |
|---|---|---|---|---|
| C1 | Minimum time outdoors: clear, at least 5–10 min (SP1) or 10 (LP1). Cloudy, at least 15 (SP1) or partly cloudy at least 20 (LP1). Densely overcast, at least 30. Using a 10,000 lux lamp beforehand halves the time. Some light is better than none. | SP1 Q&A; LP1 Q&A. Uncited | **Not falsified, untested**; speculative support | No full text tests outdoor morning durations. Chang 2012 (night, lab, about 7,700 lux): 12 min produced a 1.07 h phase delay, so short bright exposures can act. Woelders 2018: cloud cuts melanopic photons by about 0.08 log units per okta, so needing more time under cloud fits. **The book is internally inconsistent: SP1 says 5–10/15/30, LP1 says 10/20/30.** |
| C2 | Even overcast skies deliver useful daylight. Sparse cloud doesn't interfere. Overcast days matter more. | SP1 Q&A; LP1; LP4. Uncited | **Not falsified, supported (strong for the light levels)** | Woelders 2018: the loss is graded at about 0.08 log per okta, so a few oktas cost little. Tabandeh 2026: outdoor melanopic EDI (mean 12,142 lx) is far above windowless indoor (280 lx). "Overcast days matter more" is behavioural reasoning and is untested. |

### D. Windows, glasses and sunglasses

| # | Claim (paraphrased) | Location; notes | Verdict | Full-text evidence |
|---|---|---|---|---|
| D1 | Light through windows or windshields is far less effective, though better than nothing. Go outside. | SP1 Q&A; LP1 Q&A; LP4. Uncited | **Not falsified, supported (field measurement)** | Tabandeh 2026 (671 scenes): mean melanopic EDI was 2,386 lx indoors with a window view against 12,142 lx outdoors, about 5 times lower. These are scene measurements, not circadian outcomes. |
| D2 | The reason is that glass filters the relevant wavelengths, especially short ones, and especially modern glass. | SP1 Q&A | **Not assessable** | Glazing-specific spectral studies exist (Sánchez-Cano 2024; Hraška 2022; Stebelová 2023 on blue-blocking glazing), but their full texts could not be obtained (403 errors). Tabandeh 2026 found melanopic and photopic illuminance tightly coupled (r > 0.98) in windowed scenes. That points to a mostly quantity-based loss, but it does not isolate the glass, so it decides nothing. |
| D3 | Don't wear sunglasses or transition lenses; they block photons and relevant wavelengths. Ordinary glasses and contact lenses are fine. | SP1 Q&A; LP1. Uncited | **Not falsified, supported (mechanistic)** | Brown 2020: light at the cornea, weighted by melanopic sensitivity, is the best predictor of human circadian responses. Sunglasses cut corneal light; clear lenses barely do. No direct outdoor sunglasses trial was read in full. |

### E. Geometry: facing the sun, sky and disc

| # | Claim (paraphrased) | Location; notes | Verdict | Full-text evidence |
|---|---|---|---|---|
| E1 | Face toward the sun with no awnings or buildings in the way. East on a clear morning activates the system fastest. You need light in your eyes, not a view of the sun, and seeing sunrise is a bonus. Never stare at the sun. | SP1; SP2; LP1. Uncited | **Not falsified, supported (physics); circadian effect of the disc untested** | Woelders 2018: on clear days at low sun, the direct beam dominates the light arriving from all directions and makes it yellow. The book's "special" stimulus (A2/A4) therefore depends on the direct sun being in view, while the dose does not require it. No study compares disc-in-view with sky-only outdoor exposure. |
| E2 | Melanopsin cells sit mostly in the lower retina, which views the sky, so a brimmed hat blocks overhead light. | SP1 "Your Eyes"; LP1. ch01en_38 (Provencio 2000, 2002) | **Not falsified, supported (speculative, anatomy)** | Provencio 2000 (full text) does not address where in the retina the cells sit. Esquiva 2017 mapped one whole human retina and found the lowest melanopsin-cell density in the *superior* retina, which is consistent with the book. Glickman 2003 (inferior retina more effective for melatonin suppression) could not be obtained, so it is not relied on. |

### F. Red and near-infrared light

| # | Claim (paraphrased) | Location; notes | Verdict | Full-text evidence |
|---|---|---|---|---|
| F1 | Red (670 nm) light to the eyes improves colour vision in people over about 40, but only when given in the morning, within about 1–3 h of waking. | LP5 "How it affects your eyesight". ch05en_96, ch05en_97 | **Not falsified, supported (weak, device study)** | Shinhmar 2021: one 3-min exposure at 08:00–09:00 at 8 mW/cm² cut colour-contrast thresholds by 17% (tritan) and 12% (protan) 3 h later (n=20, aged 34–70). The effect lasted a week (n=10). Exposure at 12:00–13:00 had no effect, but n=6, so that null is underpowered. Timing was by clock, not hours since waking. |
| F2 | The sun is a rich source of long wavelengths, with less on overcast days. UV is lower when the sun is low. | LP5 "Sources"; LP4. ch05en_19 (Jeffery 2025) | **Not falsified, supported (speculative)** | Jeffery 2025: solar near-infrared passes through the human chest. This was measured at midday. A 15-min 850 nm LED to the back improved colour contrast 24 h later, even with the eyes shielded. Spitschan 2016: UV falls with solar elevation in the same way visible light does. No study tests a vision or health benefit from *low-sun* light. At low elevation the beam is relatively red but its absolute intensity is lower than at midday. |

### Out of scope, noted for honesty

Sleep Protocol 4 paraphrases Wright 2013 as campers going to sleep around sunset. The full text says *melatonin onset* came near sunset, while sleep start moved only about 1.2 h earlier, from about 00:30. That detail is contradicted, but it is not a morning-light claim. The rest of that passage matches the full texts: about 4 times more light, and a weekend reaching about 69% of a week's shift (Wright 2013; Stothard 2017).

## What changed from #3, and why

| Topic | #3 conclusion | Now | Why |
|---|---|---|---|
| Low sun and light quality (A4) | Not supported; don't model | **Not falsified (speculative support); untested in humans in the morning** | Standard change. On full reading, the human counter-tests are evening or night, at room-level light, with inconclusive primary Bayes factors. Brown 2020 itself leaves morning open and reports an unexplained cone or colour residual in phase-shift data. |
| The book "merges opposite-signed signals" (A3) | Mismatched citation | **Withdrawn** | Patterson 2020/2022 and Rivera & Huberman 2020 describe ipRGCs as blue–yellow contrast detectors, which matches the book's description. |
| Sunrise light is blue-enriched, so the warm part is less melanopic (A2) | Added as a "spectral correction" | **Reversed for the sun-up period** | Spitschan 2016's blue shift is mostly below the horizon and uses a horizontal sensor. Woelders 2018 measured light from all directions and found clear low-sun light yellow, and cloud bluer, as the book says. Melanopic-per-lux is lower in yellow light, but that is not a claim the book makes. |
| Petrowski: red light was the weaker cortisol stimulus | Counted against warm light | **Irrelevant** | The book never claims red light alone is the better cortisol stimulus. Mekschrat 2024, from the same group, found no difference in mean cortisol between red and blue light. Petrowski 2019 itself was not obtained. |
| "+50%" from Leproult doesn't transfer (B3) | Number doesn't transfer | **Not falsified** | The objection was abstract-based, and "as much as" is an upper bound. The book's own systematic review reports typical bright-versus-dim differences of about 40–50%. |
| Cortisol window "closes" after an hour (B4) | Uncited; phase advance continues | **Not falsified; indirect support** | #3 judged a cortisol claim against phase-advance outcomes. The cortisol data support an early, narrow window. |
| Inferior retina (E2) | Right in direction, wrong citation; Glickman supports | **Not falsified; Esquiva 2017 supports** | Glickman could not be obtained in full, so that support is replaced. |
| Durations, cloud, disc not required, windows, red/NIR | Uncited heuristic; agrees; agrees; mechanism overstated; outside scope | **Unchanged in direction**; the window mechanism is now *not assessable* rather than "overstated" | Uncited is not falsified. |

## Implications for the tool (book stands unless falsified)

1. **Dose stays the backbone.** Melanopic light at the eye is still the only factor tested broadly in humans. Keep open-sky exposure from the Candidate, weighted towards the eastern sector of the Horizon profile, as the primary signal.
2. **Low sun angle and light quality: model it, labelled as the book's untested factor.** The "special" stimulus the book describes is the direct low sun (yellow) against a blue sky. Woelders shows it exists physically only on clear mornings with the sun in view, at about 0–30° elevation. Give a **quality bonus** to minutes when the sun is visible above the Horizon profile, the sun is low, and the forecast sky is clear or near clear. Do **not** penalise low elevation for its lower lux. Phrase it as "Protocols' sunrise-light factor (untested in humans)", not as established science.
3. **Sun disc in view regains weight.** The book does not make the disc required: open sky still counts and still scores the dose. But the disc is what delivers the claimed quality factor (2), and the book's advice is to face the sun unobstructed. So the Clear window becomes a ranked bonus layer on top of the sky-openness score, rather than the pure "nice to have" #3 proposed. It is still not a pass/fail gate.
4. **Duration rules: use the book's targets by cloud class.** Adopt LP1's figures as targets: clear 10 min, partly cloudy 20, densely overcast 30. Use SP1's 5–10 / 15 / 30 as the "minimum" floor, and flag the inconsistency to the user. A suggested mapping is 0–2 oktas clear, 3–5 partly cloudy, 6–8 overcast. The book's "take a walk" advice and its "some is better than none" support counting **total** minutes in the window rather than the longest unbroken run. Optionally, halve the target if the user has used a 10,000 lux lamp. The cloud multiplier of 10^(−0.08 × oktas) from #3 is consistent with these targets and can stay as the dose model.
5. **First-hour window: anchor it to wake time and weight the first 60 minutes after waking most heavily.** The cortisol window claim is not falsified, so treat that hour as the book's priority window. Keep a tapering credit for later light: the phase advance continues, and the book itself says "as early in the day as possible". For Bristol in winter, if Nominal sunrise or local sun-clear time is later than wake + 60 min, the tool should say that the outdoor cortisol window is unavailable that day. The book's own fallback is a 10,000 lux lamp in the first hour, then 5–20 min outside once the sun is up. Make wake time a setting.
6. **Red/NIR: show it as an optional morning-sun bonus, not part of entrainment.** The morning-only red-light result is from a device and is not falsified. The low sun's red/NIR dose is untested and low in absolute terms. At most, label disc-visible morning minutes as also "direct sun on face (Protocols LP5)", tied to the same Clear-window bonus. Do not add a separate score.
7. **Outdoors only.** Never count minutes behind glass. Copy: no sunglasses, glasses and contacts are fine, no brimmed hat, never stare at the sun.

## Method note

- The research was done inline by the delegated agent, without a further background agent.
- Full texts came from PubMed Central through the PubMed tool, unless marked otherwise.
- For Khalsa 2003, St Hilaire 2012 and Chang 2012, the PMC article pages were read with a fetch tool that summarises pages. They were not read line by line, and figure values were unavailable.
- Brown 2020 was read on the publisher's open-access page in Chrome. About 97% of it was read; the end of the text was truncated, after the conclusions.

| Paper | Full text read? | Source |
|---|---|---|
| Blume 2024 | Yes | PMC10963261 |
| Spitschan 2019 | Yes | PMC6926470 |
| Brown 2020 | Yes (≈97%) | Wiley OA HTML via Chrome |
| Spitschan 2016 | Yes | PMC4895134 |
| Woelders 2018 | Yes | PMC6185968 |
| Patterson 2020 | Yes | PMC7141953 |
| Patterson 2022 | Yes | PMC8589871 |
| Rivera & Huberman 2020 | Yes | PMC8407369 |
| Khalsa 2003 | Yes (via fetch summary) | PMC2342968 |
| St Hilaire 2012 | Yes (via fetch summary) | PMC3406389 |
| Chang 2012 | Yes (via fetch summary) | PMC3406393 |
| Wright 2013 | Yes | PMC4020279 |
| Stothard 2017 | Yes | PMC5335920 |
| Robertson-Dixon 2023 | Yes | PMC10608196 |
| Jung 2010 | Yes | PMC3686562 |
| Mekschrat 2024 (Petrowski group; red vs blue post-waking) | Yes | PMC11381833 |
| Choi 2019 | Yes | PMC6344573 |
| Shinhmar 2021 | Yes | PMC8613193 |
| Jeffery 2025 | Yes | PMC12238558 |
| Provencio 1998, 2000 | Yes | PMC18217, PMC6772411 |
| Esquiva 2017 | Yes | PMC5378720 |
| Walmsley 2015 | Yes (abstract and discussion checked) | PMC4401556 |
| Tabandeh 2026 | Yes | PMC13486849 |
| **Leproult 2001** | **No**: OUP paywall; no OA copy (OpenAlex) | abstract only, not relied on |
| **Petrowski 2019** | **No**: Elsevier; Chrome hit a CAPTCHA; no OA copy | not relied on |
| **Glickman 2003** | **No**: SAGE, closed (OpenAlex) | not relied on |
| Scheer & Buijs 1999 | No | cited only via Jung 2010's discussion |
| Glazing papers (Sánchez-Cano 2024, Hraška 2022, Stebelová 2023) | No (403 / not retrieved) | D2 marked not assessable |
| Provencio 2002, Shinhmar 2020, Wilhelm 2007, Weitzman 1971 | Not obtained / not needed | verdicts rest on other full texts |

## References

- Blume C et al. Effects of calibrated blue–yellow changes in light on the human circadian clock. *Nat Hum Behav* 2024. https://doi.org/10.1038/s41562-023-01791-7
- Brown TM. Melanopic illuminance defines the magnitude of human circadian light responses under a wide range of conditions. *J Pineal Res* 2020. https://doi.org/10.1111/jpi.12655
- Chang AM et al. Human responses to bright light of different durations. *J Physiol* 2012. https://doi.org/10.1113/jphysiol.2011.226555
- Choi K et al. Awakening effects of blue-enriched morning light exposure on university students' physiological and subjective responses. *Sci Rep* 2019. https://doi.org/10.1038/s41598-018-36791-5
- Esquiva G et al. Loss of melanopsin-expressing ganglion cell subtypes and dendritic degeneration in the aging human retina. *Front Aging Neurosci* 2017. https://doi.org/10.3389/fnagi.2017.00079
- Jeffery G et al. Longer wavelengths in sunlight pass through the human body and have a systemic impact which improves vision. *Sci Rep* 2025. https://doi.org/10.1038/s41598-025-09785-3
- Jung CM et al. Acute effects of bright light exposure on cortisol levels. *J Biol Rhythms* 2010. https://doi.org/10.1177/0748730410368413
- Khalsa SBS et al. A phase response curve to single bright light pulses in human subjects. *J Physiol* 2003. https://doi.org/10.1113/jphysiol.2003.040477
- Patterson SS et al. A color vision circuit for non-image-forming vision in the primate retina. *Curr Biol* 2020. https://doi.org/10.1016/j.cub.2020.01.040
- Patterson SS, Neitz M, Neitz J. S-cone circuits in the primate retina for non-image-forming vision. *Semin Cell Dev Biol* 2022. https://doi.org/10.1016/j.semcdb.2021.05.004
- Mekschrat L, Schmalbach B, Rohleder N, Petrowski K. IL-6 after wake-up in human males: exposure to red versus blue light and the interplay with cortisol. *Brain Behav Immun Health* 2024. https://doi.org/10.1016/j.bbih.2024.100833
- Provencio I et al. Melanopsin: an opsin in melanophores, brain, and eye. *PNAS* 1998. https://doi.org/10.1073/pnas.95.1.340
- Provencio I et al. A novel human opsin in the inner retina. *J Neurosci* 2000. https://doi.org/10.1523/JNEUROSCI.20-02-00600.2000
- Rivera AM, Huberman AD. A chromatic retinal circuit encodes sunrise and sunset for the brain. *Curr Biol* 2020. https://doi.org/10.1016/j.cub.2020.02.090
- Robertson-Dixon I et al. The influence of light wavelength on human HPA axis rhythms: a systematic review. *Life* 2023. https://doi.org/10.3390/life13101968
- Shinhmar H et al. Weeklong improved colour contrasts sensitivity after single 670 nm exposures associated with enhanced mitochondrial function. *Sci Rep* 2021. https://doi.org/10.1038/s41598-021-02311-1
- Spitschan M et al. Variation of outdoor illumination as a function of solar elevation and light pollution. *Sci Rep* 2016. https://doi.org/10.1038/srep26756
- Spitschan M et al. No evidence for an S cone contribution to acute neuroendocrine and alerting responses to light. *Curr Biol* 2019. https://doi.org/10.1016/j.cub.2019.11.031
- St Hilaire MA et al. Human phase response curve to a 1 h pulse of bright white light. *J Physiol* 2012. https://doi.org/10.1113/jphysiol.2012.227892
- Stothard ER et al. Circadian entrainment to the natural light-dark cycle across seasons and the weekend. *Curr Biol* 2017. https://doi.org/10.1016/j.cub.2016.12.041
- Tabandeh N et al. Photoreceptor-specific scene statistics reveal melanopic structure in natural environments. *iScience* 2026. https://doi.org/10.1016/j.isci.2026.116661
- Walmsley L et al. Colour as a signal for entraining the mammalian circadian clock. *PLoS Biol* 2015. https://doi.org/10.1371/journal.pbio.1002127
- Woelders T et al. Integration of color and intensity increases time signal stability for the human circadian system when sunlight is obscured by clouds. *Sci Rep* 2018. https://doi.org/10.1038/s41598-018-33606-5
- Wright KP et al. Entrainment of the human circadian clock to the natural light-dark cycle. *Curr Biol* 2013. https://doi.org/10.1016/j.cub.2013.06.039

Not obtained in full: Leproult R et al. *J Clin Endocrinol Metab* 2001 (https://doi.org/10.1210/jcem.86.1.7102); Petrowski K et al. *Psychoneuroendocrinology* 2019 (https://doi.org/10.1016/j.psyneuen.2019.05.016); Glickman G et al. *J Biol Rhythms* 2003 (https://doi.org/10.1177/0748730402239678).

Bibliographic data and full texts via PubMed / PubMed Central unless noted.
