// The fallback: what an Answer lists when the sky is overcast or no reachable
// spot has sun. It works on either plan, Morning or Evening: it needs only the
// start of the plan and, for the spot beyond the limit, the plan's own
// Leave-by rule. `ciao_sun.reference.fallback` is the reference.

import type { Spot } from "../contract";
import { type World, compareCandidates } from "../router/world";
import { dedupe } from "./ranking";
import { type Scored, type Scoring, buildSpot, walkMinutes } from "./scoring";

/** Nearest first: walk in whole metres ascending, then candidateId ascending (grid ref, then index as a number). */
export function rankByWalk(world: World, among: readonly Scored[]): Scored[] {
  return [...among].sort((a, b) => a.walkM - b.walkM || compareCandidates(world, a.k, b.k));
}

/**
 * The nearest reachable spots that pass openness, de-duped, whatever their sun.
 *
 * Each is left for at the start of the window and says to stay for the
 * Duration target: the walk counts towards it, so the stay is the target.
 * Its sun fields are still the geometry's, as on a ranked spot.
 */
export function fallbackSpots(scoring: Scoring, targetMin: number): Spot[] {
  const reachable = scoring.scored.filter((candidate) => candidate.reachable);
  return dedupe(scoring.world, rankByWalk(scoring.world, reachable)).map((candidate) => ({
    ...buildSpot(scoring, candidate, scoring.plan.start, targetMin),
    stayMin: targetMin,
  }));
}

/**
 * The nearest spot with Sun minutes beyond max walk, within the 20 min cap.
 *
 * Nearest by `rankByWalk`. It is a spot with sun, so it is left for by the
 * plan's own Leave-by rule and has no "stay N min". Undefined when there is none.
 */
export function nearestSunBeyondLimit(scoring: Scoring, targetMin: number): Spot | undefined {
  const beyond = scoring.scored.filter((candidate) => !candidate.reachable && candidate.sunMinutes > 0);
  const nearest = rankByWalk(scoring.world, beyond)[0];
  if (nearest === undefined) {
    return undefined;
  }
  const { plan } = scoring;
  const leave = plan.leaveBy(nearest.inView, walkMinutes(nearest), plan, targetMin);
  return buildSpot(scoring, nearest, leave, targetMin);
}
