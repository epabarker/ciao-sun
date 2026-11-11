// The lamp message, and the lamp-only Answer for a Morning window that holds
// no minutes. `ciao_sun.reference.lamp` is the reference.

import type { Answer, Query } from "../contract";
import { TIME_ZONE } from "../solar/local-day";
import { type SunTrack, sunTrack } from "../solar/sun-track";
import { clock, nowMinute, wakeMinute } from "./windows";

/** The lamp is suggested when Nominal sunrise is later than this after Wake time. */
export const LAMP_AFTER_WAKE_MIN = 60;

/** Whether Nominal sunrise is more than 1 h after Wake time, both as whole minutes. */
export function lamp(query: Query, track: SunTrack): boolean {
  if (track.nominalSunrise === null) {
    return true;
  }
  return track.nominalSunrise > wakeMinute(query, track) + LAMP_AFTER_WAKE_MIN;
}

/**
 * The Answer when the Morning window is empty: no list, and no window to
 * draw. The window is empty when it ends by Nominal sunrise, or when `now`
 * is at or past its end. `lamp` follows its own rule either way, so it is
 * false for a window that is merely over on a morning that had early sun.
 */
export function lampOnly(query: Query, track: SunTrack): Answer {
  const out: Answer = { status: "lamp-only", lamp: lamp(query, track), spots: [] };
  const next = nextOutdoorLight(query, track);
  if (next !== null) out.nextOutdoorLight = next;
  return out;
}

/**
 * The first minute, from the later of Wake time and now, with the sun
 * nominally up. That is Nominal sunrise when it is still to come; the minute
 * itself when it falls from Nominal sunrise up to, not including, Nominal
 * sunset; and otherwise the next day's Nominal sunrise. Null if the sun does
 * not rise then either.
 */
export function nextOutdoorLight(query: Query, track: SunTrack): string | null {
  const wake = wakeMinute(query, track);
  const now = nowMinute(query, track);
  const earliest = now === null ? wake : Math.max(wake, now);
  if (track.nominalSunrise !== null) {
    if (earliest <= track.nominalSunrise) {
      return clock(track, track.nominalSunrise);
    }
    if (track.nominalSunset === null || earliest < track.nominalSunset) {
      return clock(track, earliest);
    }
  }
  const tomorrow = sunTrack(query.origin.lat, query.origin.lon, nextDate(query.date), TIME_ZONE);
  return tomorrow.nominalSunrise === null ? null : clock(tomorrow, tomorrow.nominalSunrise);
}

/** The calendar day after `date` (YYYY-MM-DD). */
function nextDate(date: string): string {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(Date.UTC(year!, month! - 1, day! + 1)).toISOString().slice(0, 10);
}
