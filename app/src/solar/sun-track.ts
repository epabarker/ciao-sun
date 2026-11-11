// The solar model: one local day of sun positions, with the day's three events.
//
// docs/solar-model.md is the specification and `ciao_sun.solar` the reference
// this must agree with: within 0.01 degrees at every minute, and on the same
// minute for Nominal sunrise, Nominal sunset and solar noon. Terms follow
// GLOSSARY.md.

import { MS_PER_MINUTE, TIME_ZONE, localDay } from "./local-day";
import { sunPosition } from "./spa";

/** Geometric elevation of the disc centre at Nominal sunrise and sunset, degrees. */
export const NOMINAL_RISE_SET_ELEVATION_DEG = -0.833;

const REFRACTION_SCALE_ARCMIN = 1.02;
const REFRACTION_A_DEG2 = 10.3;
const REFRACTION_B_DEG = 5.11;
/** Where the formula's refraction peaks; below it the refraction is held constant. */
const REFRACTION_FLOOR_DEG = Math.sqrt(REFRACTION_A_DEG2) - REFRACTION_B_DEG;

/** One local day of sun positions at 1 min steps. Sample i is `startMs + i` minutes. */
export interface SunTrack {
  /** The instant of sample 0: local midnight of the day, ms since the Unix epoch. */
  readonly startMs: number;
  /** Samples in the day: 1,440, or 1,380 and 1,500 on the days the clocks change. */
  readonly length: number;
  /** True azimuth, degrees clockwise from true north. */
  readonly azimuth: Float64Array;
  /** Geometric elevation of the disc centre, degrees. */
  readonly elevation: Float64Array;
  /** Geometric elevation + refraction, degrees: what a Horizon profile is compared with. */
  readonly apparentElevation: Float64Array;
  /** Sample index of Nominal sunrise; null when the centre never crosses up that day. */
  readonly nominalSunrise: number | null;
  /** Sample index of Nominal sunset; null when the centre never crosses down that day. */
  readonly nominalSunset: number | null;
  /** Sample index of solar noon, the upper transit. */
  readonly solarNoon: number;
}

/**
 * Refraction to add to a geometric elevation, both in degrees. Continuous and
 * smooth at every elevation: there is no switch-on level.
 */
export function refractionDeg(elevationDeg: number): number {
  const h = Math.max(elevationDeg, REFRACTION_FLOOR_DEG);
  const argumentDeg = h + REFRACTION_A_DEG2 / (h + REFRACTION_B_DEG);
  return REFRACTION_SCALE_ARCMIN / Math.tan((argumentDeg * Math.PI) / 180) / 60;
}

/**
 * Sample indexes nearest each upward zero crossing of `value`: the crossing is
 * placed by linear interpolation between the two samples that bracket it, then
 * rounded half up to a whole sample.
 */
function crossingMinutes(length: number, value: (i: number) => number): number[] {
  const nearest: number[] = [];
  let before = value(0);
  for (let i = 0; i + 1 < length; i++) {
    const after = value(i + 1);
    if (before < 0 && after >= 0) {
      nearest.push(i + Math.floor(-before / (after - before) + 0.5));
    }
    before = after;
  }
  return nearest;
}

/** The instant of sample `i` of a sun track, ms since the Unix epoch. */
export function sampleTimeMs(track: SunTrack, i: number): number {
  return track.startMs + i * MS_PER_MINUTE;
}

/** The sun track for the local day `date` (YYYY-MM-DD) at a place. */
export function sunTrack(
  lat: number,
  lon: number,
  date: string,
  timeZone: string = TIME_ZONE,
): SunTrack {
  const { startMs, minutes } = localDay(date, timeZone);
  const azimuth = new Float64Array(minutes);
  const elevation = new Float64Array(minutes);
  const apparentElevation = new Float64Array(minutes);
  for (let i = 0; i < minutes; i++) {
    const position = sunPosition((startMs + i * MS_PER_MINUTE) / 1000, lat, lon);
    azimuth[i] = position.azimuth;
    elevation[i] = position.elevation;
    apparentElevation[i] = position.elevation + refractionDeg(position.elevation);
  }

  const above = (i: number) => elevation[i]! - NOMINAL_RISE_SET_ELEVATION_DEG;
  const rises = crossingMinutes(minutes, above);
  const sets = crossingMinutes(minutes, (i) => -above(i));
  // sin(azimuth) falls through zero only at the upper transit, in either hemisphere.
  const transits = crossingMinutes(minutes, (i) => -Math.sin((azimuth[i]! * Math.PI) / 180));
  const solarNoon = transits[0];
  if (solarNoon === undefined) {
    throw new RangeError(`No solar noon on ${date} at ${lat},${lon}.`);
  }

  return {
    startMs,
    length: minutes,
    azimuth,
    elevation,
    apparentElevation,
    nominalSunrise: rises[0] ?? null,
    nominalSunset: sets.at(-1) ?? null,
    solarNoon,
  };
}
