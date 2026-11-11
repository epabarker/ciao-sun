// The harness's own rules, on small hand-made cases: a comparison that cannot
// fail would hold the scorer to nothing.

import { describe, expect, it } from "vitest";

import type { Answer, Spot } from "../../src/contract";
import type { SunTrack } from "../../src/solar/sun-track";
import { FixtureSet, SYNTHETIC_PIN, pinFromEnvironment } from "./fixture-set";
import { answerDifferences, compareSunTrack, nearBoundaryFreedom } from "./parity";

const spot: Spot = {
  candidateId: "ST5873/5",
  name: "East Street",
  lat: 51.4589203,
  lon: -2.6036053,
  walkMetres: 160,
  walkMin: 2,
  leaveBy: "2026-12-21T15:33:00+00:00",
  sunIntervals: [{ start: "2026-12-21T13:30:00+00:00", end: "2026-12-21T15:52:00+00:00" }],
  lowSunIntervals: [],
  sunMinutes: 142,
  lowSunMinutes: 142,
  skyOpenness: 0.874,
  targetMet: true,
};
const answer: Answer = { status: "ranked", durationTargetMin: 20, spots: [spot] };
const withSpot = (change: Partial<Spot>): Answer => ({ ...answer, spots: [{ ...spot, ...change }] });

describe("Answer parity", () => {
  it("holds for equal Answers", () => {
    expect(answerDifferences(structuredClone(answer), answer)).toEqual([]);
  });

  it("allows Sky openness 0.001 and no more", () => {
    expect(answerDifferences(withSpot({ skyOpenness: 0.875 }), answer)).toEqual([]);
    expect(answerDifferences(withSpot({ skyOpenness: 0.876 }), answer)).toEqual([
      "spots[0].skyOpenness: 0.876, the reference has 0.874",
    ]);
  });

  it("allows 1e-9 on positions, walk minutes, Low-sun minutes and stay minutes", () => {
    expect(answerDifferences(withSpot({ lat: spot.lat + 5e-10, walkMin: 2 + 5e-10 }), answer)).toEqual([]);
    expect(answerDifferences(withSpot({ lat: spot.lat + 1e-7 }), answer)).toHaveLength(1);
    expect(answerDifferences(withSpot({ lowSunMinutes: 142.01 }), answer)).toHaveLength(1);
  });

  it("holds integers, strings, booleans and times exactly", () => {
    expect(answerDifferences(withSpot({ sunMinutes: 143 }), answer)).toHaveLength(1);
    expect(answerDifferences(withSpot({ walkMetres: 161 }), answer)).toHaveLength(1);
    expect(answerDifferences(withSpot({ targetMet: false }), answer)).toHaveLength(1);
    expect(answerDifferences(withSpot({ leaveBy: "2026-12-21T15:34:00+00:00" }), answer)).toEqual([
      'spots[0].leaveBy: "2026-12-21T15:34:00+00:00", the reference has "2026-12-21T15:33:00+00:00"',
    ]);
    expect(answerDifferences({ ...answer, status: "fallback" }, answer)).toHaveLength(1);
  });

  it("holds the order of spots and of intervals", () => {
    const other = { ...spot, candidateId: "ST5773/26", name: "West Row" };
    expect(
      answerDifferences({ ...answer, spots: [other, spot] }, { ...answer, spots: [spot, other] }),
    ).toEqual([
      'spots[0].candidateId: "ST5773/26", the reference has "ST5873/5"',
      'spots[0].name: "West Row", the reference has "East Street"',
      'spots[1].candidateId: "ST5873/5", the reference has "ST5773/26"',
      'spots[1].name: "East Street", the reference has "West Row"',
    ]);
    expect(answerDifferences({ ...answer, spots: [] }, answer)).toEqual([
      "spots: 0 entries, the reference has 1",
    ]);
  });

  it("wants a member absent from one Answer absent from the other", () => {
    expect(answerDifferences(withSpot({ stayMin: 30 }), answer)).toEqual([
      "spots[0].stayMin: 30, the reference has absent",
    ]);
    expect(answerDifferences(answer, { ...answer, lamp: true })).toEqual([
      "lamp: absent, the reference has true",
    ]);
  });
});

describe("solar parity", () => {
  const track = (azimuth: number[], apparentElevation: number[]): SunTrack => ({
    startMs: Date.UTC(2026, 11, 21),
    length: azimuth.length,
    azimuth: Float64Array.from(azimuth),
    elevation: Float64Array.from(apparentElevation),
    apparentElevation: Float64Array.from(apparentElevation),
    nominalSunrise: null,
    nominalSunset: null,
    solarNoon: 0,
  });
  const reference = {
    start: "2026-12-21T00:00:00+00:00",
    stepMin: 1,
    azimuth: [359.9981, 10],
    apparentElevation: [-61.2, -61.5],
  };

  it("measures the largest difference of the day, azimuths modulo 360", () => {
    const result = compareSunTrack(track([0.0031, 10.004], [-61.2, -61.52]), reference);

    expect(result.problems).toEqual([]);
    expect(result.worstAzimuthDeg).toBeCloseTo(0.005, 9);
    expect(result.worstApparentElevationDeg).toBeCloseTo(0.02, 9);
    expect(result.lowestApparentElevationDeg).toBe(-61.5);
  });

  it("wants the same start and the same number of samples", () => {
    const short = { ...track([0], [-61.2]), startMs: Date.UTC(2026, 11, 21, 1) };

    expect(compareSunTrack(short, reference).problems).toEqual([
      "start is 2026-12-21T01:00:00+00:00, the reference's is 2026-12-21T00:00:00+00:00",
      "1 samples, the reference has 2 of azimuth",
      "1 samples, the reference has 2 of apparentElevation",
    ]);
  });
});

describe("the committed synthetic set", () => {
  const set = new FixtureSet(SYNTHETIC_PIN);

  it("is the set under test unless the environment names another build", () => {
    expect(pinFromEnvironment({})).toEqual(SYNTHETIC_PIN);
    expect(
      pinFromEnvironment({ CIAO_SUN_FIXTURES_DATA_BASE: "/data", CIAO_SUN_FIXTURES_BUILD: "20270101a" }),
    ).toEqual({ dataBase: "/data", format: 1, build: "20270101a" });
    expect(() => pinFromEnvironment({ CIAO_SUN_FIXTURES_BUILD: "20270101a" })).toThrow(/both/);
  });

  it("refuses a build directory that is not the pinned build", () => {
    expect(() => new FixtureSet({ ...SYNTHETIC_PIN, build: "20261111b" })).toThrow();
  });

  it("has fifteen fixtures, ten of them with no near-boundary freedom", async () => {
    // docs/fixtures.md, "Near-boundary minutes".
    const fixtures = await Promise.all(set.entries.map((entry) => set.load(entry)));

    expect(fixtures).toHaveLength(15);
    expect(fixtures.filter((fixture) => !nearBoundaryFreedom(fixture).any)).toHaveLength(10);
  });

  it("lists morning-no-sun-in-reach's near-boundary minute inside its window", async () => {
    const entry = set.entries.find(({ id }) => id === "morning-no-sun-in-reach")!;
    const fixture = await set.load(entry);
    const freedom = nearBoundaryFreedom(fixture);
    const window = fixture.answer.window!;

    const minutes = Object.values(freedom.candidates).flat();
    expect(minutes.length).toBeGreaterThan(0);
    expect(minutes.some((minute) => minute >= window.start && minute < window.end)).toBe(true);
  });
});
