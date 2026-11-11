// The span the sky slot's cloud cover is averaged over (spec #27, "Cloud
// category"): the Morning window, or the last 3 h of the Evening window (all
// of it if shorter). The bounds are the scorer's own window plans, so `now`
// clips the span as it clips the window. `ciao_sun.reference.cloud.cloud_span`
// is the reference; both are held to fixtures/cloud/cases.json.
//
// Pure, like the scorer it reads: the request is `forecastSky`'s.

import type { Query } from "../contract";
import { planEvening } from "../scorer/evening";
import { planMorning } from "../scorer/morning";
import { TIME_ZONE } from "../solar/local-day";
import { sampleTimeMs, sunTrack } from "../solar/sun-track";
import type { CloudSpan } from "./forecast";

/** The evening span is this much of the Evening window's end. */
export const EVENING_CLOUD_SPAN_MIN = 180;

/** The instants C is averaged between, or null when the query has no window. */
export function cloudSpan(query: Query): CloudSpan | null {
  const track = sunTrack(query.origin.lat, query.origin.lon, query.date, TIME_ZONE);
  const plan = (query.window === "morning" ? planMorning : planEvening)(query, track);
  if ("status" in plan) {
    return null;
  }
  const start = query.window === "evening" ? Math.max(plan.start, plan.end - EVENING_CLOUD_SPAN_MIN) : plan.start;
  return { startMs: sampleTimeMs(track, start), endMs: sampleTimeMs(track, plan.end) };
}
