// The parity rules of docs/fixtures.md ("Parity: what the JS scorer is held
// to"), as functions that return what disagrees. Empty means parity.

import type { Answer } from "../../src/contract";
import { TIME_ZONE, toLocalIso } from "../../src/solar/local-day";
import { type SunTrack, sampleTimeMs } from "../../src/solar/sun-track";
import type { FixtureDocument, ReferenceSunTrack } from "./fixture-set";

/** JS and reference sun positions must agree within this, in degrees. */
export const SOLAR_TOLERANCE_DEG = 0.01;

export interface SunTrackDisagreement {
  /** Structural mismatches: a different start or number of samples. */
  problems: string[];
  /** The largest azimuth difference of the day, degrees, modulo 360. */
  worstAzimuthDeg: number;
  /** The largest apparent elevation difference of the day, degrees. */
  worstApparentElevationDeg: number;
  /** The lowest apparent elevation compared, degrees: parity holds below 0 too. */
  lowestApparentElevationDeg: number;
}

export function compareSunTrack(
  track: SunTrack,
  reference: ReferenceSunTrack,
  timeZone: string = TIME_ZONE,
): SunTrackDisagreement {
  const problems: string[] = [];
  const start = toLocalIso(track.startMs, timeZone);
  if (start !== reference.start) {
    problems.push(`start is ${start}, the reference's is ${reference.start}`);
  }
  if (reference.stepMin !== 1) {
    problems.push(`the reference's step is ${reference.stepMin} min, not 1`);
  }
  for (const series of ["azimuth", "apparentElevation"] as const) {
    if (reference[series].length !== track.length) {
      problems.push(`${track.length} samples, the reference has ${reference[series].length} of ${series}`);
    }
  }

  let worstAzimuthDeg = 0;
  let worstApparentElevationDeg = 0;
  let lowestApparentElevationDeg = Infinity;
  const samples = Math.min(track.length, reference.azimuth.length, reference.apparentElevation.length);
  for (let i = 0; i < samples; i++) {
    const turn = Math.abs(track.azimuth[i]! - reference.azimuth[i]!) % 360;
    worstAzimuthDeg = Math.max(worstAzimuthDeg, Math.min(turn, 360 - turn));
    worstApparentElevationDeg = Math.max(
      worstApparentElevationDeg,
      Math.abs(track.apparentElevation[i]! - reference.apparentElevation[i]!),
    );
    lowestApparentElevationDeg = Math.min(lowestApparentElevationDeg, reference.apparentElevation[i]!);
  }
  return { problems, worstAzimuthDeg, worstApparentElevationDeg, lowestApparentElevationDeg };
}

/** The day's three events as an Answer writes them. */
export function sunEvents(
  track: SunTrack,
  timeZone: string = TIME_ZONE,
): Pick<Answer, "nominalSunrise" | "nominalSunset" | "solarNoon"> {
  const iso = (sample: number) => toLocalIso(sampleTimeMs(track, sample), timeZone);
  return {
    ...(track.nominalSunrise !== null && { nominalSunrise: iso(track.nominalSunrise) }),
    ...(track.nominalSunset !== null && { nominalSunset: iso(track.nominalSunset) }),
    solarNoon: iso(track.solarNoon),
  };
}

// Each is an integer divided by a constant (1e7, 80 m/min, 100).
const NEAR_EXACT = new Set(["lat", "lon", "walkMin", "lowSunMinutes", "stayMin"]);
const TOLERANCE: Record<string, number> = { skyOpenness: 0.001 };

function differences(actual: unknown, expected: unknown, path: string, key: string, out: string[]): void {
  const show = (value: unknown) => (value === undefined ? "absent" : JSON.stringify(value));
  if (typeof actual === "number" && typeof expected === "number") {
    const tolerance = TOLERANCE[key] ?? (NEAR_EXACT.has(key) ? 1e-9 : 0);
    // The small slack keeps a difference of exactly the tolerance inside it despite rounding.
    if (!(Math.abs(actual - expected) <= tolerance * (1 + 1e-9))) {
      out.push(`${path}: ${actual}, the reference has ${expected}`);
    }
  } else if (Array.isArray(actual) && Array.isArray(expected)) {
    if (actual.length !== expected.length) {
      out.push(`${path}: ${actual.length} entries, the reference has ${expected.length}`);
    }
    for (let i = 0; i < Math.min(actual.length, expected.length); i++) {
      differences(actual[i], expected[i], `${path}[${i}]`, key, out);
    }
  } else if (isRecord(actual) && isRecord(expected)) {
    for (const member of new Set([...Object.keys(actual), ...Object.keys(expected)])) {
      differences(actual[member], expected[member], path ? `${path}.${member}` : member, member, out);
    }
  } else if (actual !== expected) {
    out.push(`${path}: ${show(actual)}, the reference has ${show(expected)}`);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Where a JS Answer differs from the reference's, member for member, with the
 * tolerances of docs/fixtures.md and no others. A member absent from one must
 * be absent from the other. Near-boundary freedom is not applied here: see
 * `nearBoundaryFreedom`.
 */
export function answerDifferences(actual: Answer, expected: Answer): string[] {
  const out: string[] = [];
  differences(actual, expected, "", "", out);
  return out;
}

export interface NearBoundaryFreedom {
  /** Per candidateId, the minutes (ISO, inside the day) at which sun in view may differ. */
  candidates: Record<string, string[]>;
  /** The minutes of the Answer's window at which "low sun" may differ, for every Candidate. */
  lowSunBandInWindow: string[];
  /** False when the Answer must match exactly. */
  any: boolean;
}

/**
 * The freedom a fixture leaves the JS Answer (docs/fixtures.md, "Near-boundary
 * minutes"). Candidate minutes cover the whole day, because Last sun is looked
 * for over the whole day; low-sun-band minutes are cut to the Answer's window.
 */
export function nearBoundaryFreedom(fixture: FixtureDocument): NearBoundaryFreedom {
  const startMs = Date.parse(fixture.sunTrack.start);
  const at = (minute: number) => startMs + minute * 60_000;
  const iso = (ms: number) => toLocalIso(ms, TIME_ZONE);
  const window = fixture.answer.window;
  const inWindow = (ms: number) =>
    window !== undefined && ms >= Date.parse(window.start) && ms < Date.parse(window.end);

  const candidates: Record<string, string[]> = {};
  for (const [candidateId, minutes] of Object.entries(fixture.nearBoundary.candidates)) {
    candidates[candidateId] = minutes.map((minute) => iso(at(minute)));
  }
  const lowSunBandInWindow = fixture.nearBoundary.lowSunBand
    .map(at)
    .filter(inWindow)
    .map(iso);
  return {
    candidates,
    lowSunBandInWindow,
    any: Object.keys(candidates).length > 0 || lowSunBandInWindow.length > 0,
  };
}
