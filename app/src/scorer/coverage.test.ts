// The not-covered test, on rings small enough to work out by hand. Every
// expected value is also what `ciao_sun.coverage.Coverage.contains` gives.

import { describe, expect, it } from "vitest";

import { type CoverageGeometry, contains } from "./coverage";

// A 2 x 2 degree square with a hole in the middle, which is ignored.
const square: CoverageGeometry = {
  type: "Polygon",
  coordinates: [
    [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]],
    [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5], [0.5, 0.5]],
  ],
};

describe("the coverage polygon", () => {
  it("contains a position inside its outer ring, hole or not, and nothing outside", () => {
    expect(contains(square, 1, 1)).toBe(true);
    expect(contains(square, -1, 1)).toBe(false);
    expect(contains(square, 3, 1)).toBe(false);
  });

  it("counts the south and west edges in and the north and east edges out", () => {
    // [lat, lon] -> inside, as the even-odd inequality decides on an edge.
    const cases: [number, number, boolean][] = [
      [0, 1, true],
      [1, 0, true],
      [0, 0, true],
      [2, 1, false],
      [1, 2, false],
      [2, 2, false],
    ];
    for (const [lat, lon, inside] of cases) {
      expect(contains(square, lat, lon), `${lat}, ${lon}`).toBe(inside);
    }
  });

  it("contains a position inside any part of a MultiPolygon", () => {
    const parts: CoverageGeometry = {
      type: "MultiPolygon",
      coordinates: [
        [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        [[[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]]],
      ],
    };
    expect(contains(parts, 5.5, 5.5)).toBe(true);
    expect(contains(parts, 0.5, 0.5)).toBe(true);
    expect(contains(parts, 3, 3)).toBe(false);
  });
});
