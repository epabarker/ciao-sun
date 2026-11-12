import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { Answer, Query } from "../contract";
import { answer } from "../scorer/answer";
import { UnsupportedFormatError } from "../tile/decode";
import { type FetchLike, openBuild } from "./loader";

// The committed synthetic build, served as a data host would serve it: the
// directory `fixtures/synthetic` is the `dataBase` (docs/fixtures.md).
const SYNTHETIC = fileURLToPath(new URL("../../../fixtures/synthetic/", import.meta.url));
const DATA_BASE = "https://data.example/";
const PIN = { dataBase: DATA_BASE, format: 1, build: "20261111a" };

interface Served {
  fetch: FetchLike;
  requested: string[];
}

/** A data host over the synthetic build; `override` replaces a path's body. */
function host(override: Record<string, unknown> = {}): Served {
  const requested: string[] = [];
  const fetch: FetchLike = async (url) => {
    requested.push(url);
    const path = url.startsWith(DATA_BASE) ? url.slice(DATA_BASE.length) : url;
    if (path in override) {
      return new Response(JSON.stringify(override[path]), { status: 200 });
    }
    try {
      return new Response(readFileSync(SYNTHETIC + path), { status: 200 });
    } catch {
      return new Response("not found", { status: 404 });
    }
  };
  return { fetch, requested };
}

function fixture(id: string): { query: Query; tiles: string[]; answer: Answer } {
  return JSON.parse(readFileSync(`${SYNTHETIC}f1/20261111a/fixtures/${id}.json`, "utf8"));
}

const manifest = JSON.parse(readFileSync(`${SYNTHETIC}f1/20261111a/manifest.json`, "utf8"));
const tileRequests = (requested: string[]) => requested.filter((url) => url.includes("/tiles/"));

describe("data loader", () => {
  it("reads the manifest at <dataBase>/f<format>/<build>/manifest.json", async () => {
    const served = host();
    const build = await openBuild(PIN, { fetch: served.fetch });
    expect(build.manifest.build).toBe("20261111a");
    expect(served.requested).toEqual(["https://data.example/f1/20261111a/manifest.json"]);
  });

  it("resolves a relative dataBase against the page", async () => {
    const served = host();
    const pin = { ...PIN, dataBase: "data" };
    await openBuild(pin, { fetch: served.fetch, baseUrl: "https://data.example/ciao-sun/index.html" }).catch(() => {});
    expect(served.requested).toEqual(["https://data.example/ciao-sun/data/f1/20261111a/manifest.json"]);
  });

  it.each([
    "morning-winter-solstice",
    "morning-summer-solstice",
    "morning-september-equinox-now",
    "morning-march-equinox",
    "evening-summer-solstice",
  ])(
    "fetches the window's tiles the reference ranked %s over, and the scorer's Answer over them is the fixture's",
    async (id) => {
      const expected = fixture(id);
      const served = host();
      const build = await openBuild(PIN, { fetch: served.fetch });
      const area = await build.area(expected.query.origin, expected.query.window);
      expect(area.covered).toBe(true);
      if (!area.covered) return;
      expect(area.tiles.map((tile) => tile.gridRef)).toEqual(expected.tiles);
      expect(tileRequests(served.requested)).toEqual(
        expected.tiles.map(
          (gridRef) => `https://data.example/f1/20261111a/tiles/${expected.query.window}/${gridRef}.bin`,
        ),
      );
      const got = answer(expected.query, area.tiles);
      expect(got.spots.map((spot) => [spot.candidateId, spot.leaveBy, spot.targetMet])).toEqual(
        expected.answer.spots.map((spot) => [spot.candidateId, spot.leaveBy, spot.targetMet]),
      );
    },
  );

  it("fetches each tile once however many queries ask for it", async () => {
    const served = host();
    const build = await openBuild(PIN, { fetch: served.fetch });
    const { query } = fixture("morning-winter-solstice");
    await build.area(query.origin, "morning");
    await build.area(query.origin, "morning");
    expect(tileRequests(served.requested)).toHaveLength(2);
  });

  it("fetches a square's evening tile apart from its morning one, holding only the evening sector", async () => {
    const served = host();
    const build = await openBuild(PIN, { fetch: served.fetch });
    const { query } = fixture("morning-winter-solstice");
    const morning = await build.area(query.origin, "morning");
    const evening = await build.area(query.origin, "evening");
    expect(tileRequests(served.requested)).toHaveLength(4);
    if (!morning.covered || !evening.covered) throw new Error("covered");
    const sectors = manifest.sectors;
    expect(morning.tiles[0]!.sector).toEqual(sectors.morning);
    expect(evening.tiles[0]!.sector).toEqual(sectors.evening);
  });

  it("refuses a manifest in a format it can't read, and loads no tiles", async () => {
    const served = host({ "f1/20261111a/manifest.json": { ...manifest, format: 2 } });
    const opened = openBuild(PIN, { fetch: served.fetch });
    await expect(opened).rejects.toBeInstanceOf(UnsupportedFormatError);
    await expect(opened).rejects.toMatchObject({ format: 2 });
    expect(tileRequests(served.requested)).toEqual([]);
  });

  it("refuses a manifest with no format at all as one it can't read", async () => {
    const { format: _format, ...unformatted } = manifest;
    const served = host({ "f1/20261111a/manifest.json": unformatted });
    await expect(openBuild(PIN, { fetch: served.fetch })).rejects.toBeInstanceOf(UnsupportedFormatError);
  });

  it("refuses a manifest of another build than the pinned one", async () => {
    const served = host({ "f1/20261111a/manifest.json": { ...manifest, build: "20261112a" } });
    await expect(openBuild(PIN, { fetch: served.fetch })).rejects.toThrow(/20261112a/);
  });

  it("reports a data host that can't be reached", async () => {
    const served = host();
    await expect(openBuild({ ...PIN, build: "20990101a" }, { fetch: served.fetch })).rejects.toThrow(/404/);
  });

  it("finds an origin outside the coverage not covered, and loads no tiles", async () => {
    const { query } = fixture("morning-not-covered");
    const served = host();
    const build = await openBuild(PIN, { fetch: served.fetch });
    expect(await build.area(query.origin, "morning")).toEqual({ covered: false });
    expect(tileRequests(served.requested)).toEqual([]);
  });
});
