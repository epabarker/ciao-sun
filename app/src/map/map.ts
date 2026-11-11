// The map, as the answer screen sees it: a surface that shows the origin and
// the numbered spots, highlights one, and reports a tap on a marker. MapLibre
// implements it in `maplibre.ts`, which `main.ts` loads on demand; tests use a
// fake, because MapLibre needs WebGL.
//
// What goes on the map is read from the build's manifest: the basemap's tiles,
// bounds and zooms (`basemapOf`), and the credits for the map's corner ⓘ
// (`mapCredits`). Nothing here is hardcoded but which sources the corner
// credits (spec #27, "Attribution placement"); the About sheet credits the rest.

import type { Manifest } from "../loader/loader";

export interface MapPoint {
  lat: number;
  lon: number;
}

/** A numbered marker: `rank` is its place in the list, `id` its candidateId. */
export interface MapSpot extends MapPoint {
  id: string;
  rank: number;
  name: string;
}

export interface MapMarkers {
  origin?: MapPoint;
  spots: MapSpot[];
}

/** WGS84 west, south, east, north. */
export type Bounds = [number, number, number, number];

/** The build's `z/x/y` basemap, from the manifest's `basemap` section. */
export interface Basemap {
  /** `<build>/basemap/{z}/{x}/{y}.mvt`, absolute. */
  tiles: string;
  /** No tile lies wholly outside these. */
  bounds: Bounds;
  minZoom: number;
  maxZoom: number;
}

/** One line of the corner credit, as the manifest's attribution has it. */
export interface Credit {
  text: string;
  url?: string;
}

export interface MapOptions {
  /** Undefined when the manifest has no basemap: the markers are drawn on a plain ground. */
  basemap?: Basemap;
  credits: Credit[];
  /** A tap on a spot's marker. */
  onSelect(id: string): void;
  /** How much of the map the header and the bottom sheet cover, in px, now. */
  insets(): { top: number; bottom: number };
}

export interface MapSurface {
  /** Replace the markers and frame them. */
  show(markers: MapMarkers): void;
  /** Highlight one spot's marker and bring it into view; undefined clears it. */
  highlight(id: string | undefined): void;
}

/** Makes the map in `container`. It rejects (or throws) where no map can be drawn, e.g. without WebGL. */
export type MapFactory = (container: HTMLElement, options: MapOptions) => MapSurface | Promise<MapSurface>;
