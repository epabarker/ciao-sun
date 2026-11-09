# What Morning light matters for circadian entrainment?

Research for [#3](https://github.com/epabarker/daylight-viewing/issues/3) (map [#2](https://github.com/epabarker/daylight-viewing/issues/2)). Findings are binding on the sunspot Stage 1 spec.

Terms: **Morning light**, **Nominal sunrise** (the first minute the sun's apparent elevation exceeds -0.833° at the home coordinate, i.e. sunrise over a flat horizon), **Candidate**, **Horizon profile**, **Clear window** (an unbroken run of minutes during which the sun clears the Horizon profile). `GLOSSARY.md` was not in the repo when this was written, so the definitions follow `README.md` / `HANDOFF.md`.

Sources are peer-reviewed papers retrieved via PubMed and Consensus. Each claim is graded:

- **Strong**: replicated, or an expert consensus built on many controlled studies.
- **Moderate**: one well-controlled study, or consistent field and cohort data.
- **Weak**: small n, an animal model, modelling, or extrapolation from a different context (for example evening light applied to morning).
- **Unsourced**: standard background I could not pin to a source in this pass.

## TL;DR

1. **What counts is how much light reaches the eye (melanopic illuminance), not its colour or where the sun sits.** Melanopic equivalent daylight illuminance (EDI) at the eye is the best predictor of human circadian responses. Once you correct for melanopic content, the evidence in humans does not support a separate effect of colour or "sunrise quality". The user believes sun position and light quality matter as much as intensity. That belief is **not supported**: it rests on mouse work and modelling, and a direct human test of an S-cone contribution was negative.
2. **The sun's disc does not need to be in view.** Being outdoors under open sky after sunrise already gives a melanopic EDI far above indoor levels and above the 250 lx daytime recommendation. The response saturates, so direct sun adds less than its lux suggests. Open sky (low obstruction overhead and in the direction you face) probably matters more than whether the disc itself is visible.
3. **The timing that matters is relative to the person's body clock, which tracks their waking time, not Nominal sunrise.** Light after the core body temperature minimum advances the clock. There is no long "dead zone" in the morning. The earlier in the advance region, the larger the effect. Sunrise only decides when outdoor light becomes available.
4. **Duration: short exposures are disproportionately effective, and broken-up minutes add up.** Twelve minutes of bright light produced about 40% of the phase shift that 4 h produced. Intermittent light is nearly as effective as continuous light. Total minutes in the window matter more than the longest unbroken Clear window.
5. **Cloud reduces the effect but does not cancel it.** Going from clear sky to full overcast cuts melanopic photons about 4 to 5 times, on average. Outdoor overcast light still sits well above indoor light and the 250 lx recommendation, so cloud should scale a result down, not remove it.

## 1. What the circadian system responds to

- **Melanopic EDI at the eye is the metric.** A re-analysis of 19 human lab studies (melatonin suppression, phase resetting, alerting) found that melanopic illuminance "consistently provides the best available predictor". It "is able to fully account for differences in sensitivity to stimuli of varying spectral composition", across the range met over civil twilight (~1 to 1000 lx melanopic EDI). Brown 2020 [1]. **Strong.**
- **Expert consensus for daytime** is a minimum melanopic EDI of 250 lx at the eye, measured in the vertical plane at about 1.2 m. Daylight should be used first. Brown et al. 2022 [2], a consensus built on the CIE S 026 standard. **Strong** as a consensus target. It is a floor for indoor lighting, not a measured threshold for morning entrainment.
- **The underlying receptor** is melanopsin in intrinsically photosensitive retinal ganglion cells (ipRGCs), peak ~480 to 490 nm. Rods and cones also feed in. Lucas et al. 2014 [3]. **Strong.**
- **No S-cone or colour effect has been shown in humans.** Stimuli that differed 83-fold in S-cone excitation, with melanopsin, rods and L/M cones held constant, produced no difference in melatonin suppression or alertness. Spitschan et al. 2019 [4]. **Moderate.** This was evening light and acute responses, not phase shifting.

## 2. Timing: relative to waking or to Nominal sunrise?

- **The phase response curve (PRC).** Bright light centred before the core body temperature minimum (CBTmin) delays the clock. Light centred after it advances the clock. There is no shift at CBTmin itself and "no prolonged 'dead zone'" during the subjective day. Khalsa et al. 2003 [5] (n=21, 6.7 h at ~10,000 lx). This replicates Minors et al. 1991 [6]. A 1 h PRC (~8000 lx) has the same Type 1 shape at about 40% of the amplitude. St Hilaire et al. 2012 [7]. **Strong.**
- **Where CBTmin sits relative to waking.** In entrained adults CBTmin usually falls about 2 to 3 h before habitual wake time, so light from waking onwards falls in the advance region. The advance it gives is largest early and tapers through the morning. **Unsourced in this pass.** It is standard chronobiology background, but I did not retrieve a primary source. Treat the exact offset as a parameter, not a constant.
- **Field interventions put light right after waking.** In Revell et al. 2006 [8], bright light delivered on waking (4 × 30 min at ~5000 lux, alternating with room light) plus an advancing sleep schedule advanced rhythms by ~1.7 h over 3 days without melatonin. In Crowley et al. 2024 [9], light-box exposure "within 5 minutes of waking" maintained an earlier phase. **Moderate.**
- **Under natural light, the body clock locks to the sun.** After a week camping with only natural light, internal biological night ended "before wake time just after sunrise", and later chronotypes shifted most. Wright et al. 2013 [10]. The same pattern held in winter, and a weekend achieved ~69% of a week's shift. Stothard et al. 2017 [11]. Population chronotype tracks sun time within a time zone. Roenneberg et al. 2007 [12]. **Strong** that sunrise sets the schedule when someone lives under natural light. In modern indoor life, phase is later than sunrise, so the person's wake time, not sunrise, is the better anchor for their PRC.
- **Bristol in winter:** sunrise ~08:15. For someone waking at ~07:00, the first ~75 min of their advance window has no outdoor sun. Morning light from sunrise onwards is still in the advance region, but later than the ideal time. The useful window does not end an hour after sunrise. The PRC shows advances continuing for several hours after CBTmin with diminishing returns. Inference from [5][7]. **Moderate.**
- **Evening light can wipe out morning gains.** In adolescents, extra late-evening room light plus restricted sleep turned morning-bright-light advances into delays. Monterastelli et al. 2026 [13]. **Moderate.** This is outside the tool's scope, but worth one line of copy.

## 3. Duration and dose-response

- **Duration response is non-linear.** Per minute, 0.2 h (12 min) of ~10,000 lux was over 5 times as effective as 4 h: 1.07 h versus 2.65 h of phase delay. Chang et al. 2012 [14]. A 1 h pulse gave ~40% of the 6.7 h PRC amplitude with 15% of the exposure. St Hilaire et al. 2012 [7]. **Strong.** Note that Chang measured delays (evening light). The morning duration response has not been characterised as carefully.
- **Intermittent light works.** Intermittent bright light at 31% to 63% of the continuous dose produced "almost as great a resetting response" as 5 h continuous, with "enhanced sensitivity to the initial minutes". Rimmer et al. 2000 [15]. Six 15-min pulses (23% of the dose) matched 6.5 h continuous. Gronfier et al. 2004 [16]. **Strong.**
- **Intensity response saturates.** For evening light, half the maximal phase delay and melatonin suppression came from ~100 lux, about 1% of 9000 lux. Zeitzer et al. 2000 [17]. Half-maximal melatonin suppression averaged ~25 lux, but individuals ranged from 6 to 350 lux. Phillips et al. 2019 [18]. **Strong for evening.** The morning version is **weak**: it is extrapolation, and it is in photopic lux rather than melanopic EDI.
- **Prior light history changes sensitivity.** A week of dim days made people more sensitive to light. Hébert et al. 2002 [19]. **Moderate.** Winter indoor life probably raises the marginal value of any morning outdoor light.
- **There is no evidence-based minimum duration for outdoor morning light.** Popular advice such as "10 min if clear, 30 min if overcast" has no primary source that I found. The lab data say that even ~10 to 15 min of bright light has a measurable effect, and that more helps with diminishing returns.

## 4. Intensity outdoors versus indoors; direct sun versus open sky

- **Outdoor versus indoor.** Across 671 measured scenes, mean melanopic EDI was 280 lx in windowless rooms, 2386 lx indoors with a window, and 12,142 lx outdoors. Tabandeh et al. 2026 [20]. **Moderate.**
- **Light at sunrise.** Melanopic EDI already reaches ~1000 lx by the end of civil twilight. Brown 2020 [1]. Total irradiance rises sigmoidally with solar elevation and fastest through twilight. Spitschan et al. 2016 [21]. So at Nominal sunrise, open sky already gives about 4 times the 250 lx floor, and the level climbs quickly over the next hour. **Moderate.** The ~1000 lx figure is an approximate range boundary, not a measurement for Bristol.
- **Sun's disc in view.** No human study I found compares disc-visible with disc-obscured outdoor exposure at the same location. The mechanism (melanopic EDI at the cornea) means the disc matters only through how much it adds to vertical illuminance at the eye. That is large when facing a low clear sun and nothing when facing away. Given saturation, direct sun adds less than its lux suggests once open sky already gives ≥1000 lx. Light from above (the sky) lands on the inferior retina, which was more effective than the superior retina for melatonin suppression. Glickman et al. 2003 [22] (n=9, nocturnal). **Weak.** Overall: the disc is not required. **Moderate** (from mechanism, with no direct test).
- **Safety:** never look directly at the sun. Solar retinopathy is a real risk. The tool should never suggest gazing at the sun, only being in view of it or of open sky.

## 5. Sun position and light quality (testing the user's belief)

- **Spectrum does change with elevation.** As solar elevation falls, sky light becomes relatively richer in short wavelengths. It is bluest during nautical twilight (~-6° to -12°) and shifts back towards red near and just above the horizon. Spitschan et al. 2016 [21]. On sunny days, chromaticity shifts from blue to yellow-orange in the early morning. Yu et al. 2024 (conference abstract) [23]. **Strong** for the physics.
- **Colour as a timing signal is shown in mice, not humans.** The mouse SCN shows cone-dependent blue-yellow opponency, and simulated twilight colour changes were needed for normal alignment. Walmsley et al. 2015 [24]. **Moderate in mice, weak for humans.** Woelders et al. 2018 [25] argue from 100 days of spectra that combining colour and intensity *could* stabilise a human timing signal under cloud. That is **weak**: a modelling hypothesis, not a measured human response.
- **Human test is negative.** No S-cone contribution was found [4], and melanopic EDI alone explains spectral differences across 19 studies [1].
- **Verdict:** the claim that sun elevation and light quality matter as much as intensity is **not supported**. For a fixed melanopic EDI, a low red sun has no extra benefit. If anything, reddened direct light is *less* melanopic per photopic lux. Elevation matters only through how much light it delivers, and that is large.

## 6. Overcast and cloud

- **Size of the effect.** Each extra okta of cloud cut melanopic photons by 0.08 ± 0.03 log units. Woelders et al. 2018 [25], 100 days of measurements in the Netherlands. Clear sky to full overcast (8 oktas) is therefore ≈0.64 log, a **~4 to 5 times reduction**. Cloud also shifts sky colour bluer, most strongly at solar angles of 0° to 12°. **Moderate.** The figure is averaged across solar angles and comes from a single site.
- **Overcast still clears the bar.** Overcast outdoor light, at roughly a quarter of clear-sky melanopic EDI, still sits well above indoor levels (~280 lx [20]) and above the 250 lx recommendation [2]. Given saturation, the circadian loss is smaller than the 4 to 5 times photon loss. The cohort data agree. In 400,000+ UK Biobank participants, in a cloudy climate, each hour outdoors in daylight was associated with earlier chronotype, easier waking and better mood. Burns et al. 2021 [26]. Brighter daytime light also predicted lower mortality. Windred et al. 2024 [27]. **Moderate** (observational).
- **Verdict:** the user's belief that overcast still works, as a modifier, is **supported**.

## Implications for the tool (binding on the spec)

1. **Reframe the core question.** "Is the sun's disc visible from this Candidate in the hour after Nominal sunrise?" is a weaker proxy than "how much open sky, and what melanopic dose, will I get from this Candidate in my morning window?" The disc-in-view line-of-sight result is still worth showing as a bonus (more light when facing it, and the user likes it). It should not be the pass/fail criterion. A sky-openness measure, such as obstruction across the eastern half of the Horizon profile or a sky view factor, is the better primary signal, and LIDAR can compute it.
2. **Anchor the window to the user's wake time, and let sunrise decide availability.** The window runs from max(wake time, Nominal sunrise or local sun-clear time) and should extend about 2 to 3 h past waking, with weight falling over that span. A fixed `window_minutes = 60` after Nominal sunrise is not grounded in evidence. If wake time is unknown, default to "from sunrise", but expose wake time as a setting.
3. **Score total minutes, not the longest Clear window.** Intermittent light counts nearly fully [15][16]. Replace the contiguous `min_clear_minutes` test with total minutes of exposure (or estimated dose) in the window. This also settles the `compare` versus `find` inconsistency on #2: `compare`'s total-minutes logic is closer to the evidence.
4. **Minimum duration.** No hard evidence-based minimum exists. A pragmatic display floor of ~10 to 15 min of exposure is defensible [14], with more ranked higher and diminishing returns (for example logarithmic or saturating scoring). Do not present the threshold as physiological.
5. **Lux and elevation thresholds.** Do not use a sun-elevation threshold as a quality gate. Sun above the local horizon, or simply being after sunrise for sky light, is enough. If the tool estimates light, use melanopic EDI. The 250 lx floor is always met outdoors after sunrise, so the meaningful thresholds sit at roughly the ≥1000 lx saturation region, and these are approximate. Modelling exact lux from LIDAR is optional; sky openness plus sun-visible minutes is a reasonable proxy.
6. **Cloud as a multiplier, never a veto.** Scale the expected dose by about 10^(-0.08 × oktas) (full overcast ≈ ×0.23), and tell the user overcast mornings are still worth going out. Forecast cloud should lower the ranking of disc-visibility bonuses most, because cloud removes the direct beam, and lower the overall dose less.
7. **Copy and guidance.** Never tell the user to look at the sun. Mention that evening light undermines morning gains [13], and that a dim winter raises sensitivity [19].

## Open or weak points

- The morning-specific intensity response and duration response have been measured less well than the evening ones. The 100 lx and saturation numbers come from evening studies.
- There is no direct human comparison of sun-disc-visible versus open-sky-only outdoor exposure.
- The CBTmin-to-wake offset (~2 to 3 h) is unsourced here, so it should be a parameter.
- The cloud effect comes from a single Netherlands site, averaged over solar angles. Low-sun winter mornings in Bristol may differ.

## Method note

Searches used PubMed and Consensus. Claims rest on abstracts and, where available, PMC full text: Brown 2022, Spitschan 2016 and Woelders 2018 were read in full. This research was done inline by the delegated agent rather than by a further background agent.

## References

1. Brown TM. Melanopic illuminance defines the magnitude of human circadian light responses under a wide range of conditions. *J Pineal Res* 2020;69:e12655. https://doi.org/10.1111/jpi.12655
2. Brown TM et al. Recommendations for daytime, evening, and nighttime indoor light exposure to best support physiology, sleep, and wakefulness in healthy adults. *PLoS Biol* 2022;20:e3001571. https://doi.org/10.1371/journal.pbio.3001571
3. Lucas RJ et al. Measuring and using light in the melanopsin age. *Trends Neurosci* 2014;37:1-9. https://doi.org/10.1016/j.tins.2013.10.004
4. Spitschan M et al. No evidence for an S cone contribution to acute neuroendocrine and alerting responses to light. *Curr Biol* 2019;29:R1297-8. https://doi.org/10.1016/j.cub.2019.11.031
5. Khalsa SBS et al. A phase response curve to single bright light pulses in human subjects. *J Physiol* 2003;549:945-52. https://doi.org/10.1113/jphysiol.2003.040477
6. Minors DS et al. A human phase-response curve to light. *Neurosci Lett* 1991;133:36-40. https://doi.org/10.1016/0304-3940(91)90051-t
7. St Hilaire MA et al. Human phase response curve to a 1 h pulse of bright white light. *J Physiol* 2012;590:3035-45. https://doi.org/10.1113/jphysiol.2012.227892
8. Revell VL et al. Advancing human circadian rhythms with afternoon melatonin and morning intermittent bright light. *J Clin Endocrinol Metab* 2006;91:54-9. https://doi.org/10.1210/jc.2005-1009
9. Crowley SJ et al. Extending weeknight sleep duration in late-sleeping adolescents using morning bright light on weekends: a 3-week maintenance study. *Sleep Adv* 2024;5:zpae065. https://doi.org/10.1093/sleepadvances/zpae065
10. Wright KP et al. Entrainment of the human circadian clock to the natural light-dark cycle. *Curr Biol* 2013;23:1554-8. https://doi.org/10.1016/j.cub.2013.06.039
11. Stothard ER et al. Circadian entrainment to the natural light-dark cycle across seasons and the weekend. *Curr Biol* 2017;27:508-13. https://doi.org/10.1016/j.cub.2016.12.041
12. Roenneberg T et al. The human circadian clock entrains to sun time. *Curr Biol* 2007;17:R44-5. https://doi.org/10.1016/j.cub.2006.12.011
13. Monterastelli AJ et al. Late evening room light and sleep restriction reduces the ability of bright morning light to phase advance adolescents' circadian clocks. *Sci Rep* 2026;16. https://doi.org/10.1038/s41598-026-37985-y
14. Chang AM et al. Human responses to bright light of different durations. *J Physiol* 2012;590:3103-12. https://doi.org/10.1113/jphysiol.2011.226555
15. Rimmer DW et al. Dynamic resetting of the human circadian pacemaker by intermittent bright light. *Am J Physiol Regul Integr Comp Physiol* 2000;279:R1574-9. https://doi.org/10.1152/ajpregu.2000.279.5.R1574
16. Gronfier C et al. Efficacy of a single sequence of intermittent bright light pulses for delaying circadian phase in humans. *Am J Physiol Endocrinol Metab* 2004;287:E174-81. https://doi.org/10.1152/ajpendo.00385.2003
17. Zeitzer JM et al. Sensitivity of the human circadian pacemaker to nocturnal light: melatonin phase resetting and suppression. *J Physiol* 2000;526:695-702. https://doi.org/10.1111/j.1469-7793.2000.00695.x
18. Phillips AJK et al. High sensitivity and interindividual variability in the response of the human circadian system to evening light. *PNAS* 2019;116:12019-24. https://doi.org/10.1073/pnas.1901824116
19. Hébert M et al. The effects of prior light history on the suppression of melatonin by light in humans. *J Pineal Res* 2002;33:198-203. https://doi.org/10.1034/j.1600-079x.2002.01885.x
20. Tabandeh N et al. Photoreceptor-specific scene statistics reveal melanopic structure in natural environments. *iScience* 2026. https://doi.org/10.1016/j.isci.2026.116661
21. Spitschan M et al. Variation of outdoor illumination as a function of solar elevation and light pollution. *Sci Rep* 2016;6:26756. https://doi.org/10.1038/srep26756
22. Glickman G et al. Inferior retinal light exposure is more effective than superior retinal exposure in suppressing melatonin in humans. *J Biol Rhythms* 2003;18:71-9. https://doi.org/10.1177/0748730402239678
23. Yu C-H et al. Unveiling the temporal dynamics of diurnal and crepuscular illumination. *J Vis* 2024 (abstract). https://consensus.app/papers/details/e4ae29dfbab5534981363a23f1e0ebe7/
24. Walmsley L et al. Colour as a signal for entraining the mammalian circadian clock. *PLoS Biol* 2015;13:e1002127. https://doi.org/10.1371/journal.pbio.1002127
25. Woelders T et al. Integration of color and intensity increases time signal stability for the human circadian system when sunlight is obscured by clouds. *Sci Rep* 2018;8. https://doi.org/10.1038/s41598-018-33606-5
26. Burns AC et al. Time spent in outdoor light is associated with mood, sleep, and circadian rhythm-related outcomes. *J Affect Disord* 2021;295:347-52. https://doi.org/10.1016/j.jad.2021.08.056
27. Windred DP et al. Brighter nights and darker days predict higher mortality risk. *PNAS* 2024;121:e2405924121. https://doi.org/10.1073/pnas.2405924121

Bibliographic data from PubMed (DOIs above) and Consensus.
