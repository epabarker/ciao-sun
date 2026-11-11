// The deterministic ranking and the greedy de-dupe, shared by every list an
// Answer shows. `ciao_sun.reference.ranking` is the reference.

import { type World, compareCandidates, distanceM } from "../router/world";
import type { Scored } from "./scoring";

export const DEDUPE_RADIUS_M = 200;
export const SPOTS_SHOWN = 5;

/**
 * Best first: Low-sun minutes to 0.01 min descending, then walk in whole
 * metres ascending, then candidateId ascending (grid ref, then index as a
 * number).
 */
export function rankByLowSun(world: World, among: readonly Scored[]): Scored[] {
  return [...among].sort(
    (a, b) =>
      b.lowSunHundredths - a.lowSunHundredths || a.walkM - b.walkM || compareCandidates(world, a.k, b.k),
  );
}

/**
 * Greedy de-dupe of Scored Candidates given in rank order. Keep a Candidate;
 * drop any later one with the same Spot name, or within 200 m of a kept one.
 * Stop at `keep` kept.
 */
export function dedupe(world: World, ranked: readonly Scored[], keep: number = SPOTS_SHOWN): Scored[] {
  const kept: Scored[] = [];
  for (const candidate of ranked) {
    if (kept.length === keep) {
      break;
    }
    const k = candidate.k;
    const apart = kept.every(
      ({ k: other }) =>
        world.name[k] !== world.name[other] &&
        distanceM(world.lat[k]!, world.lon[k]!, world.lat[other]!, world.lon[other]!) > DEDUPE_RADIUS_M,
    );
    if (apart) {
      kept.push(candidate);
    }
  }
  return kept;
}
