// The scorer: `(Query, tiles) -> Answer`, pure, with no DOM and no network.
//
// The JS client is canonical (ADR 0001); `ciao_sun.reference.scorer` is the
// reference its golden fixtures come from, and every rule here is that one's
// (spec #27, "Scoring rules"). The rules live beside it:
//
// - `windows`, `morning`: the window, its weights and its Leave-by rule
// - `sunview`: sun in view, the 0-30 degree band, Sky openness
// - `../router/world`: tiles joined into one walk graph; the origin snap and the walk
// - `scoring`: per-Candidate scores, and a scored Candidate as a Spot
// - `ranking`: the deterministic order and the de-dupe
// - `lamp`: the lamp message
//
// Morning `ranked` Answers are written (#43). The Evening window, the
// fallback, lamp-only, no-evening-window and not-covered are #44: each throws
// where it will go.

import type { Answer, Query, Sky, Spot, Status, WindowName } from "../contract";
import { joinTiles } from "../router/world";
import { TIME_ZONE } from "../solar/local-day";
import { type SunTrack, sunTrack } from "../solar/sun-track";
import type { Tile } from "../tile/decode";
import { lamp } from "./lamp";
import { planMorning } from "./morning";
import { dedupe, rankByLowSun } from "./ranking";
import { buildSpot, score, walkMinutes } from "./scoring";
import { type WindowPlan, clock, eventClock } from "./windows";

export const DURATION_TARGET_MIN: Record<Sky, 10 | 20 | 30> = { clear: 10, partly: 20, overcast: 30 };

/**
 * A planner returns the query's window, or the whole Answer when there is no
 * window to rank in (lamp-only, no-evening-window).
 */
export type Planner = (query: Query, track: SunTrack) => WindowPlan | Answer;

const PLANNERS: Record<WindowName, Planner> = {
  morning: planMorning,
  evening: () => {
    throw new Error("the Evening window is not written yet (#44)");
  },
};

function isAnswer(plan: WindowPlan | Answer): plan is Answer {
  return "status" in plan;
}

/** The Answer to a Query over decoded tiles. */
export function answer(query: Query, tiles: readonly Tile[]): Answer {
  const track = sunTrack(query.origin.lat, query.origin.lon, query.date, TIME_ZONE);
  const plan = PLANNERS[query.window](query, track);
  if (isAnswer(plan)) {
    return plan;
  }

  const world = joinTiles(tiles);
  const scoring = score(world, query, track, plan);
  const targetMin = DURATION_TARGET_MIN[query.sky];

  const sunny = scoring.scored.filter((candidate) => candidate.reachable && candidate.sunMinutes > 0);
  if (query.sky === "overcast" || sunny.length === 0) {
    throw new Error("fallback Answers are not written yet (#44)");
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
