// Rules the committed synthetic fixtures cannot reach, through the scorer's
// own seam, `answer`, on a world small enough to work out by hand. The world
// there is 320 m long, so no fixture lists more than two spots or meets a
// saturated tie (docs/fixtures.md).

import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";

import type { Query } from "../contract";
import { PROFILE_SAMPLES, type Tile } from "../tile/decode";
import { answer } from "./answer";

// Node O, where the Query stands, and node P 100 m east of it.
const O = { id: 1, latE7: 514_589_000, lonE7: -26_052_000 };
const P = { id: 2, latE7: 514_589_000, lonE7: -26_037_560 };
// Storage code 0 is a Horizon profile at -2 degrees: open sky all round, so
// every Candidate sees the sun for the same minutes and they all tie.
const OPEN = 0;

/** A tile whose Candidates all hang off node O, `offsetCm` from it, 300 m apart north-south. */
function tile(gridRef: string, offsetsCm: number[]): Tile {
  const count = offsetsCm.length;
  const latE7 = Int32Array.from(offsetsCm, (_, k) => O.latE7 + (gridRef === "ST5773" ? -1 : 1) * (k + 1) * 27_000);
  return {
    gridRef,
    names: offsetsCm.map((_, k) => `${gridRef} spot ${k}`),
    candidates: {
      latE7,
      lonE7: new Int32Array(count).fill(O.lonE7),
      nodeIndex: new Uint32Array(count),
      offsetCm: Uint32Array.from(offsetsCm),
      nameIndex: Uint32Array.from(offsetsCm, (_, k) => k),
      profileCodes: new Uint8Array(count * PROFILE_SAMPLES).fill(OPEN),
    },
    walkGraph: {
      nodeId: Float64Array.of(O.id, P.id),
      nodeLatE7: Int32Array.of(O.latE7, P.latE7),
      nodeLonE7: Int32Array.of(O.lonE7, P.lonE7),
      edgeFrom: Uint32Array.of(0),
      edgeTo: Uint32Array.of(1),
      edgeLengthCm: Uint32Array.of(10_000),
    },
  };
}

const query: Query = {
  window: "morning",
  date: "2026-03-20",
  wakeTime: "06:30",
  origin: { lat: O.latE7 / 1e7, lon: O.lonE7 / 1e7 },
  maxWalkMin: 15,
  sky: "clear",
};

describe("ranking on a saturated tie", () => {
  // Far Candidates are 2,000 cm off the node: 20 m. The rest are 449 cm and
  // 550 cm off, which round half up to 4 m and 6 m, and 450 cm, which is 5 m.
  const west = tile("ST5773", [2_000, 2_000, 450, 2_000, 2_000, 2_000, 2_000, 2_000, 2_000, 450, 450]);
  const east = tile("ST5873", [449, 450, 550, 450, 2_000, 2_000, 2_000, 2_000, 2_000, 2_000, 450]);

  it("orders equal Low-sun minutes by whole walk metres, then by candidateId with the index as a number", () => {
    const result = answer(query, [east, west]);

    expect(result.status).toBe("ranked");
    // Worked by hand, and what `ciao_sun.reference.scorer.answer` gives for the same tiles.
    // The sun is up and low all window: 60 min at full weight from 06:30, then
    // 120 min tapering to 0 at 09:30, (120 + 119 + ... + 1) / 120 = 60.5.
    expect(result.spots.map((spot) => spot.lowSunMinutes)).toEqual([120.5, 120.5, 120.5, 120.5, 120.5]);
    expect(result.spots.map((spot) => [spot.candidateId, spot.walkMetres])).toEqual([
      ["ST5873/0", 4],
      ["ST5773/2", 5],
      ["ST5773/9", 5],
      ["ST5773/10", 5],
      ["ST5873/1", 5],
    ]);
  });

  it("does not depend on the order the tiles are given in", () => {
    expect(answer(query, [west, east])).toEqual(answer(query, [east, west]));
  });
});

describe("the scorer", () => {
  it("imports nothing outside src/ and touches no DOM or network", () => {
    const directories = ["scorer", "router"].map((name) => new URL(`../${name}/`, import.meta.url));
    for (const directory of directories) {
      for (const file of readdirSync(directory).filter((f) => f.endsWith(".ts") && !f.endsWith(".test.ts"))) {
        const source = readFileSync(new URL(file, directory), "utf8");
        const imports = [...source.matchAll(/from\s+"([^"]+)"/g)].map((match) => match[1]!);
        expect(imports.filter((path) => !path.startsWith(".")), file).toEqual([]);
        expect(source, file).not.toMatch(/\b(document|navigator|XMLHttpRequest|localStorage|caches)\b/);
        expect(source, file).not.toMatch(/\b(fetch|WebSocket|EventSource)\s*\(|\bwindow\./);
      }
    }
  });
});
