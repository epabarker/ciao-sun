import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";

import {
  OUTSIDE_SECTOR,
  PROFILE_SAMPLES,
  TileFormatError,
  UnsupportedFormatError,
  codeToDegrees,
  decodeTile,
  horizonProfileDegrees,
  spotName,
} from "./decode";

const SYNTHETIC = new URL("../../../fixtures/synthetic/", import.meta.url);

function hex(text: string): number[] {
  return text.split(/\s+/).map((byte) => Number.parseInt(byte, 16));
}

/** The 1,550-byte payload of the worked example in docs/tile-format-f1.md, row by row. */
function workedExamplePayload(): Uint8Array {
  return Uint8Array.from([
    ...hex("43 53 55 4E"), // magic
    ...hex("01 00"), // format 1
    ...hex("53 54 35 38 37 33"), // ST5873
    ...hex("01 00 00 00"), // C = 1
    ...hex("02 00 00 00"), // N = 2
    ...hex("01 00 00 00"), // E = 1
    ...hex("01 00 00 00"), // S = 1
    ...hex("00 00"), // sector first sample F = 0
    ...hex("A0 05"), // sector samples P = 1440
    ...hex("C8 45 AB 1E"), // Candidate latitude
    ...hex("10 34 72 FE"), // Candidate longitude
    ...hex("01 00 00 00"), // Candidate walk node
    ...hex("DA 02 00 00"), // Candidate offset
    ...hex("00 00 00 00"), // Candidate Spot name
    ...hex("65 00 00 00 00 00 00 00"), // node 0 id
    ...hex("07 00 00 00 00 01 00 00"), // node 1 id
    ...hex("E0 41 AB 1E"), // node 0 latitude
    ...hex("68 55 AB 1E"), // node 1 latitude
    ...hex("28 30 72 FE"), // node 0 longitude
    ...hex("B0 43 72 FE"), // node 1 longitude
    ...hex("00 00 00 00"), // edge 0 from
    ...hex("01 00 00 00"), // edge 0 to
    ...hex("8F 19 00 00"), // edge 0 length
    0x14,
    ...new Array<number>(359).fill(0), // samples 0-359
    ...hex("05 69 97 FB"), // samples 360-363
    ...new Array<number>(1076).fill(0), // samples 364-1439
    ...hex("0C 00"), // Spot name length
    ...hex("42 72 61 6E 64 6F 6E 20 48 69 6C 6C"), // Brandon Hill
  ]);
}

function gzip(payload: Uint8Array): Uint8Array {
  return new Uint8Array(gzipSync(payload));
}

/** The worked example with `change` applied to its payload before it is compressed. */
function tileWith(
  change: (payload: Uint8Array, view: DataView) => Uint8Array | void,
): Uint8Array {
  const payload = workedExamplePayload();
  const changed = change(payload, new DataView(payload.buffer));
  return gzip(changed ?? payload);
}

function sha256(bytes: ArrayBufferView): string {
  return createHash("sha256")
    .update(new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength))
    .digest("hex");
}

describe("the worked example of docs/tile-format-f1.md", () => {
  it("is 1,550 bytes of payload", () => {
    expect(workedExamplePayload()).toHaveLength(1550);
  });

  it("decodes to its Candidate, Spot name and walk graph", async () => {
    const tile = await decodeTile(gzip(workedExamplePayload()));

    expect(tile.gridRef).toBe("ST5873");
    expect(tile.names).toEqual(["Brandon Hill"]);
    expect(Array.from(tile.candidates.latE7)).toEqual([514541000]);
    expect(Array.from(tile.candidates.lonE7)).toEqual([-26070000]);
    expect(Array.from(tile.candidates.nodeIndex)).toEqual([1]);
    expect(Array.from(tile.candidates.offsetCm)).toEqual([730]);
    expect(Array.from(tile.candidates.nameIndex)).toEqual([0]);
    expect(spotName(tile, 0)).toBe("Brandon Hill");
    expect(Array.from(tile.walkGraph.nodeId)).toEqual([101, 2 ** 40 + 7]);
    expect(Array.from(tile.walkGraph.nodeLatE7)).toEqual([
      514540000, 514545000,
    ]);
    expect(Array.from(tile.walkGraph.nodeLonE7)).toEqual([
      -26071000, -26066000,
    ]);
    expect(Array.from(tile.walkGraph.edgeFrom)).toEqual([0]);
    expect(Array.from(tile.walkGraph.edgeTo)).toEqual([1]);
    expect(Array.from(tile.walkGraph.edgeLengthCm)).toEqual([6543]);
  });

  it("undoes the azimuth delta and the storage code: 0.0 degrees all round, a ridge due east", async () => {
    const tile = await decodeTile(gzip(workedExamplePayload()));

    const codes = tile.candidates.profileCodes;
    expect(codes).toHaveLength(PROFILE_SAMPLES);
    expect(Array.from(codes.subarray(358, 365))).toEqual([
      20, 20, 25, 130, 25, 20, 20,
    ]);
    expect(new Set(codes)).toEqual(new Set([20, 25, 130]));

    const degrees = horizonProfileDegrees(tile, 0);
    expect(degrees).toHaveLength(PROFILE_SAMPLES);
    expect(degrees[0]).toBe(0);
    expect(degrees[360]).toBe(0.5);
    expect(degrees[361]).toBe(15);
    expect(degrees[362]).toBe(0.5);
    expect(degrees[1439]).toBe(0);
  });
});

describe("the storage code", () => {
  it.each([
    [0, -2.0],
    [20, 0.0],
    [120, 10.0],
    [121, 10.5],
    [227, 63.5],
  ])("code %i is %f degrees", (code, degrees) => {
    expect(codeToDegrees(code)).toBeCloseTo(degrees, 12);
  });

  it("has no code above 227", () => {
    expect(() => codeToDegrees(228)).toThrow(TileFormatError);
  });
});

describe("the committed synthetic tiles decode to what the Python reader gives", () => {
  const expected = JSON.parse(
    readFileSync(new URL("decoded-tiles.json", SYNTHETIC), "utf8"),
  ) as Record<string, Record<string, PythonTile>>;

  interface PythonTile {
    sector: { firstSample: number; samples: number };
    names: string[];
    candidates: {
      latE7: number[];
      lonE7: number[];
      nodeIndex: number[];
      offsetCm: number[];
      nameIndex: number[];
      spotNames: string[];
      profileCodesSha256: string;
      profileDegreesSha256: string;
      firstProfileCodes: number[];
    };
    walkGraph: Record<
      | "nodeId"
      | "nodeLatE7"
      | "nodeLonE7"
      | "edgeFrom"
      | "edgeTo"
      | "edgeLengthCm",
      number[]
    >;
  }

  it("covers both tiles of the build in both windows", () => {
    expect(Object.keys(expected).sort()).toEqual(["evening", "morning"]);
    for (const window of ["morning", "evening"]) {
      expect(Object.keys(expected[window]!).sort()).toEqual([
        "ST5773",
        "ST5873",
      ]);
    }
  });

  it.each([
    ["morning", "ST5773"],
    ["morning", "ST5873"],
    ["evening", "ST5773"],
    ["evening", "ST5873"],
  ])("%s %s", async (window, gridRef) => {
    const python = expected[window]![gridRef]!;
    const bytes = readFileSync(
      new URL(`f1/20261111a/tiles/${window}/${gridRef}.bin`, SYNTHETIC),
    );

    const tile = await decodeTile(new Uint8Array(bytes), gridRef);

    expect(tile.gridRef).toBe(gridRef);
    expect(tile.sector).toEqual(python.sector);
    expect(tile.names).toEqual(python.names);
    const c = tile.candidates;
    expect(Array.from(c.latE7)).toEqual(python.candidates.latE7);
    expect(Array.from(c.lonE7)).toEqual(python.candidates.lonE7);
    expect(Array.from(c.nodeIndex)).toEqual(python.candidates.nodeIndex);
    expect(Array.from(c.offsetCm)).toEqual(python.candidates.offsetCm);
    expect(Array.from(c.nameIndex)).toEqual(python.candidates.nameIndex);
    expect(
      python.candidates.spotNames.map((_, k) => spotName(tile, k)),
    ).toEqual(python.candidates.spotNames);
    expect(c.latE7.length).toBeGreaterThan(40);

    expect(Array.from(c.profileCodes.subarray(0, PROFILE_SAMPLES))).toEqual(
      python.candidates.firstProfileCodes,
    );
    expect(sha256(c.profileCodes)).toBe(python.candidates.profileCodesSha256);
    // The sector's angles, Candidate by Candidate, in sector order.
    const { firstSample, samples } = tile.sector;
    const degrees = new Float64Array(c.latE7.length * samples);
    for (let k = 0; k < c.latE7.length; k++) {
      for (let j = 0; j < samples; j++) {
        degrees[k * samples + j] = codeToDegrees(
          c.profileCodes[
            k * PROFILE_SAMPLES + ((firstSample + j) % PROFILE_SAMPLES)
          ]!,
        );
      }
    }
    expect(sha256(degrees)).toBe(python.candidates.profileDegreesSha256);

    const g = tile.walkGraph;
    expect(Array.from(g.nodeId)).toEqual(python.walkGraph.nodeId);
    expect(Array.from(g.nodeLatE7)).toEqual(python.walkGraph.nodeLatE7);
    expect(Array.from(g.nodeLonE7)).toEqual(python.walkGraph.nodeLonE7);
    expect(Array.from(g.edgeFrom)).toEqual(python.walkGraph.edgeFrom);
    expect(Array.from(g.edgeTo)).toEqual(python.walkGraph.edgeTo);
    expect(Array.from(g.edgeLengthCm)).toEqual(python.walkGraph.edgeLengthCm);
  });
});

describe("a tile holds only its window's sector of each Horizon profile", () => {
  /** The worked example cut to `samples` samples from `first`: the ridge is at 360-362. */
  function inSector(first: number, samples: number): Uint8Array {
    const whole = workedExamplePayload();
    const profileAt = 96;
    const codes = new Array<number>(PROFILE_SAMPLES).fill(20);
    codes[360] = 25;
    codes[361] = 130;
    codes[362] = 25;
    const kept = Array.from(
      { length: samples },
      (_, j) => codes[(first + j) % PROFILE_SAMPLES]!,
    );
    const deltas = kept.map((code, j) =>
      j === 0 ? code : (code - kept[j - 1]! + 256) & 0xff,
    );
    const payload = Uint8Array.from([
      ...whole.subarray(0, 28),
      first & 0xff,
      first >> 8,
      samples & 0xff,
      samples >> 8,
      ...whole.subarray(32, profileAt),
      ...deltas,
      ...whole.subarray(profileAt + PROFILE_SAMPLES),
    ]);
    return gzip(payload);
  }

  it("decodes the sector's samples in place and marks the rest of the circle outside it", async () => {
    const tile = await decodeTile(inSector(140, 625)); // 35 to 191 degrees, a Bristol morning
    const codes = tile.candidates.profileCodes;

    expect(tile.sector).toEqual({ firstSample: 140, samples: 625 });
    expect(Array.from(codes.subarray(359, 364))).toEqual([20, 25, 130, 25, 20]);
    expect(codes[139]).toBe(OUTSIDE_SECTOR);
    expect(codes[765]).toBe(OUTSIDE_SECTOR);
    expect(codes[764]).toBe(20);
  });

  it("reads a sector that runs on past north", async () => {
    const codes = (await decodeTile(inSector(1400, 100))).candidates
      .profileCodes;

    expect(codes[1400]).toBe(20);
    expect(codes[59]).toBe(20);
    expect(codes[60]).toBe(OUTSIDE_SECTOR);
    expect(codes[1399]).toBe(OUTSIDE_SECTOR);
  });

  it("refuses to give an angle for a sample outside the sector", async () => {
    const tile = await decodeTile(inSector(140, 625));

    expect(() => horizonProfileDegrees(tile, 0)).toThrow(TileFormatError);
  });

  it.each([
    [1440, 10],
    [0, 0],
    [0, 1441],
  ])(
    "refuses a sector of %i + %i samples, which is not within the circle",
    async (first, samples) => {
      const bytes = tileWith((_, view) => {
        view.setUint16(28, first, true);
        view.setUint16(30, samples, true);
      });
      await expect(decodeTile(bytes)).rejects.toThrow(/sector/);
    },
  );
});

describe("a reader refuses the file rather than return a partial tile", () => {
  it("when it is not gzip", async () => {
    await expect(decodeTile(workedExamplePayload())).rejects.toThrow(
      TileFormatError,
    );
  });

  it("when the gzip stream is cut short", async () => {
    const whole = gzip(workedExamplePayload());
    await expect(
      decodeTile(whole.subarray(0, whole.length - 12)),
    ).rejects.toThrow(TileFormatError);
  });

  it("when the magic is wrong", async () => {
    const bytes = tileWith((payload) => void (payload[0] = 0x58));
    await expect(decodeTile(bytes)).rejects.toThrow(/magic/);
  });

  it("when the format number is one it does not know, and says so separately", async () => {
    const bytes = tileWith((_, view) => view.setUint16(4, 2, true));
    const refusal = await decodeTile(bytes).catch((error: unknown) => error);

    expect(refusal).toBeInstanceOf(UnsupportedFormatError);
    expect(refusal).toBeInstanceOf(TileFormatError);
    expect((refusal as UnsupportedFormatError).format).toBe(2);
  });

  it("checks the format number before any other byte after the magic", async () => {
    // An f2 file may be laid out quite differently: nothing after the format number is trusted.
    const header = workedExamplePayload().slice(0, 6);
    new DataView(header.buffer).setUint16(4, 2, true);
    await expect(decodeTile(gzip(header))).rejects.toThrow(
      UnsupportedFormatError,
    );
  });

  it("when the payload ends before its last field", async () => {
    const bytes = tileWith((payload) => payload.slice(0, payload.length - 1));
    await expect(decodeTile(bytes)).rejects.toThrow(/truncated/);
  });

  it("when the payload has bytes after its last field", async () => {
    const bytes = tileWith((payload) => Uint8Array.from([...payload, 0]));
    await expect(decodeTile(bytes)).rejects.toThrow(/after its last field/);
  });

  it("when the grid reference is not two letters and four digits", async () => {
    const bytes = tileWith((payload) => void (payload[6] = "I".charCodeAt(0)));
    await expect(decodeTile(bytes)).rejects.toThrow(/grid ref/);
  });

  it("when the grid reference differs from the file name", async () => {
    await expect(
      decodeTile(gzip(workedExamplePayload()), "ST5773"),
    ).rejects.toThrow(/ST5773/);
  });

  it("when a Candidate's walk node index is out of range", async () => {
    const bytes = tileWith((_, view) => view.setUint32(40, 2, true));
    await expect(decodeTile(bytes)).rejects.toThrow(/walk node index/);
  });

  it("when a Candidate's Spot name index is out of range", async () => {
    const bytes = tileWith((_, view) => view.setUint32(48, 1, true));
    await expect(decodeTile(bytes)).rejects.toThrow(/Spot name index/);
  });

  it("when an edge's node index is out of range", async () => {
    const bytes = tileWith((_, view) => view.setUint32(88, 2, true));
    await expect(decodeTile(bytes)).rejects.toThrow(/edge/);
  });

  it("when a node id is 2^53 or more", async () => {
    const bytes = tileWith((_, view) => view.setBigUint64(52, 2n ** 53n, true));
    await expect(decodeTile(bytes)).rejects.toThrow(/2\^53/);
  });

  it("when two nodes share an id", async () => {
    const bytes = tileWith((_, view) => view.setBigUint64(60, 101n, true));
    await expect(decodeTile(bytes)).rejects.toThrow(/unique/);
  });

  it("when a decoded storage code is above 227", async () => {
    // Sample 0 becomes code 228; the next delta brings the row back down.
    const bytes = tileWith((payload) => {
      payload[96] = 228;
      payload[97] = 256 - 208;
    });
    await expect(decodeTile(bytes)).rejects.toThrow(/storage code/);
  });

  it("when a Spot name is not valid UTF-8", async () => {
    const bytes = tileWith((payload) => void (payload[1538] = 0xff));
    await expect(decodeTile(bytes)).rejects.toThrow(/UTF-8/);
  });
});
