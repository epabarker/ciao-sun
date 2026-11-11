// The scorer: `(Query, tiles) -> Answer`, pure, with no DOM and no network.
//
// The JS client is canonical (ADR 0001); `ciao_sun.reference.scorer` is the
// reference its golden fixtures come from, and every rule here is that one's
// (spec #27, "Scoring rules"). The rules live beside it:
//
// - `windows`, `morning`, `evening`: the window, its weights and its Leave-by rule
// - `sunview`: sun in view, the 0-30 degree band, Sky openness, Last sun
// - `../router/world`: tiles joined into one walk graph; the origin snap and the walk
// - `scoring`: per-Candidate scores, and a scored Candidate as a Spot
// - `ranking`: the deterministic order and the de-dupe
// - `fallback`: the nearest open spots, and the nearest sun beyond max walk
// - `lamp`: the lamp message and the lamp-only Answer
// - `coverage`: whether the origin is covered

import type { Answer, Query, Sky, Spot, Status, WindowName } from "../contract";
import { joinTiles } from "../router/world";
import { TIME_ZONE } from "../solar/local-day";
import { type SunTrack, sunTrack } from "../solar/sun-track";
import type { Tile } from "../tile/decode";
import { type CoverageGeometry, contains } from "./coverage";
import { lamp } from "./lamp";
import { planEvening } from "./evening";
import { fallbackSpots, nearestSunBeyondLimit } from "./fallback";
import { planMorning } from "./morning";
import { dedupe, rankByLowSun } from "./ranking";
import { type SightOverrides, buildSpot, score, walkMinutes } from "./scoring";
import { type WindowPlan, clock, eventClock } from "./windows";

export const DURATION_TARGET_MIN: Record<Sky, 10 | 20 | 30> = { clear: 10, partly: 20, overcast: 30 };

/**
 * A planner returns the query's window, or the whole Answer when there is no
 * window to rank in (lamp-only, no-evening-window).
 */
export type Planner = (query: Query, track: SunTrack) => WindowPlan | Answer;

const PLANNERS: Record<WindowName, Planner> = {
  morning: planMorning,
  evening: planEvening,
};

function isAnswer(plan: WindowPlan | Answer): plan is Answer {
  return "status" in plan;
}

/**
 * The Answer to a Query over decoded tiles.
 *
 * `coverage` is the build's coverage polygon (the manifest's `coverage`). An
 * origin outside it is not covered, whatever the window; without one, every
 * origin is answered.
 */
export function answer(query: Query, tiles: readonly Tile[], coverage?: CoverageGeometry): Answer {
  return answerWith(query, tiles, coverage);
}

/**
 * `answer`, with sun in view and low sun forced at the given minutes. Only the
 * parity harness passes `overrides`, to re-run a fixture's Query with the
 * reference's side of each near-boundary minute (docs/fixtures.md).
 */
export function answerWith(
  query: Query,
  tiles: readonly Tile[],
  coverage?: CoverageGeometry,
  overrides?: SightOverrides,
): Answer {
  if (coverage !== undefined && !contains(coverage, query.origin.lat, query.origin.lon)) {
    return { status: "not-covered", spots: [] };
  }
  const track = sunTrack(query.origin.lat, query.origin.lon, query.date, TIME_ZONE);
  const plan = PLANNERS[query.window](query, track);
  if (isAnswer(plan)) {
    return plan;
  }

  const world = joinTiles(tiles);
  const scoring = score(world, query, track, plan, overrides);
  const targetMin = DURATION_TARGET_MIN[query.sky];

  const sunny = scoring.scored.filter((candidate) => candidate.reachable && candidate.sunMinutes > 0);
  if (query.sky === "overcast" || sunny.length === 0) {
    const fallback = windowedAnswer("fallback", fallbackSpots(scoring, targetMin), query, track, plan);
    const beyond = query.sky === "overcast" ? undefined : nearestSunBeyondLimit(scoring, targetMin);
    if (beyond !== undefined) fallback.nearestSunBeyondLimit = beyond;
    return fallback;
  }

  const spots = dedupe(world, rankByLowSun(world, sunny)).map((candidate) => {
    const leave = plan.leaveBy(candidate.inView, walkMinutes(candidate), plan, targetMin);
    return buildSpot(scoring, candidate, leave, targetMin);
  });
  return windowedAnswer("ranked", spots, query, track, plan);
}

/** An Answer that has a window, with the fields every such Answer carries. */
export function windowedAnswer(
  status: Status,
  spots: Spot[],
  query: Query,
  track: SunTrack,
  plan: WindowPlan,
): Answer {
  const out: Answer = {
    status,
    window: {
      start: clock(track, plan.start),
      end: clock(track, plan.end),
      axisStart: clock(track, plan.axisStart),
      axisEnd: clock(track, plan.axisEnd),
    },
    solarNoon: eventClock(track, track.solarNoon)!,
    durationTargetMin: DURATION_TARGET_MIN[query.sky],
    spots,
  };
  const sunrise = eventClock(track, track.nominalSunrise);
  const sunset = eventClock(track, track.nominalSunset);
  if (sunrise !== undefined) out.nominalSunrise = sunrise;
  if (sunset !== undefined) out.nominalSunset = sunset;
  if (query.window === "morning") out.lamp = lamp(query, track);
  return out;
}
