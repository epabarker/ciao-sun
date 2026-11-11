// The harness's own rules, on small hand-made cases: a comparison that cannot
// fail would hold the scorer to nothing.

import { describe, expect, it } from "vitest";

import type { Answer, Query, Spot } from "../../src/contract";
import { answerWith } from "../../src/scorer/answer";
import type { SightOverrides } from "../../src/scorer/scoring";
import { type SunTrack, sunTrack } from "../../src/solar/sun-track";
import { PROFILE_SAMPLES, type Tile } from "../../src/tile/decode";
import {
  type FixtureDocument,
  FixtureSet,
  type LoadedFixture,
  SYNTHETIC_PIN,
  pinFromEnvironment,
} from "./fixture-set";
import {
  answerDifferences,
  compareSunTrack,
  effectiveFreedom,
  nearBoundaryFreedom,
  referenceSight,
  unexplainedDifferences,
} from "./parity";

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

  it("allows 1e-9 on positions, walk minutes and Low-sun minutes", () => {
    expect(answerDifferences(withSpot({ lat: spot.lat + 5e-10, walkMin: 2 + 5e-10 }), answer)).toEqual([]);
    expect(answerDifferences(withSpot({ lat: spot.lat + 1e-7 }), answer)).toHaveLength(1);
    expect(answerDifferences(withSpot({ lowSunMinutes: 142.01 }), answer)).toHaveLength(1);
  });

  it("holds integers, strings, booleans and times exactly", () => {
    expect(answerDifferences(withSpot({ sunMinutes: 143 }), answer)).toHaveLength(1);
    expect(answerDifferences(withSpot({ walkMetres: 161 }), answer)).toHaveLength(1);
    expect(answerDifferences(withSpot({ stayMin: 22 + 5e-10 }), withSpot({ stayMin: 22 }))).toHaveLength(1);
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

  it("has every status of the Answer contract, so fixture parity covers each one", () => {
    // Spec #27, "The Query -> Answer contract".
    const statuses = ["ranked", "fallback", "lamp-only", "no-evening-window", "not-covered"];

    expect([...new Set(set.entries.map((entry) => entry.status))].sort()).toEqual(statuses.sort());
  });

  it("reads the reference's side of every near-boundary minute: re-run with it, each Answer is unchanged", async () => {
    // Real near-boundary minutes, sides read from the reference's Answer and
    // its sun track: forcing them must not move the JS off the reference.
    const fixtures = await Promise.all(set.entries.map((entry) => set.load(entry)));
    const free = fixtures.filter((f) => effectiveFreedom(f).any);

    expect(free.map((f) => f.id).sort()).toEqual([
      "evening-march-equinox-now",
      "evening-summer-solstice",
      "morning-no-sun-in-reach",
    ]);
    for (const f of free) {
      const rerun = answerWith(f.query, f.decodedTiles, f.coverage, referenceSight(f));
      expect(answerDifferences(rerun, f.answer), f.id).toEqual([]);
    }
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

describe("near-boundary freedom", () => {
  // Minute 840 of 2026-12-21 is 14:00, inside the window; minute 600 is 10:00, before it.
  const fixture = (window: "morning" | "evening", minutes: number[], lowSunBand: number[] = []): FixtureDocument => ({
    query: {
      window,
      date: "2026-12-21",
      wakeTime: "07:30",
      origin: { lat: 51.4589122, lon: -2.6051884 },
      maxWalkMin: 15,
      sky: "clear",
    },
    tiles: ["ST5873"],
    answer: {
      ...answer,
      window: {
        start: "2026-12-21T13:30:00+00:00",
        end: "2026-12-21T16:04:00+00:00",
        axisStart: "2026-12-21T13:04:00+00:00",
        axisEnd: "2026-12-21T16:04:00+00:00",
      },
    },
    sunTrack: { start: "2026-12-21T00:00:00+00:00", stepMin: 1, azimuth: [], apparentElevation: [] },
    nearBoundary: { toleranceDeg: 0.01, candidates: { "ST5873/5": minutes }, lowSunBand },
  });

  it("counts a morning minute outside the window as none, but not an evening one: Last sun is looked for all day", () => {
    expect(effectiveFreedom(fixture("morning", [840])).any).toBe(true);
    expect(effectiveFreedom(fixture("morning", [600])).any).toBe(false);
    expect(effectiveFreedom(fixture("evening", [600])).any).toBe(true);
    expect(effectiveFreedom(fixture("morning", [], [600])).any).toBe(false);
    expect(effectiveFreedom(fixture("morning", [], [840])).any).toBe(true);
  });

  it("leaves every Morning ranked fixture of the synthetic set none: their Answers must match exactly", async () => {
    const set = new FixtureSet(SYNTHETIC_PIN);
    const fixtures = await Promise.all(set.entries.map((entry) => set.load(entry)));
    const morningRanked = fixtures.filter(
      (f) => f.query.window === "morning" && f.answer.status === "ranked",
    );

    expect(morningRanked).toHaveLength(5);
    expect(morningRanked.filter((f) => effectiveFreedom(f).any).map((f) => f.id)).toEqual([]);
  });
});

describe("a near-boundary flip", () => {
  // A hand-made world: node O, where the Query stands, and node P 100 m east.
  // Candidates hang off O, `offsetCm` from it and `northM` north of it, under
  // open sky (storage code 0, a Horizon profile at -2 degrees), so the sun is
  // in view and low all through the 2026-03-20 Morning window, 06:30 to 09:30:
  // minutes 390 to 569 of the day.
  const O = { latE7: 514_589_000, lonE7: -26_052_000 };
  const P = { latE7: 514_589_000, lonE7: -26_037_560 };
  function world(candidates: { offsetCm: number; northM: number }[]): Tile {
    const count = candidates.length;
    return {
      gridRef: "ST5873",
      names: candidates.map((_, k) => `Spot ${k}`),
      candidates: {
        latE7: Int32Array.from(candidates, ({ northM }) => O.latE7 + Math.round(northM * 90)),
        lonE7: new Int32Array(count).fill(O.lonE7),
        nodeIndex: new Uint32Array(count),
        offsetCm: Uint32Array.from(candidates, ({ offsetCm }) => offsetCm),
        nameIndex: Uint32Array.from(candidates, (_, k) => k),
        profileCodes: new Uint8Array(count * PROFILE_SAMPLES),
      },
      walkGraph: {
        nodeId: Float64Array.of(1, 2),
        nodeLatE7: Int32Array.of(O.latE7, P.latE7),
        nodeLonE7: Int32Array.of(O.lonE7, P.lonE7),
        edgeFrom: Uint32Array.of(0),
        edgeTo: Uint32Array.of(1),
        edgeLengthCm: Uint32Array.of(10_000),
      },
    };
  }
  // A, 4 m away, and B, 20 m away and 300 m north of A: neither de-dupes the other.
  const tiles = [world([{ offsetCm: 449, northM: 0 }, { offsetCm: 2_000, northM: 300 }])];
  const [A, B] = ["ST5873/0", "ST5873/1"];
  const query: Query = {
    window: "morning",
    date: "2026-03-20",
    wakeTime: "06:30",
    origin: { lat: O.latE7 / 1e7, lon: O.lonE7 / 1e7 },
    maxWalkMin: 15,
    sky: "clear",
  };
  const rescore = (q: Query, on = tiles) => (overrides: SightOverrides) => answerWith(q, on, undefined, overrides);

  /**
   * The fixture a reference would write if its sun were on the other side at
   * the minutes `flipped` forces: its Answer is the JS's with those flips,
   * and it lists `listed` as near-boundary minutes.
   */
  function fixtureWith(
    q: Query,
    flipped: SightOverrides,
    listed: Record<string, number[]>,
    lowSunBand: number[] = [],
    on: Tile[] = tiles,
  ): LoadedFixture {
    const track = sunTrack(q.origin.lat, q.origin.lon, q.date);
    const round = (values: Float64Array) => Array.from(values, (v) => Math.round(v * 1e4) / 1e4);
    return {
      id: "hand-made",
      query: q,
      tiles: ["ST5873"],
      answer: answerWith(q, on, undefined, flipped),
      sunTrack: {
        start: "2026-03-20T00:00:00+00:00",
        stepMin: 1,
        azimuth: round(track.azimuth),
        apparentElevation: round(track.apparentElevation),
      },
      nearBoundary: { toleranceDeg: 0.01, candidates: listed, lowSunBand },
      decodedTiles: on,
      coverage: { type: "Polygon", coordinates: [] },
    };
  }

  describe("that reorders the list", () => {
    // Without the flip A and B tie on Low-sun minutes and the nearer, A, comes
    // first. With A out of the sun at 06:30, B leads by a minute.
    const flipped = { sunInView: { [A]: { 390: false } } };

    it("is excused when the minute is listed for that Candidate", async () => {
      const f = fixtureWith(query, flipped, { [A]: [390] });
      const plain = answerWith(query, tiles);

      expect(plain.spots.map((s) => s.candidateId)).toEqual([A, B]);
      expect(f.answer.spots.map((s) => s.candidateId)).toEqual([B, A]);
      expect(await unexplainedDifferences(plain, f, rescore(query))).toEqual([]);
    });

    it("still fails when the minute is not listed, or listed for the other Candidate", async () => {
      const plain = answerWith(query, tiles);

      for (const listed of [{}, { [B]: [390] }, { [A]: [391] }]) {
        const f = fixtureWith(query, flipped, listed);
        expect(await unexplainedDifferences(plain, f, rescore(query)), JSON.stringify(listed)).toContain(
          `spots[0].candidateId: "${A}", the reference has "${B}"`,
        );
      }
    });

    it("still fails on a difference no flip can cause", async () => {
      const f = fixtureWith(query, flipped, { [A]: [390] });
      f.answer = { ...f.answer, lamp: true, spots: [{ ...f.answer.spots[0]!, walkMetres: 21 }, f.answer.spots[1]!] };

      expect(await unexplainedDifferences(answerWith(query, tiles), f, rescore(query))).toEqual([
        "spots[0].walkMetres: 20, the reference has 21",
        "lamp: false, the reference has true",
      ]);
    });
  });

  describe("that changes who makes the top 5", () => {
    // Six Candidates tie on Low-sun minutes, 1 to 6 m away, 300 m apart: the
    // nearest five are listed. With the 5th out of the sun at 06:30, it drops
    // to 6th and the 6th takes its place, as on a saturated Bristol list.
    const six = [world([1, 2, 3, 4, 5, 6].map((m, k) => ({ offsetCm: m * 100, northM: k * 300 })))];
    const [fifth, sixth] = ["ST5873/4", "ST5873/5"];
    const flipped = { sunInView: { [fifth]: { 390: false } } };

    it("is excused when the minute is listed for the Candidate that drops out", async () => {
      const f = fixtureWith(query, flipped, { [fifth]: [390] }, [], six);
      const plain = answerWith(query, six);

      expect(plain.spots.map((s) => s.candidateId)).toContain(fifth);
      expect(f.answer.spots.map((s) => s.candidateId)).toEqual(["ST5873/0", "ST5873/1", "ST5873/2", "ST5873/3", sixth]);
      expect(await unexplainedDifferences(plain, f, rescore(query, six))).toEqual([]);
    });

    it("still fails when the minute is not listed", async () => {
      const f = fixtureWith(query, flipped, { [sixth]: [390] }, [], six);

      expect(await unexplainedDifferences(answerWith(query, six), f, rescore(query, six))).toContain(
        `spots[4].candidateId: "${fifth}", the reference has "${sixth}"`,
      );
    });
  });

  describe("that changes the status", () => {
    // `now` leaves one minute of the window, 09:29 (minute 569). With the sun
    // out of view there at both Candidates, no reachable spot has sun.
    const late = { ...query, now: "2026-03-20T09:29:00Z" };
    const flipped = { sunInView: { [A]: { 569: false }, [B]: { 569: false } } };

    it("is excused when the minute is listed for every Candidate with sun", async () => {
      const f = fixtureWith(late, flipped, { [A]: [569], [B]: [569] });
      const plain = answerWith(late, tiles);

      expect([plain.status, f.answer.status]).toEqual(["ranked", "fallback"]);
      expect(await unexplainedDifferences(plain, f, rescore(late))).toEqual([]);
    });

    it("still fails when one of them has no listed minute there", async () => {
      const f = fixtureWith(late, flipped, { [A]: [569] });

      expect(await unexplainedDifferences(answerWith(late, tiles), f, rescore(late))).toContain(
        'status: "ranked", the reference has "fallback"',
      );
    });
  });

  it("at a low-sun-band minute is excused for every Candidate, and only there", async () => {
    const flipped = { lowSun: { 390: false } };
    const plain = answerWith(query, tiles);

    expect(await unexplainedDifferences(plain, fixtureWith(query, flipped, {}, [390]), rescore(query))).toEqual([]);
    expect(await unexplainedDifferences(plain, fixtureWith(query, flipped, {}, [391]), rescore(query))).toEqual([
      'spots[0].lowSunIntervals[0].start: "2026-03-20T06:30:00+00:00", the reference has "2026-03-20T06:31:00+00:00"',
      "spots[0].lowSunMinutes: 120.5, the reference has 119.5",
      'spots[1].lowSunIntervals[0].start: "2026-03-20T06:30:00+00:00", the reference has "2026-03-20T06:31:00+00:00"',
      "spots[1].lowSunMinutes: 120.5, the reference has 119.5",
    ]);
  });

  describe("the reference's side of a listed minute", () => {
    // C is 100 m from A: de-duped, so in no list.
    const withC = [
      world([
        { offsetCm: 449, northM: 0 },
        { offsetCm: 2_000, northM: 300 },
        { offsetCm: 600, northM: 100 },
      ]),
    ];
    const C = "ST5873/2";

    it("is read from the reference's Answer for a Candidate it lists", () => {
      const f = fixtureWith(query, { sunInView: { [A]: { 390: false } } }, { [A]: [390, 400] }, [390]);

      expect(referenceSight(f)).toEqual({ sunInView: { [A]: { 390: false, 400: true } }, lowSun: { 390: true } });
    });

    it("is out of view, inside the window, for a Candidate the Answer does not show", () => {
      // Minute 300 is before the window: it bears on nothing a Morning Answer shows.
      const f = fixtureWith(query, {}, { [C]: [300, 400] }, [], withC);

      expect(f.answer.spots.map((s) => s.candidateId)).not.toContain(C);
      expect(referenceSight(f).sunInView).toEqual({ [C]: { 400: false } });
    });
  });
});
