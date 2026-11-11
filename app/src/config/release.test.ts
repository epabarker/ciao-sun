import { describe, expect, it } from "vitest";

import { RELEASE, parseReleaseConfig } from "./release";

describe("release config", () => {
  it("pins the committed synthetic build until the first Bristol build is published (#55)", () => {
    expect(RELEASE).toEqual({ dataBase: "synthetic-data/", format: 1, build: "20261111a" });
  });

  it("refuses a pin without a data base, format or build id", () => {
    expect(() => parseReleaseConfig({ format: 1, build: "20261111a" })).toThrow(/dataBase/);
    expect(() => parseReleaseConfig({ dataBase: "x/", format: "1", build: "20261111a" })).toThrow(/format/);
    expect(() => parseReleaseConfig({ dataBase: "x/", format: 1, build: "2026-11-11.1" })).toThrow(/build/);
  });
});
