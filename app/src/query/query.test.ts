import { describe, expect, it } from "vitest";

import { parseOrigin } from "./origin";
import { buildQuery, nextMorningDate } from "./query";

const at = (iso: string) => Date.parse(iso);

describe("the Morning window's date", () => {
  it("is today until the Morning window ends, Wake time + 3 h", () => {
    expect(nextMorningDate(at("2026-09-23T05:00:00+01:00"), "07:00")).toBe("2026-09-23");
    expect(nextMorningDate(at("2026-09-23T09:59:00+01:00"), "07:00")).toBe("2026-09-23");
  });

  it("is tomorrow once today's Morning window is over, so that opening the app at night plans tomorrow", () => {
    expect(nextMorningDate(at("2026-09-23T10:00:00+01:00"), "07:00")).toBe("2026-09-24");
    expect(nextMorningDate(at("2026-12-31T23:30:00+00:00"), "07:00")).toBe("2027-01-01");
  });

  it("reads the clock in Europe/London, whatever the device's zone", () => {
    // 00:30 in London on 1 July is still 30 June in UTC.
    expect(nextMorningDate(at("2026-07-01T00:30:00+01:00"), "07:00")).toBe("2026-07-01");
  });
});

describe("a typed origin", () => {
  it("reads latitude, longitude in decimal degrees", () => {
    expect(parseOrigin("51.4589122, -2.6051884")).toEqual({ lat: 51.4589122, lon: -2.6051884 });
    expect(parseOrigin(" 51.45 -2.6 ")).toEqual({ lat: 51.45, lon: -2.6 });
  });

  it("refuses anything else", () => {
    expect(parseOrigin("")).toBeUndefined();
    expect(parseOrigin("BS6 5AA")).toBeUndefined();
    expect(parseOrigin("91, 0")).toBeUndefined();
  });
});

describe("the Query the sentence asks", () => {
  const inputs = {
    wakeTime: "07:00",
    date: "2026-09-23",
    sky: "partly" as const,
    maxWalkMin: 15,
    origin: { lat: 51.4589084, lon: -2.6059081 },
  };

  it("starts from now when the date is today", () => {
    expect(buildQuery(inputs, at("2026-09-23T07:42:30+01:00"))).toEqual({
      window: "morning",
      ...inputs,
      now: "2026-09-23T07:42:30+01:00",
    });
  });

  it("has no now for another day", () => {
    expect(buildQuery(inputs, at("2026-09-22T21:00:00+01:00"))).not.toHaveProperty("now");
  });

  it("asks for at most the 20 min cap", () => {
    expect(buildQuery({ ...inputs, maxWalkMin: 30 }, at("2026-09-22T21:00:00+01:00")).maxWalkMin).toBe(20);
  });
});
