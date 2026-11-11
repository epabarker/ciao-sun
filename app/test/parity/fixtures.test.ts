// The golden-fixture harness (docs/fixtures.md): every fixture of one build,
// checked against the JS. Tile decoding, the sun track and the sun's three
// events are checked now; Answer parity turns on when `./scorer` exports the
// JS scorer.

import { afterAll, describe, expect, it } from "vitest";

import { sunTrack } from "../../src/solar/sun-track";
import { PROFILE_SAMPLES } from "../../src/tile/decode";
import { FixtureSet, pinFromEnvironment } from "./fixture-set";
import {
  SOLAR_TOLERANCE_DEG,
  answerDifferences,
  compareSunTrack,
  nearBoundaryFreedom,
  sunEvents,
} from "./parity";
import { scorer } from "./scorer";

const set = new FixtureSet(pinFromEnvironment());
const worst = { azimuth: 0, apparentElevation: 0, lowest: Infinity, minutes: 0, events: 0 };

describe(`golden fixtures of build f${set.pin.format}/${set.pin.build}`, () => {
  it("has fixtures to check", () => {
    expect(set.entries.length).toBeGreaterThan(0);
    expect(new Set(set.entries.map((entry) => entry.id)).size).toBe(set.entries.length);
  });

  describe.each(set.entries.map((entry) => [entry.id, entry] as const))("%s", (_id, entry) => {
    const loaded = set.load(entry);
    const track = loaded.then(({ query }) =>
      sunTrack(query.origin.lat, query.origin.lon, query.date),
    );

    it("names tiles that decode, and its index line agrees with it", async () => {
      const fixture = await loaded;

      expect(fixture.tiles).toEqual(entry.tiles);
      expect(fixture.answer.status).toBe(entry.status);
      expect(fixture.decodedTiles.map((tile) => tile.gridRef)).toEqual(fixture.tiles);
      for (const tile of fixture.decodedTiles) {
        expect(tile.candidates.profileCodes).toHaveLength(
          tile.candidates.latE7.length * PROFILE_SAMPLES,
        );
      }
    });

    it("lists only spots that are Candidates of its tiles, under their Spot names", async () => {
      const fixture = await loaded;
      const tiles = new Map(fixture.decodedTiles.map((tile) => [tile.gridRef, tile]));
      const spots = [...fixture.answer.spots];
      if (fixture.answer.nearestSunBeyondLimit) {
        spots.push(fixture.answer.nearestSunBeyondLimit);
      }

      for (const spot of spots) {
        const [gridRef, index] = spot.candidateId.split("/");
        const tile = tiles.get(gridRef!)!;
        const k = Number(index);
        expect(tile, spot.candidateId).toBeDefined();
        expect(tile.names[tile.candidates.nameIndex[k]!]).toBe(spot.name);
        expect(tile.candidates.latE7[k]! / 1e7).toBeCloseTo(spot.lat, 9);
        expect(tile.candidates.lonE7[k]! / 1e7).toBeCloseTo(spot.lon, 9);
      }
    });

    it("has a sun track within 0.01 degrees of the reference at every minute", async () => {
      const fixture = await loaded;

      const result = compareSunTrack(await track, fixture.sunTrack);

      expect(result.problems).toEqual([]);
      expect(result.worstAzimuthDeg).toBeLessThan(SOLAR_TOLERANCE_DEG);
      expect(result.worstApparentElevationDeg).toBeLessThan(SOLAR_TOLERANCE_DEG);
      // Every day has night in it: the comparison reaches well below 0 degrees.
      expect(result.lowestApparentElevationDeg).toBeLessThan(0);

      worst.azimuth = Math.max(worst.azimuth, result.worstAzimuthDeg);
      worst.apparentElevation = Math.max(worst.apparentElevation, result.worstApparentElevationDeg);
      worst.lowest = Math.min(worst.lowest, result.lowestApparentElevationDeg);
      worst.minutes += fixture.sunTrack.azimuth.length;
    });

    it("has Nominal sunrise, Nominal sunset and solar noon on the reference's minute", async () => {
      const { answer } = await loaded;
      const events = sunEvents(await track);

      // An Answer with no window (lamp-only, not-covered) does not carry them.
      for (const event of ["nominalSunrise", "nominalSunset", "solarNoon"] as const) {
        if (answer[event] !== undefined) {
          expect(events[event], event).toBe(answer[event]);
          worst.events += 1;
        }
      }
    });

    it.skipIf(!scorer)("has the reference's Answer", async () => {
      const fixture = await loaded;

      const answer = await scorer!(fixture.query, {
        tiles: fixture.decodedTiles,
        coverage: fixture.coverage,
      });

      const differences = answerDifferences(answer, fixture.answer);
      // TODO(#43, #44): where `nearBoundaryFreedom(fixture).any`, allow what
      // follows from a flip at a listed minute, and nothing else.
      expect(differences, JSON.stringify(nearBoundaryFreedom(fixture))).toEqual([]);
    });
  });

  afterAll(() => {
    expect(worst.events, "no fixture carried a sun event to check").toBeGreaterThan(0);
    console.info(
      `solar parity over ${worst.minutes} fixture minutes (down to ${worst.lowest.toFixed(1)} deg): ` +
        `worst azimuth ${worst.azimuth.toFixed(5)} deg, ` +
        `worst apparent elevation ${worst.apparentElevation.toFixed(5)} deg; ` +
        `${worst.events} sun events on the reference's minute`,
    );
  });
});
