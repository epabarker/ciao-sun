// The parity rules of docs/fixtures.md ("Parity: what the JS scorer is held
// to"), as functions that return what disagrees. Empty means parity.

import type { Answer, Interval, Spot } from "../../src/contract";
import type { SightOverrides } from "../../src/scorer/scoring";
import { LOW_SUN_MAX_DEG, LOW_SUN_MIN_DEG, horizonAt } from "../../src/scorer/sunview";
import { TIME_ZONE, toLocalIso } from "../../src/solar/local-day";
import { type SunTrack, sampleTimeMs } from "../../src/solar/sun-track";
import { PROFILE_STEP_DEG, type Tile, horizonProfileCodes } from "../../src/tile/decode";
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

/**
 * The near-boundary minutes that can change this fixture's Answer: the
 * Candidate minutes inside the Answer's window, or the whole day's for an
 * Evening window, whose Last sun is looked for over the whole day; and the
 * low-sun-band minutes inside the window.
 */
export function effectiveFreedom(fixture: FixtureDocument): NearBoundaryFreedom {
  const freedom = nearBoundaryFreedom(fixture);
  const window = fixture.answer.window;
  // An Evening window's Spots carry Last sun.
  const wholeDay = fixture.query.window === "evening";
  // Compared as instants: the offset changes within a day when the clocks do.
  const inWindow = (iso: string) =>
    window !== undefined &&
    Date.parse(iso) >= Date.parse(window.start) &&
    Date.parse(iso) < Date.parse(window.end);
  const candidates: Record<string, string[]> = {};
  for (const [candidateId, minutes] of Object.entries(freedom.candidates)) {
    const kept = wholeDay ? minutes : minutes.filter(inWindow);
    if (kept.length > 0) {
      candidates[candidateId] = kept;
    }
  }
  return {
    candidates,
    lowSunBandInWindow: freedom.lowSunBandInWindow,
    any: Object.keys(candidates).length > 0 || freedom.lowSunBandInWindow.length > 0,
  };
}

/** What the fixture's stored sun track may be off by: it is rounded to 4 decimal places. */
const STORED_ROUNDING_DEG = 5e-5;

/** A fixture and the decoded tiles it names, which the scorer under test is given. */
export type FixtureWithTiles = FixtureDocument & { readonly decodedTiles: readonly Tile[] };

/**
 * The reference's side of every near-boundary minute that can change the
 * Answer (`effectiveFreedom`), as overrides for the JS scorer.
 *
 * - **Sun in view**, at a listed minute of a Candidate: inside the window,
 *   from the reference's Spot for that Candidate when its Answer has one
 *   (in its sun intervals or not); outside it (Evening only, where it bears
 *   only on Last sun), from that Spot's Last sun, and left alone when it is
 *   before Last sun. For a Candidate the Answer does not show, from the
 *   fixture's sun track against that Candidate's Horizon profile.
 * - **Low sun**, at a listed minute of the window: from any reference Spot
 *   with the sun in view then (in its low-sun intervals or not); otherwise
 *   from the fixture's sun track.
 *
 * The stored sun track is rounded, so a side read from it is used only when
 * the rounding cannot change it; otherwise this throws, naming the minute.
 */
export function referenceSight(fixture: FixtureWithTiles): Required<SightOverrides> {
  const sunInView: Record<string, Record<number, boolean>> = {};
  const lowSun: Record<number, boolean> = {};
  const { answer, nearBoundary, sunTrack, query } = fixture;
  if (answer.window === undefined) {
    return { sunInView, lowSun };
  }
  const minuteOf = (iso: string) => (Date.parse(iso) - Date.parse(sunTrack.start)) / 60_000;
  const [start, end] = [minuteOf(answer.window.start), minuteOf(answer.window.end)];
  const inside = (intervals: readonly Interval[], m: number) =>
    intervals.some((interval) => minuteOf(interval.start) <= m && m < minuteOf(interval.end));
  const shown = new Map<string, Spot>();
  for (const spot of [...answer.spots, ...(answer.nearestSunBeyondLimit ? [answer.nearestSunBeyondLimit] : [])]) {
    shown.set(spot.candidateId, spot);
  }

  for (const [candidateId, minutes] of Object.entries(nearBoundary.candidates)) {
    for (const m of minutes) {
      const inWindow = start <= m && m < end;
      if (!inWindow && query.window !== "evening") {
        continue;
      }
      const spot = shown.get(candidateId);
      let side: boolean | undefined;
      if (spot === undefined) {
        side = sunSideFromTrack(fixture, candidateId, m);
      } else if (inWindow) {
        side = inside(spot.sunIntervals, m);
      } else {
        const last = spot.lastSun === undefined ? null : minuteOf(spot.lastSun);
        side = last === null || m > last ? false : m === last ? true : undefined;
      }
      if (side !== undefined) {
        (sunInView[candidateId] ??= {})[m] = side;
      }
    }
  }

  for (const m of nearBoundary.lowSunBand) {
    if (m < start || m >= end) {
      continue;
    }
    const witness = [...shown.values()].find((spot) => inside(spot.sunIntervals, m));
    lowSun[m] = witness ? inside(witness.lowSunIntervals, m) : lowSideFromTrack(fixture, m);
  }
  return { sunInView, lowSun };
}

/** Whether the reference had the sun in view at minute `m` of a Candidate, from the stored sun track. */
function sunSideFromTrack(fixture: FixtureWithTiles, candidateId: string, m: number): boolean {
  const [gridRef, index] = candidateId.split("/");
  const tile = fixture.decodedTiles.find((t) => t.gridRef === gridRef);
  if (tile === undefined) {
    throw new Error(`near-boundary Candidate ${candidateId} is not in the fixture's tiles`);
  }
  const codes = horizonProfileCodes(tile, Number(index));
  const azimuth = fixture.sunTrack.azimuth[m]!;
  const elevation = fixture.sunTrack.apparentElevation[m]!;
  // The profile is linear between samples, so over the azimuths the stored
  // value can stand for, it is extreme at an end or at a sample between them.
  const sample = Math.round(azimuth / PROFILE_STEP_DEG) * PROFILE_STEP_DEG;
  const azimuths = [azimuth - STORED_ROUNDING_DEG, azimuth, azimuth + STORED_ROUNDING_DEG];
  if (Math.abs(sample - azimuth) <= STORED_ROUNDING_DEG) azimuths.push(sample);
  const horizons = azimuths.map((a) => horizonAt(codes, a));
  if (elevation - STORED_ROUNDING_DEG > Math.max(...horizons)) return true;
  if (elevation + STORED_ROUNDING_DEG <= Math.min(...horizons)) return false;
  throw new Error(
    `cannot tell the reference's side at near-boundary ${candidateId} at minute ${m}: ` +
      `the stored sun track's rounding puts the sun on either side of its Horizon profile`,
  );
}

/** Whether the reference counted the sun as low at minute `m`, from the stored sun track. */
function lowSideFromTrack(fixture: FixtureWithTiles, m: number): boolean {
  const elevation = fixture.sunTrack.apparentElevation[m]!;
  for (const end of [LOW_SUN_MIN_DEG, LOW_SUN_MAX_DEG]) {
    if (Math.abs(elevation - end) <= STORED_ROUNDING_DEG) {
      throw new Error(
        `cannot tell the reference's low sun at minute ${m}: ${elevation} degrees is within the stored rounding of ${end}`,
      );
    }
  }
  return elevation >= LOW_SUN_MIN_DEG && elevation <= LOW_SUN_MAX_DEG;
}

/**
 * The differences between the JS Answer and the reference's that near-boundary
 * freedom does not explain (docs/fixtures.md, "Near-boundary minutes").
 *
 * When the Answers differ and the fixture has freedom, the Query is answered
 * again by `rescore`, the JS scorer with the reference's side of each
 * near-boundary minute forced (`referenceSight`). What still differs is
 * unexplained, whatever it is: a Spot member, the order of the list, the
 * status. With no freedom, every difference is unexplained.
 */
export async function unexplainedDifferences(
  actual: Answer,
  fixture: FixtureWithTiles,
  rescore: (overrides: SightOverrides) => Answer | Promise<Answer>,
): Promise<string[]> {
  const differences = answerDifferences(actual, fixture.answer);
  if (differences.length === 0 || !effectiveFreedom(fixture).any) {
    return differences;
  }
  return answerDifferences(await rescore(referenceSight(fixture)), fixture.answer);
}
