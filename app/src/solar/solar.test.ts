import { describe, expect, it } from "vitest";

import { localDay, toLocalIso } from "./local-day";
import { refractionDeg, sunTrack } from "./sun-track";

const BRISTOL = { lat: 51.45, lon: -2.6 };

describe("refraction (docs/solar-model.md check values)", () => {
  it.each([
    [-5, 0.744129],
    [-0.833, 0.618185],
    [-0.5667, 0.572663],
    [0, 0.483032],
    [1, 0.362398],
    [5, 0.161235],
    [30, 0.0291],
  ])("at a geometric elevation of %f degrees is %f degrees", (elevation, refraction) => {
    expect(refractionDeg(elevation)).toBeCloseTo(refraction, 6);
  });

  it("is held at its peak below the floor, so it has no switch-on step", () => {
    expect(refractionDeg(-90)).toBe(refractionDeg(-1.95));
    expect(refractionDeg(-1.9)).toBeLessThan(refractionDeg(-1.95));
    expect(refractionDeg(-0.84) - refractionDeg(-0.83)).toBeLessThan(0.01);
  });
});

describe("the sun track of the worked example: Bristol, 2026-12-21", () => {
  const track = sunTrack(BRISTOL.lat, BRISTOL.lon, "2026-12-21");
  const minute = (hhmm: string) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3));

  it("covers every whole minute of the local day", () => {
    expect(track.length).toBe(1440);
    expect(track.azimuth).toHaveLength(1440);
    expect(toLocalIso(track.startMs, "Europe/London")).toBe("2026-12-21T00:00:00+00:00");
  });

  it.each([
    ["07:00", 114.5324, -10.5646, -9.8205],
    ["08:13", 128.2538, -0.8762, -0.2506],
    ["12:08", 179.889, 15.1106, 15.1714],
    ["16:04", 231.7584, -0.885, -0.2579],
  ])("at %s the sun is at azimuth %f, geometric %f, apparent %f", (time, az, geometric, apparent) => {
    const i = minute(time);
    expect(Math.abs(track.azimuth[i]! - az)).toBeLessThan(0.0002);
    expect(Math.abs(track.elevation[i]! - geometric)).toBeLessThan(0.0002);
    expect(Math.abs(track.apparentElevation[i]! - apparent)).toBeLessThan(0.0002);
  });

  it("has Nominal sunrise at 08:13, solar noon at 12:08 and Nominal sunset at 16:04", () => {
    expect(track.nominalSunrise).toBe(minute("08:13"));
    expect(track.solarNoon).toBe(minute("12:08"));
    expect(track.nominalSunset).toBe(minute("16:04"));
  });
});

describe("a sun track covers one local civil day", () => {
  it("of 1,380 minutes when the clocks go forward", () => {
    const track = sunTrack(BRISTOL.lat, BRISTOL.lon, "2026-03-29");
    expect(track.length).toBe(1380);
    expect(toLocalIso(track.startMs, "Europe/London")).toBe("2026-03-29T00:00:00+00:00");
    expect(toLocalIso(track.startMs + 1379 * 60_000, "Europe/London")).toBe(
      "2026-03-29T23:59:00+01:00",
    );
  });

  it("of 1,500 minutes when the clocks go back", () => {
    const track = sunTrack(BRISTOL.lat, BRISTOL.lon, "2026-10-25");
    expect(track.length).toBe(1500);
    expect(toLocalIso(track.startMs, "Europe/London")).toBe("2026-10-25T00:00:00+01:00");
    expect(toLocalIso(track.startMs + 1499 * 60_000, "Europe/London")).toBe(
      "2026-10-25T23:59:00+00:00",
    );
  });

  it("in the query's time zone, not the machine's", () => {
    expect(localDay("2026-06-21", "Europe/London")).toEqual({
      startMs: Date.UTC(2026, 5, 20, 23, 0),
      minutes: 1440,
    });
    expect(localDay("2026-06-21", "America/New_York").startMs).toBe(Date.UTC(2026, 5, 21, 4, 0));
  });
});

describe("a day on which the sun never crosses -0.833 degrees", () => {
  it("has no Nominal sunrise or sunset in the polar night, but still a solar noon", () => {
    const track = sunTrack(78.22, 15.65, "2026-12-21", "Arctic/Longyearbyen");
    expect(track.nominalSunrise).toBeNull();
    expect(track.nominalSunset).toBeNull();
    expect(Math.max(...track.elevation)).toBeLessThan(-0.833);
    // Longyearbyen is 15.65 E on UTC+1: the sun transits a few minutes before 12:00.
    expect(track.solarNoon).toBeGreaterThan(11 * 60 + 45);
    expect(track.solarNoon).toBeLessThan(12 * 60);
  });

  it("has neither under the midnight sun", () => {
    const track = sunTrack(78.22, 15.65, "2026-06-21", "Arctic/Longyearbyen");
    expect(track.nominalSunrise).toBeNull();
    expect(track.nominalSunset).toBeNull();
    expect(Math.min(...track.elevation)).toBeGreaterThan(-0.833);
  });
});

describe("times are written as the reference writes them", () => {
  it.each([
    [Date.UTC(2026, 8, 23, 5, 58), "2026-09-23T06:58:00+01:00"],
    [Date.UTC(2027, 0, 15, 16, 31), "2027-01-15T16:31:00+00:00"],
  ])("%i is %s in Europe/London", (ms, iso) => {
    expect(toLocalIso(ms, "Europe/London")).toBe(iso);
    expect(Date.parse(iso)).toBe(ms);
  });
});
