// From what the sentence says to the Query the scorer is asked, and the
// defaults the sentence starts from. Pure, with the clock passed in.
//
// The Morning window ends at Wake time + 3 h, or at solar noon if that is
// sooner (#62), so its date is today until then and tomorrow after. The query starts from "now" on today's date (the scorer
// clips the window start to it). The Evening window's date is today until
// Nominal sunset; the app opens on whichever window comes next (`chooseWindow`).

import type { Query, Sky, WindowName } from "../contract";
import { clampMaxWalk } from "../settings/store";
import { MORNING_WINDOW_MIN } from "../scorer/morning";
import { MS_PER_MINUTE, TIME_ZONE, instantOf, toLocalIso } from "../solar/local-day";
import { sampleTimeMs, sunTrack } from "../solar/sun-track";

/** What the sentence holds: "I wake at [wakeTime] on [date], the sky looks [sky], ...". */
export interface QueryInputs {
  wakeTime: string;
  date: string;
  sky: Sky;
  maxWalkMin: number;
  origin: { lat: number; lon: number };
}

/** The local date, YYYY-MM-DD in Europe/London, at an instant. */
export function localDate(ms: number): string {
  return toLocalIso(ms, TIME_ZONE).slice(0, 10);
}

/** The date after a local date. */
export function nextDate(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(Date.UTC(y!, m! - 1, d! + 1)).toISOString().slice(0, 10);
}

function wakeInstant(date: string, wakeTime: string): number {
  const [hour, minute] = wakeTime.split(":").map(Number);
  return instantOf(date, hour!, minute!, TIME_ZONE);
}

/**
 * Where the tab choice and the dates read the sun: central Bristol. The
 * coverage is Bristol, across which sunset and solar noon differ by seconds,
 * and the choice is made before GPS answers, so a late fix never flips the tab.
 */
export const PLANNING_POINT = { lat: 51.4545, lon: -2.5879 } as const;

/**
 * The instant a local date's Morning window ends at a place: Wake time + 3 h,
 * or solar noon if that is sooner, as the scorer's `planMorning` has it.
 */
export function morningEndMs(date: string, wakeTime: string, at: { lat: number; lon: number }): number {
  const track = sunTrack(at.lat, at.lon, date, TIME_ZONE);
  const afterWake = wakeInstant(date, wakeTime) + MORNING_WINDOW_MIN * MS_PER_MINUTE;
  return Math.min(afterWake, sampleTimeMs(track, track.solarNoon));
}

/** The date of the next Morning window to plan: today until it ends, else tomorrow. */
export function nextMorningDate(
  nowMs: number,
  wakeTime: string,
  at: { lat: number; lon: number } = PLANNING_POINT,
): string {
  const today = localDate(nowMs);
  return nowMs < morningEndMs(today, wakeTime, at) ? today : nextDate(today);
}

/** The instant of Nominal sunset on a local date at a place, or null if the sun does not set. */
function nominalSunsetMs(date: string, at: { lat: number; lon: number }): number | null {
  const track = sunTrack(at.lat, at.lon, date, TIME_ZONE);
  return track.nominalSunset === null ? null : sampleTimeMs(track, track.nominalSunset);
}

/** The date of the next Evening window to plan: today until Nominal sunset, else tomorrow. */
export function nextEveningDate(nowMs: number, at: { lat: number; lon: number }): string {
  const today = localDate(nowMs);
  const sunset = nominalSunsetMs(today, at);
  return sunset !== null && nowMs < sunset ? today : nextDate(today);
}

/** The date a window's tab plans for at `nowMs`. */
export function nextWindowDate(window: WindowName, nowMs: number, wakeTime: string, at = PLANNING_POINT): string {
  return window === "morning" ? nextMorningDate(nowMs, wakeTime) : nextEveningDate(nowMs, at);
}

/**
 * The tab the app opens on, and its date: whichever window comes next.
 * Today's Morning until it ends, then today's Evening until Nominal sunset,
 * then tomorrow's Morning.
 */
export function chooseWindow(
  nowMs: number,
  wakeTime: string,
  at: { lat: number; lon: number } = PLANNING_POINT,
): { window: WindowName; date: string } {
  const today = localDate(nowMs);
  if (nextMorningDate(nowMs, wakeTime, at) === today) {
    return { window: "morning", date: today };
  }
  const sunset = nominalSunsetMs(today, at);
  if (sunset !== null && nowMs < sunset) {
    return { window: "evening", date: today };
  }
  return { window: "morning", date: nextDate(today) };
}

/**
 * Whether the Query's Morning window is already over when it is asked: `now`
 * is on the query's date, at or after the window's end (`morningEndMs`, at
 * the Query's origin, as the scorer reads the sun). A fact of the Query,
 * not a score: the answer screen uses it to tell a Morning window emptied by
 * `now` from one that holds no daylight, both `lamp-only`.
 */
export function morningWindowOver(query: Query): boolean {
  if (query.now === undefined) return false;
  const nowMs = Date.parse(query.now);
  return localDate(nowMs) === query.date && nowMs >= morningEndMs(query.date, query.wakeTime, query.origin);
}

/** The Query for the sentence's inputs, asked at `nowMs`. */
export function buildQuery(inputs: QueryInputs, nowMs: number, window: WindowName = "morning"): Query {
  const query: Query = {
    window,
    date: inputs.date,
    wakeTime: inputs.wakeTime,
    origin: { lat: inputs.origin.lat, lon: inputs.origin.lon },
    maxWalkMin: clampMaxWalk(inputs.maxWalkMin),
    sky: inputs.sky,
  };
  if (localDate(nowMs) === inputs.date) {
    query.now = toLocalIso(nowMs, TIME_ZONE);
  }
  return query;
}
