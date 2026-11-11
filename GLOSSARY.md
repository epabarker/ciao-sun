# Ciao Sun

Helps a person say hello to the sun after waking and goodbye to it before sunset: it finds nearby places, and times, with the most open sky and the sun in view, for Morning light and Evening light.

## Language

**Morning light**:
The light exposure after waking that the tool exists to help someone get; what counts (timing, duration, sun elevation, overcast) is set by circadian research.
_Avoid_: sunlight hit, sun exposure

**Evening light**:
The late-day light exposure before sunset that the tool exists to help someone get, as its own answer whether or not they got Morning light; what counts is set by circadian research.
_Avoid_: sunset hit, golden hour

**Nominal sunrise**:
The first minute the sun's geometric centre reaches -0.833° at a location, which is when its upper limb would appear on a flat horizon under standard refraction. It depends only on place and date, not on when the sun actually appears at a Candidate, which can be later behind obstructions or slightly earlier from a high spot above a falling horizon.
_Avoid_: local sunrise, actual sunrise

**Nominal sunset**:
The last minute the sun's geometric centre is at or above -0.833° at a location, which is when its upper limb would disappear on a flat horizon under standard refraction. It depends only on place and date, not on when the sun actually disappears at a Candidate, which is its Last sun.
_Avoid_: local sunset, actual sunset

**Last sun**:
The last minute on a given day that the sun is above a Candidate's Horizon profile, in the sense used for Sun minutes. It can be well before Nominal sunset behind obstructions.
_Avoid_: local sunset, sundown

**Candidate**:
A standing position assessed for whether the sun is visible from it.
_Avoid_: point, cell

**Horizon profile**:
The obstruction angle seen from a Candidate at each azimuth; fixed for a location, independent of date. Trees count as in full leaf on every date, so in winter the sun may show through bare branches below it.
_Avoid_: skyline, horizon mask

**Clear window**:
An unbroken run of time during which the sun is above a Candidate's Horizon profile, in the sense used for Sun minutes.
_Avoid_: pass fraction, clear time

**Wake time**:
When the person gets up on a given day; the anchor for their Morning window and for the start of their Evening window.
_Avoid_: alarm time, start time

**Morning window**:
The period in which Morning light counts: from the later of Wake time and Nominal sunrise until a few hours after waking, weighted most in the first hour after waking and tapering after.
_Avoid_: sunrise hour, sunrise window

**Evening window**:
The period in which Evening light counts: from the later of solar noon and six hours after Wake time until Nominal sunset, with no part weighted above another. A Candidate's Sun minutes within it end at its Last sun; if the window would start after Nominal sunset, there is none that day.
_Avoid_: sunset hour, golden hour, light window

**Sun minutes**:
The total minutes within the Morning window or Evening window that the sun is above a Candidate's Horizon profile, whether or not they are contiguous. "Above" means the centre of the sun's disc, as seen through the atmosphere, is higher than the Horizon profile at the sun's azimuth, whether that profile is above or below 0°.
_Avoid_: clear time, pass fraction

**Sky openness**:
How little of the sky a Candidate's Horizon profile blocks; distinguishes enclosed spots from open ones, independent of whether the sun is in view.
_Avoid_: sky view, exposure

**Duration target**:
The outdoor minutes to aim for in a Morning window or Evening window, set by how cloudy it is in that window; a target to show, not a physiological threshold.
_Avoid_: minimum, threshold, dose

**Protocols factor**:
A labelled bonus for Sun minutes when the sun is low and the sky is clear, at either end of the day, from *Protocols*' claim about low-sun light quality; untested in humans.
_Avoid_: sunrise quality, golden-hour bonus

**Stage**:
One step of the planned rollout: just me in Bristol, then just me in England then the UK, then anyone in the UK.
_Avoid_: phase, milestone
