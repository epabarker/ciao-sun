// Basemap tiles are fetched by the page, not by MapLibre's worker, so the
// service worker sees them in every browser and they work offline (#52).

import { describe, expect, it } from "vitest";

import { pageTileLoader, throughPage } from "./page-fetch";

const TEMPLATE = "https://data.example/f1/20261111a/basemap/{z}/{x}/{y}.mvt";

function host(status = 200) {
  const requested: { url: string; signal: AbortSignal | undefined }[] = [];
  const fetch = async (url: string, init?: RequestInit) => {
    requested.push({ url, signal: init?.signal ?? undefined });
    return new Response(status === 200 ? new Uint8Array([0x1a, 0x02, 0x08, 0x01]) : "", { status });
  };
  return { fetch, requested };
}

describe("basemap tiles through the page", () => {
  it("asks the page for the build's own z/x/y tile and hands MapLibre its bytes", async () => {
    const h = host();
    const abort = new AbortController();
    // MapLibre fills the template, then asks for the URL by its scheme.
    const url = throughPage(TEMPLATE).replace("{z}", "10").replace("{x}", "504").replace("{y}", "340");
    const { data } = await pageTileLoader(h.fetch)({ url, type: "arrayBuffer" }, abort);
    expect(h.requested.map((r) => r.url)).toEqual(["https://data.example/f1/20261111a/basemap/10/504/340.mvt"]);
    expect(h.requested[0]?.signal).toBe(abort.signal);
    expect([...new Uint8Array(data)]).toEqual([0x1a, 0x02, 0x08, 0x01]);
  });

  it("fails a tile the host doesn't have, so the map shows its plain ground there", async () => {
    const h = host(404);
    const url = throughPage(TEMPLATE).replace("{z}/{x}/{y}", "15/1/1");
    await expect(pageTileLoader(h.fetch)({ url, type: "arrayBuffer" }, new AbortController())).rejects.toThrow(/404/);
  });

  it("names a scheme of its own, not http, so MapLibre's worker passes the request to the page", () => {
    expect(throughPage(TEMPLATE)).toMatch(/^[a-z-]+:\/\//);
    expect(throughPage(TEMPLATE)).not.toMatch(/^https?:/);
  });
});
