# sunspot

Helps a person get Morning light after waking by finding nearby places, and times, with the most open sky and the sun in view.

## Language

**Morning light**:
The light exposure after waking that the tool exists to help someone get; what counts (timing, duration, sun elevation, overcast) is set by circadian research.
_Avoid_: sunlight hit, sun exposure

**Nominal sunrise**:
The first minute the sun's apparent centre clears -0.833° over a flat horizon at a location; not when the sun actually appears at an obstructed site.
_Avoid_: local sunrise, actual sunrise

**Candidate**:
A standing position assessed for whether the sun is visible from it.
_Avoid_: point, cell

**Horizon profile**:
The obstruction angle seen from a Candidate at each azimuth; fixed for a location, independent of date.
_Avoid_: skyline, horizon mask

**Clear window**:
An unbroken run of time during which the sun is above a Candidate's Horizon profile.
_Avoid_: pass fraction, clear time

**Wake time**:
When the person gets up on a given morning; the anchor for their Morning window.
_Avoid_: alarm time, start time

**Morning window**:
The period in which Morning light counts: from the later of Wake time and Nominal sunrise until a few hours after waking, weighted most in the first hour after waking and tapering after.
_Avoid_: sunrise hour, sunrise window

**Sun minutes**:
The total minutes within the Morning window that the sun is above a Candidate's Horizon profile, whether or not they are contiguous.
_Avoid_: clear time, pass fraction

**Sky openness**:
How little of the sky a Candidate's Horizon profile blocks; distinguishes enclosed spots from open ones, independent of whether the sun is in view.
_Avoid_: sky view, exposure

**Duration target**:
The outdoor minutes to aim for on a given morning, set by how cloudy it is; a target to show, not a physiological threshold.
_Avoid_: minimum, threshold, dose

**Protocols factor**:
A labelled bonus for Sun minutes when the sun is low and the sky is clear, from *Protocols*' claim about low-sun light quality; untested in humans.
_Avoid_: sunrise quality, golden-hour bonus

**Stage**:
One step of the planned rollout: just me in Bristol, then just me in England then the UK, then anyone in the UK.
_Avoid_: phase, milestone
