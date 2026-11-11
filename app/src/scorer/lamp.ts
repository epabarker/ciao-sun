// The lamp message. `ciao_sun.reference.lamp` is the reference; the lamp-only
// Answer is #44's.

import type { Query } from "../contract";
import type { SunTrack } from "../solar/sun-track";
import { wakeMinute } from "./windows";

/** The lamp is suggested when Nominal sunrise is later than this after Wake time. */
export const LAMP_AFTER_WAKE_MIN = 60;

/** Whether Nominal sunrise is more than 1 h after Wake time, both as whole minutes. */
export function lamp(query: Query, track: SunTrack): boolean {
  if (track.nominalSunrise === null) {
    return true;
  }
  return track.nominalSunrise > wakeMinute(query, track) + LAMP_AFTER_WAKE_MIN;
}
