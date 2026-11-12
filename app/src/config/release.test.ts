import { describe, expect, it } from "vitest";

import { RELEASE, parseReleaseConfig } from "./release";

describe("release config", () => {
  it("pins the first published Bristol build, on the data subdomain (#55)", () => {
    expect(RELEASE).toEqual({ dataBase: "https://ciao-sun-data.edbarker.dev/", format: 1, build: "20261111b" });
  });

  it("refuses a pin without a data base, format or build id", () => {
    expect(() => parseReleaseConfig({ format: 1, build: "20261111a" })).toThrow(/dataBase/);
    expect(() => parseReleaseConfig({ dataBase: "x/", format: "1", build: "20261111a" })).toThrow(/format/);
    expect(() => parseReleaseConfig({ dataBase: "x/", format: 1, build: "2026-11-11.1" })).toThrow(/build/);
  });
});
