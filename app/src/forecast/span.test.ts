// The span C is averaged over, from a Query: the JS port of
// `ciao_sun.reference.cloud.cloud_span`, held to the spans the Python side
// wrote into fixtures/cloud/cases.json and to its own unit cases.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import type { Query } from "../contract";
import { cloudSpan } from "./span";

interface CloudCase {
  name: string;
  query: Query;
  span: { start: string; end: string };
}

const shared = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../fixtures/cloud/cases.json", import.meta.url)), "utf8"),
) as { cases: CloudCase[] };

const query = (window: Query["window"], date: string, wakeTime: string, now?: string): Query => ({
  window,
  date,
  wakeTime,
  origin: { lat: 51.45, lon: -2.6 },
  maxWalkMin: 15,
  sky: "clear",
  ...(now === undefined ? {} : { now }),
});

describe("the cloud span of a query", () => {
  it.each(shared.cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    expect(cloudSpan(c.query)).toEqual({ startMs: Date.parse(c.span.start), endMs: Date.parse(c.span.end) });
  });

  it("is the last 3 h of an Evening window longer than that", () => {
    expect(cloudSpan(query("evening", "2026-06-21", "07:00"))).toEqual({
      startMs: Date.parse("2026-06-21T18:31:00+01:00"),
      endMs: Date.parse("2026-06-21T21:31:00+01:00"),
    });
  });

  it("starts at now when now clips the Morning window", () => {
    expect(cloudSpan(query("morning", "2026-12-21", "07:00", "2026-12-21T09:00:00+00:00"))).toEqual({
      startMs: Date.parse("2026-12-21T09:00:00Z"),
      endMs: Date.parse("2026-12-21T10:00:00Z"),
    });
  });

  it("is null when the query has no window", () => {
    // Wake at 11:00 in December: the Evening window would start after sunset.
    expect(cloudSpan(query("evening", "2026-12-21", "11:00"))).toBeNull();
    // Wake at 04:00: the Morning window ends before sunrise.
    expect(cloudSpan(query("morning", "2026-12-21", "04:00"))).toBeNull();
  });
});
