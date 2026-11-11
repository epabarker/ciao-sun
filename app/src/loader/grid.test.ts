import { describe, expect, it } from "vitest";

import { gridRefOrigin, gridRefsInReach, wgs84ToNationalGrid } from "./grid";

// pyproj's EPSG:4326 -> EPSG:27700, as the build and the reference project
// (`uv run python -c "from pyproj import Transformer; ..."`).
const PYPROJ: [lat: number, lon: number, easting: number, northing: number][] = [
  [51.4589122, -2.6051884, 358050.004, 173500.003],
  [51.472, -2.604, 358144.578, 174954.876],
  [51.5007, -0.1246, 530269.902, 179640.717],
  [54.5, -3.2, 322383.556, 512293.593],
  [50.1, -5.5, 149802.183, 28080.323],
];

describe("National Grid position", () => {
  it.each(PYPROJ)("of %f, %f is within 5 m of pyproj's", (lat, lon, easting, northing) => {
    const [e, n] = wgs84ToNationalGrid(lat, lon);
    expect(Math.hypot(e - easting, n - northing)).toBeLessThan(5);
  });
});

describe("grid ref origin", () => {
  it("is the square's south-west corner (docs/tile-format-f1.md: ST5873 is 358000 E, 173000 N)", () => {
    expect(gridRefOrigin("ST5873")).toEqual([358000, 173000]);
  });

  it("finds the letters arithmetically: TQ3079 is central London", () => {
    expect(gridRefOrigin("TQ3079")).toEqual([530000, 179000]);
  });

  it("refuses a malformed grid ref", () => {
    expect(() => gridRefOrigin("ST58")).toThrow(/grid ref/);
    expect(() => gridRefOrigin("IA5873")).toThrow(/grid ref/);
  });
});

describe("tiles in reach", () => {
  const index = ["ST5773", "ST5873", "ST5973", "ST5875", "ST6073"];

  it("are the indexed squares within the reach of the origin, sorted", () => {
    // 358050 E, 173500 N: 50 m into ST5873, 950 m from ST5973's west edge,
    // 1,500 m below ST5875 and 1,950 m from ST6073.
    expect(gridRefsInReach(index, 51.4589122, -2.6051884, 1600)).toEqual(["ST5773", "ST5873", "ST5875", "ST5973"]);
    expect(gridRefsInReach(index, 51.4589122, -2.6051884, 900)).toEqual(["ST5773", "ST5873"]);
  });
});
