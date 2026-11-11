// Scoring every Candidate that could be shown, and turning one into a Spot.
// `ciao_sun.reference.scoring` is the reference.

import { MAX_WALK_CAP_MIN, type Interval, type Query, type Spot } from "../contract";
import {
  WALK_SPEED_M_PER_MIN,
  type World,
  candidateCount,
  candidateId,
  profileCodesOf,
  walkMetres,
} from "../router/world";
import type { SunTrack } from "../solar/sun-track";
import { OPENNESS_CUTOFF, lastSun, lowSun, opennessSector, runs, skyOpenness, sunInView } from "./sunview";
import { type WindowPlan, clock } from "./windows";

/**
 * One Candidate within the 20 min walk cap whose Sky openness passes the
 * cut-off. Candidates beyond the query's max walk are scored too
 * (`reachable` is false), because a fallback may name the nearest sun beyond
 * the limit.
 */
export interface Scored {
  /** Index into the World's Candidates. */
  readonly k: number;
  readonly walkM: number;
  /** Within the query's max walk. */
  readonly reachable: boolean;
  readonly skyOpenness: number;
  /** Per window minute, 1 when the sun is in view. */
  readonly inView: Uint8Array;
  readonly sunMinutes: number;
  /** Low-sun minutes x 100, rounded half up: the ranking's primary key. */
  readonly lowSunHundredths: number;
}

/**
 * Sun in view and low sun forced at some minutes (sun-track indexes), over
 * what the geometry says. The parity harness uses it for near-boundary
 * minutes; an Answer for a person never has any.
 */
export interface SightOverrides {
  /** Per candidateId, per minute: whether the sun is in view there. */
  readonly sunInView?: Readonly<Record<string, Readonly<Record<number, boolean>>>>;
  /** Per minute: whether the sun is at 0-30 degrees. */
  readonly lowSun?: Readonly<Record<number, boolean>>;
}

/** `mask`, which holds minutes `start` onwards, with `forced` applied where it falls inside. */
function applyForced(mask: Uint8Array, start: number, forced: Readonly<Record<number, boolean>> | undefined): Uint8Array {
  if (forced !== undefined) {
    for (const [minute, value] of Object.entries(forced)) {
      const i = Number(minute) - start;
      if (i >= 0 && i < mask.length) mask[i] = value ? 1 : 0;
    }
  }
  return mask;
}

/** What every Scored Candidate of one query shares. */
export interface Scoring {
  readonly world: World;
  readonly track: SunTrack;
  readonly plan: WindowPlan;
  /** Per window minute, 1 when the sun is at 0-30 degrees. */
  readonly low: Uint8Array;
  /** In World order. */
  readonly scored: readonly Scored[];
  readonly overrides: SightOverrides | undefined;
}

export function score(
  world: World,
  query: Query,
  track: SunTrack,
  plan: WindowPlan,
  overrides?: SightOverrides,
): Scoring {
  const capM = MAX_WALK_CAP_MIN * WALK_SPEED_M_PER_MIN;
  const walks = walkMetres(world, query.origin.lat, query.origin.lon, capM);
  const sector = opennessSector(track, plan.unclippedStart, plan.end);
  const low = applyForced(lowSun(track, plan.start, plan.end), plan.start, overrides?.lowSun);
  const maxWalkM = query.maxWalkMin * WALK_SPEED_M_PER_MIN;
  const { weightNumerators: weights, weightDenominator: denominator } = plan;

  const scored: Scored[] = [];
  for (let k = 0; k < candidateCount(world); k++) {
    const walkM = walks[k]!;
    if (walkM < 0) {
      continue;
    }
    const codes = profileCodesOf(world, k);
    const openness = skyOpenness(codes, sector);
    if (!(openness >= OPENNESS_CUTOFF)) {
      continue;
    }
    const inView = applyForced(
      sunInView(codes, track, plan.start, plan.end),
      plan.start,
      overrides?.sunInView?.[candidateId(world, k)],
    );
    let sunMinutes = 0;
    let weighted = 0;
    for (let i = 0; i < inView.length; i++) {
      if (inView[i] === 1) {
        sunMinutes += 1;
        if (low[i] === 1) {
          weighted += weights[i]!;
        }
      }
    }
    scored.push({
      k,
      walkM,
      reachable: walkM <= maxWalkM,
      skyOpenness: openness,
      inView,
      sunMinutes,
      lowSunHundredths: Math.floor((200 * weighted + denominator) / (2 * denominator)),
    });
  }
  return { world, track, plan, low, scored, overrides };
}

/** A Scored Candidate's walk in minutes: its whole metres at the walking speed. */
export function walkMinutes(candidate: Scored): number {
  return candidate.walkM / WALK_SPEED_M_PER_MIN;
}

/**
 * A Scored Candidate as a Spot that is left for at minute `leave`.
 *
 * The Duration target is met when the walk plus the Sun minutes from arrival
 * to the window's end reach it. Arrival is `leave` plus the walk rounded up to
 * whole minutes.
 */
export function buildSpot(scoring: Scoring, candidate: Scored, leave: number, targetMin: number): Spot {
  const { world, track, plan, low, overrides } = scoring;
  const { k, inView } = candidate;
  const walkMin = walkMinutes(candidate);
  const arrival = leave + Math.ceil(walkMin);
  let sunFromArrival = 0;
  for (let i = Math.max(arrival - plan.start, 0); i < inView.length; i++) {
    sunFromArrival += inView[i]!;
  }
  const intervals = (mask: Uint8Array): Interval[] =>
    runs(mask).map(([a, b]) => ({ start: clock(track, plan.start + a), end: clock(track, plan.start + b) }));
  const inViewLow = inView.map((v, i) => v & low[i]!);

  const spot: Spot = {
    candidateId: candidateId(world, k),
    name: world.name[k]!,
    lat: world.lat[k]!,
    lon: world.lon[k]!,
    walkMetres: candidate.walkM,
    walkMin,
    leaveBy: clock(track, leave),
    sunIntervals: intervals(inView),
    lowSunIntervals: intervals(inViewLow),
    sunMinutes: candidate.sunMinutes,
    lowSunMinutes: candidate.lowSunHundredths / 100,
    skyOpenness: Math.floor(candidate.skyOpenness * 1000 + 0.5) / 1000,
    targetMet: walkMin + sunFromArrival >= targetMin,
  };
  if (plan.reportsLastSun) {
    const last = lastSun(profileCodesOf(world, k), track, overrides?.sunInView?.[spot.candidateId]);
    if (last !== null) spot.lastSun = clock(track, last);
  }
  return spot;
}
