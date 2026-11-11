// From what the sentence says to the Query the scorer is asked, and the
// defaults the sentence starts from. Pure, with the clock passed in.
//
// The Morning window ends at Wake time + 3 h, so its date is today until then
// and tomorrow after. The query starts from "now" on today's date (the scorer
// clips the window start to it). #48 adds the Evening window's date and the
// tab choice beside `nextMorningDate`.

import type { Query, Sky, WindowName } from "../contract";
import { clampMaxWalk } from "../settings/store";
import { TIME_ZONE, instantOf, toLocalIso } from "../solar/local-day";

/** Minutes from Wake time to the end of the Morning window. */
export const MORNING_WINDOW_MIN = 180;

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

/** The date of the next Morning window to plan: today until it ends, else tomorrow. */
export function nextMorningDate(nowMs: number, wakeTime: string): string {
  const today = localDate(nowMs);
  const end = wakeInstant(today, wakeTime) + MORNING_WINDOW_MIN * 60_000;
  return nowMs < end ? today : nextDate(today);
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
