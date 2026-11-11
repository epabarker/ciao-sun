// The basemap's MapLibre style: Protomaps' v4 "light" flavour over the build's
// own `z/x/y` tiles (the manifest's `basemap.tilesetVersion` is a v4 schema;
// @protomaps/basemaps 5.x writes v4 styles).
//
// `layers()` is called without a `lang`, which leaves out every label and POI
// layer: the style has no text and no icons, so it needs no glyphs and no
// sprite, and the map fetches nothing but the build's tiles. Spots are named in
// the list; the markers are HTML.

import { layers, namedFlavor } from "@protomaps/basemaps";
import type { StyleSpecification } from "maplibre-gl";

import type { Basemap } from "./map";

const SOURCE = "basemap";
const FLAVOR = namedFlavor("light");

export function basemapStyle(basemap: Basemap | undefined): StyleSpecification {
  if (!basemap) {
    return {
      version: 8,
      sources: {},
      layers: [{ id: "background", type: "background", paint: { "background-color": FLAVOR.background } }],
    };
  }
  return {
    version: 8,
    sources: {
      [SOURCE]: {
        type: "vector",
        tiles: [basemap.tiles],
        // No tile is requested outside the bounds, nor below or above the zooms
        // that have tiles: MapLibre overzooms beyond maxzoom.
        bounds: basemap.bounds,
        minzoom: basemap.minZoom,
        maxzoom: basemap.maxZoom,
      },
    },
    layers: layers(SOURCE, FLAVOR),
  };
}
