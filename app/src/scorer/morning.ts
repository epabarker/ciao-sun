// The Morning window: its bounds, its taper and its Leave-by rule.
// `ciao_sun.reference.morning` is the reference.

import type { Answer, Query } from "../contract";
import type { SunTrack } from "../solar/sun-track";
import { type WindowPlan, nowMinute, wakeMinute } from "./windows";

/** The window ends this long after Wake time. */
export const MORNING_WINDOW_MIN = 180;
/** Weight 1 until this long after Wake time, then linear to 0 at the end. */
export const FULL_WEIGHT_MIN = 60;

/**
 * Arrive as the sun appears: the first sun interval's start minus the walk.
 * The walk is rounded up to whole minutes. Never before Wake time or now.
 */
export function morningLeaveBy(inView: Uint8Array, walkMin: number, plan: WindowPlan): number {
  const firstSun = plan.start + Math.max(inView.indexOf(1), 0);
  return Math.max(firstSun - Math.ceil(walkMin), plan.earliestLeave);
}

export function planMorning(query: Query, track: SunTrack): WindowPlan | Answer {
  const wake = wakeMinute(query, track);
  const now = nowMinute(query, track);
  const end = Math.min(wake + MORNING_WINDOW_MIN, track.length);
  const earliestLeave = now === null ? wake : Math.max(wake, now);
  if (track.nominalSunrise === null) {
    return noDaylight(query, track);
  }
  const unclippedStart = Math.max(wake, track.nominalSunrise);
  const start = Math.max(unclippedStart, earliestLeave);
  if (start >= end) {
    return noDaylight(query, track);
  }

  const taperMin = MORNING_WINDOW_MIN - FULL_WEIGHT_MIN;
  const weightNumerators = Int32Array.from({ length: end - start }, (_, i) =>
    Math.min(taperMin, MORNING_WINDOW_MIN - (start + i - wake)),
  );
  return {
    start,
    end,
    unclippedStart,
    axisStart: earliestLeave,
    axisEnd: end,
    earliestLeave,
    weightNumerators,
    weightDenominator: taperMin,
    leaveBy: morningLeaveBy,
    reportsLastSun: false,
  };
}

/** The Morning window holds no daylight: the lamp-only Answer (#44). */
function noDaylight(query: Query, _track: SunTrack): Answer {
  throw new Error(`lamp-only Answers are not written yet (#44): ${query.date} ${query.wakeTime}`);
}
