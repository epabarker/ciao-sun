// The Evening window: its bounds, its axis and its Leave-by rule. Its minutes
// are unweighted. `ciao_sun.reference.evening` is the reference.

import type { Answer, Query } from "../contract";
import type { SunTrack } from "../solar/sun-track";
import { morningLeaveBy } from "./morning";
import { type WindowPlan, eventClock, nowMinute, wakeMinute } from "./windows";

/** The window starts no sooner than this long after Wake time. */
export const WAKE_TO_EVENING_MIN = 360;
/** The axis covers this long before Nominal sunset. */
export const EVENING_AXIS_MIN = 180;

/**
 * The latest departure that meets the Duration target before Last sun.
 *
 * The target is met when the walk plus the Sun minutes from arrival reach it,
 * so the Sun minutes still needed are the target less the walk, rounded up to
 * a whole minute, and at least 1: a walk that meets the target alone must
 * still arrive for the last Sun minute, or no departure would be the latest.
 * Arrival is the minute that leaves exactly that many Sun minutes in the
 * window, and the walk before it is rounded up to whole minutes.
 *
 * If that departure is before Wake time or now, or the window holds too few
 * Sun minutes, no departure meets the target: the morning rule applies.
 */
export function eveningLeaveBy(inView: Uint8Array, walkMin: number, plan: WindowPlan, targetMin: number): number {
  const needed = Math.max(Math.ceil(targetMin - walkMin), 1);
  const sun: number[] = [];
  inView.forEach((v, i) => {
    if (v === 1) sun.push(i);
  });
  if (sun.length >= needed) {
    const leave = plan.start + sun[sun.length - needed]! - Math.ceil(walkMin);
    if (leave >= plan.earliestLeave) {
      return leave;
    }
  }
  return morningLeaveBy(inView, walkMin, plan);
}

export function planEvening(query: Query, track: SunTrack): WindowPlan | Answer {
  const wake = wakeMinute(query, track);
  const now = nowMinute(query, track);
  const earliestLeave = now === null ? wake : Math.max(wake, now);
  if (track.nominalSunset === null) {
    return noEveningWindow(track);
  }
  const end = track.nominalSunset;
  const unclippedStart = Math.max(track.solarNoon, wake + WAKE_TO_EVENING_MIN);
  const start = Math.max(unclippedStart, earliestLeave);
  if (start >= end) {
    return noEveningWindow(track);
  }

  return {
    start,
    end,
    unclippedStart,
    axisStart: Math.max(end - EVENING_AXIS_MIN, 0),
    axisEnd: end,
    earliestLeave,
    weightNumerators: new Int32Array(end - start).fill(1),
    weightDenominator: 1,
    leaveBy: eveningLeaveBy,
    reportsLastSun: true,
  };
}

/**
 * The window would not start before Nominal sunset: the no-evening-window
 * Answer. It has no window, spots or Duration target, only the day's sun
 * events.
 */
function noEveningWindow(track: SunTrack): Answer {
  const out: Answer = { status: "no-evening-window", spots: [] };
  const sunrise = eventClock(track, track.nominalSunrise);
  const sunset = eventClock(track, track.nominalSunset);
  if (sunrise !== undefined) out.nominalSunrise = sunrise;
  if (sunset !== undefined) out.nominalSunset = sunset;
  out.solarNoon = eventClock(track, track.solarNoon)!;
  return out;
}
