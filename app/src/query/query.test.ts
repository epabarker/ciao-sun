import { describe, expect, it } from "vitest";

import { parseOrigin } from "./origin";
import {
  PLANNING_POINT,
  buildQuery,
  chooseWindow,
  morningWindowOver,
  nextEveningDate,
  nextMorningDate,
} from "./query";

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

  it("is tomorrow from solar noon when Wake time + 3 h is later: the Morning window ends there (#62)", () => {
    // Solar noon at PLANNING_POINT on 2026-12-21 is 12:08 GMT.
    expect(nextMorningDate(at("2026-12-21T12:07:00Z"), "10:30")).toBe("2026-12-21");
    expect(nextMorningDate(at("2026-12-21T12:09:00Z"), "10:30")).toBe("2026-12-22");
  });

  it("reads the clock in Europe/London, whatever the device's zone", () => {
    // 00:30 in London on 1 July is still 30 June in UTC.
    expect(nextMorningDate(at("2026-07-01T00:30:00+01:00"), "07:00")).toBe("2026-07-01");
  });
});

// At PLANNING_POINT, from the Python reference's sun_track: Nominal sunset is
// 19:06 BST on 2026-09-23 and 16:03 GMT on 2026-12-20.
describe("the Evening window's date", () => {
  it("is today until Nominal sunset, and tomorrow from then", () => {
    expect(nextEveningDate(at("2026-09-23T19:05:59+01:00"), PLANNING_POINT)).toBe("2026-09-23");
    expect(nextEveningDate(at("2026-09-23T19:06:00+01:00"), PLANNING_POINT)).toBe("2026-09-24");
    expect(nextEveningDate(at("2026-12-20T16:30:00Z"), PLANNING_POINT)).toBe("2026-12-21");
  });
});

describe("the tab the app opens on", () => {
  it("is today's Morning before and during the Morning window", () => {
    expect(chooseWindow(at("2026-09-23T05:00:00+01:00"), "07:00", PLANNING_POINT)).toEqual({
      window: "morning",
      date: "2026-09-23",
    });
    expect(chooseWindow(at("2026-09-23T09:59:00+01:00"), "07:00", PLANNING_POINT).window).toBe("morning");
  });

  it("is today's Evening during the day, from the end of the Morning window until Nominal sunset", () => {
    // 10:00 is after the Morning window and before the Evening window starts at 13:03.
    expect(chooseWindow(at("2026-09-23T10:00:00+01:00"), "07:00", PLANNING_POINT)).toEqual({
      window: "evening",
      date: "2026-09-23",
    });
    expect(chooseWindow(at("2026-09-23T19:05:00+01:00"), "07:00", PLANNING_POINT).window).toBe("evening");
  });

  it("is tomorrow's Morning after Nominal sunset", () => {
    expect(chooseWindow(at("2026-09-23T19:06:00+01:00"), "07:00", PLANNING_POINT)).toEqual({
      window: "morning",
      date: "2026-09-24",
    });
    expect(chooseWindow(at("2026-12-20T21:00:00Z"), "07:30", PLANNING_POINT)).toEqual({
      window: "morning",
      date: "2026-12-21",
    });
  });

  it("leaves a Wake time after solar noon no Morning today: after Nominal sunset it is tomorrow's", () => {
    // Wake time 15:00: the Morning window would end at 18:00, but ends at solar noon (#62).
    expect(chooseWindow(at("2026-12-20T16:30:00Z"), "15:00", PLANNING_POINT)).toEqual({
      window: "morning",
      date: "2026-12-21",
    });
    expect(chooseWindow(at("2026-12-20T14:00:00Z"), "15:00", PLANNING_POINT).window).toBe("evening");
  });
});

describe("whether a Query's Morning window is over", () => {
  const q = (now?: string) =>
    buildQuery(
      { wakeTime: "07:00", date: "2026-12-21", sky: "clear", maxWalkMin: 15, origin: PLANNING_POINT },
      at(now ?? "2026-12-20T21:00:00Z"),
    );

  it("is when now, on the query's date, is at or after Wake time + 3 h", () => {
    expect(morningWindowOver(q("2026-12-21T09:59:00Z"))).toBe(false);
    expect(morningWindowOver(q("2026-12-21T10:00:00Z"))).toBe(true);
    expect(morningWindowOver(q("2026-12-21T17:30:00Z"))).toBe(true);
  });

  it("is from solar noon when Wake time + 3 h is later (#62)", () => {
    const late = (now: string) =>
      buildQuery(
        { wakeTime: "10:30", date: "2026-12-21", sky: "clear", maxWalkMin: 15, origin: PLANNING_POINT },
        at(now),
      );
    expect(morningWindowOver(late("2026-12-21T12:07:00Z"))).toBe(false);
    expect(morningWindowOver(late("2026-12-21T12:09:00Z"))).toBe(true);
  });

  it("is never for a query with no now, which plans another day", () => {
    expect(morningWindowOver(q())).toBe(false);
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

  it("asks for the tab's window", () => {
    expect(buildQuery(inputs, at("2026-09-23T12:00:00+01:00"), "evening")).toMatchObject({
      window: "evening",
      now: "2026-09-23T12:00:00+01:00",
    });
  });

  it("asks for at most the 20 min cap", () => {
    expect(buildQuery({ ...inputs, maxWalkMin: 30 }, at("2026-09-22T21:00:00+01:00")).maxWalkMin).toBe(20);
  });
});
