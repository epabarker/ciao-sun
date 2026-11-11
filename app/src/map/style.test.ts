// The basemap style: a Protomaps v4 style over the build's own z/x/y tiles,
// with nothing fetched from anywhere else.

import { describe, expect, it } from "vitest";

import type { Basemap } from "./map";
import { basemapStyle } from "./style";

// The committed synthetic build's manifest `basemap` section.
const BASEMAP: Basemap = {
  tiles: "https://data.example/f1/20261111a/basemap/{z}/{x}/{y}.mvt",
  bounds: [-2.6087265511658946, 51.457994802289726, -2.603089691584964, 51.45982202430133],
  minZoom: 10,
  maxZoom: 15,
};

describe("basemap style", () => {
  it("reads one vector source: the build's tiles, only inside its bounds and zooms", () => {
    const style = basemapStyle(BASEMAP);
    expect(style.version).toBe(8);
    expect(Object.values(style.sources)).toEqual([
      { type: "vector", tiles: [BASEMAP.tiles], bounds: BASEMAP.bounds, minzoom: 10, maxzoom: 15 },
    ]);
  });

  it("draws the Protomaps v4 layers: earth, water, roads and buildings", () => {
    const layers = basemapStyle(BASEMAP).layers;
    const sourceLayers = new Set(layers.map((layer) => ("source-layer" in layer ? layer["source-layer"] : undefined)));
    for (const name of ["earth", "water", "roads", "buildings", "landuse"]) expect(sourceLayers).toContain(name);
  });

  it("has no text labels or icons, so it needs no glyphs or sprite from a CDN", () => {
    const style = basemapStyle(BASEMAP);
    expect(style.glyphs).toBeUndefined();
    expect(style.sprite).toBeUndefined();
    expect(style.layers.filter((layer) => layer.type === "symbol")).toEqual([]);
    const urls = JSON.stringify(style).match(/[a-z]+:\/\/[^"]+/g);
    expect(urls).toEqual([BASEMAP.tiles]);
  });

  it("is a plain ground when the build has no basemap", () => {
    const style = basemapStyle(undefined);
    expect(style.sources).toEqual({});
    expect(style.layers.map((layer) => layer.type)).toEqual(["background"]);
  });
});
