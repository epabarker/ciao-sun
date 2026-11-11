// What the Morning window and the Evening window have in common.
//
// Times inside the scorer are **minutes**: whole minutes since local midnight
// of the query date, which are also indexes into the day's sun track. A window
// holds the minutes from `start` up to, not including, `end`.
// `ciao_sun.reference.windows` is the reference.

import type { Query } from "../contract";
import { MS_PER_MINUTE, TIME_ZONE, instantOf, toLocalIso } from "../solar/local-day";
import { type SunTrack, sampleTimeMs } from "../solar/sun-track";

/**
 * (sun in view at each minute of the window, walk in minutes, the plan,
 * Duration target) -> the minute to leave by. Only called for a spot with Sun
 * minutes.
 */
export type LeaveByRule = (inView: Uint8Array, walkMin: number, plan: WindowPlan, targetMin: number) => number;

/** One query's window, and the rules that differ between morning and evening. */
export interface WindowPlan {
  readonly start: number;
  readonly end: number;
  /**
   * The window before `now` clips it. Sky openness is taken over this one's
   * sun path, so a Candidate's openness does not change as the morning goes on.
   */
  readonly unclippedStart: number;
  readonly axisStart: number;
  readonly axisEnd: number;
  /** Leave-by is never before this. */
  readonly earliestLeave: number;
  /**
   * Low-sun minutes weigh minute `start + i` by weightNumerators[i] /
   * weightDenominator. Integers, so the ranking key is exact in any language.
   */
  readonly weightNumerators: Int32Array;
  readonly weightDenominator: number;
  readonly leaveBy: LeaveByRule;
  /** Evening: each Spot carries its Last sun. */
  readonly reportsLastSun: boolean;
}

/** The minute of the track's day at or after the instant `ms`. */
export function minuteOf(track: SunTrack, ms: number): number {
  return Math.ceil((ms - track.startMs) / MS_PER_MINUTE);
}

/** The Answer's string for a minute of the track's day. */
export function clock(track: SunTrack, minute: number): string {
  return toLocalIso(sampleTimeMs(track, minute), TIME_ZONE);
}

export function wakeMinute(query: Query, track: SunTrack): number {
  const [hour, minute] = query.wakeTime.split(":").map(Number);
  return minuteOf(track, instantOf(query.date, hour!, minute!, TIME_ZONE));
}

const ISO_INSTANT =
  /^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$/;

/** `now` as an instant; an ISO time with no offset is a Europe/London wall clock. */
function nowMs(now: string): number {
  const match = ISO_INSTANT.exec(now);
  if (!match) {
    throw new RangeError(`${JSON.stringify(now)} is not an ISO 8601 time`);
  }
  if (match[6] !== undefined) {
    return Date.parse(now);
  }
  const [, date, hour, minute, second = "0", fraction = ""] = match;
  const whole = instantOf(date!, Number(hour), Number(minute), TIME_ZONE, Number(second));
  return whole + (fraction ? Number(`0${fraction}`) * 1000 : 0);
}

/** `now` as a minute of the query date, or null when it is absent or on another day. */
export function nowMinute(query: Query, track: SunTrack): number | null {
  if (query.now === undefined) {
    return null;
  }
  const ms = nowMs(query.now);
  if (toLocalIso(ms, TIME_ZONE).slice(0, 10) !== query.date) {
    return null;
  }
  return minuteOf(track, ms);
}

/** A sun-track event (a sample index, so already a whole minute) as the Answer writes it. */
export function eventClock(track: SunTrack, sample: number | null): string | undefined {
  return sample === null ? undefined : clock(track, sample);
}
