// The map surface in the browser: MapLibre GL JS over the build's basemap.
// `main.ts` imports this module on demand, so the list's first paint doesn't
// wait for MapLibre, and the tests never load it (it needs WebGL).
//
// - The style is `basemapStyle`: the build's tiles and nothing else.
// - The camera stays near the basemap's bounds and at or above its lowest
//   zoom; the source's own bounds and zooms keep tiles that don't exist from
//   being requested. A basemap tile that fails to load or parse (the
//   synthetic build's are text placeholders) is logged once; the markers and
//   the list are unaffected.
// - Markers are HTML elements, so the numbers need no glyphs.
// - The corner ⓘ is MapLibre's compact attribution, carrying the manifest's
//   OpenStreetMap and Protomaps credits.

import { LngLatBounds, Map as MapLibreMap, Marker, setWorkerUrl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";

import type { Bounds, Credit, MapFactory, MapMarkers, MapOptions, MapSurface } from "./map";
import { basemapStyle } from "./style";

// MapLibre looks for its worker beside its own module, which bundling moves.
setWorkerUrl(workerUrl);

/** The closest a spot is framed, and the deepest the map goes (MapLibre overzooms the basemap). */
const FRAME_MAX_ZOOM = 17;
const MAX_ZOOM = 19;
const EDGE_PX = 32;
const MIN_FRAME_PX = 80;

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function creditHtml(credit: Credit): string {
  const text = escapeHtml(credit.text);
  return credit.url ? `<a href="${escapeHtml(credit.url)}" target="_blank" rel="noopener">${text}</a>` : text;
}

/** The least the camera bounds reach past the basemap's, each way. */
const CAMERA_MARGIN_M = 2000;

/**
 * Where the camera may go: the basemap's bounds, widened each way by half
 * their size and at least CAMERA_MARGIN_M, so a spot at the edge can still be
 * brought out from under the sheet, and a small coverage doesn't pin a tall
 * phone screen at a zoom too close to frame its spots. MapLibre keeps the
 * whole view inside these. Beyond the basemap's bounds the map is the plain ground.
 */
function cameraBounds([west, south, east, north]: Bounds): Bounds {
  const metresPerDegLat = 111_320;
  const metresPerDegLon = metresPerDegLat * Math.cos((((south + north) / 2) * Math.PI) / 180);
  const dx = Math.max((east - west) / 2, CAMERA_MARGIN_M / metresPerDegLon);
  const dy = Math.max((north - south) / 2, CAMERA_MARGIN_M / metresPerDegLat);
  return [west - dx, south - dy, east + dx, north + dy];
}

export const createMapLibre: MapFactory = (container: HTMLElement, options: MapOptions): MapSurface => {
  const { basemap } = options;
  const map = new MapLibreMap({
    container,
    style: basemapStyle(basemap),
    attributionControl: { compact: true, customAttribution: options.credits.map(creditHtml) },
    ...(basemap
      ? {
          bounds: basemap.bounds,
          maxBounds: cameraBounds(basemap.bounds),
          minZoom: basemap.minZoom,
        }
      : {}), // the first `show` frames the markers
    maxZoom: MAX_ZOOM,
    renderWorldCopies: false,
    dragRotate: false,
    pitchWithRotate: false,
    touchPitch: false,
  });
  map.touchZoomRotate.disableRotation();
  map.keyboard.disableRotation();  // The credits start folded into the ⓘ on a phone; MapLibre would open them at first.
  container.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");

  let warned = false;
  map.on("error", (event) => {
    if (warned) return;
    warned = true;
    console.warn(`The basemap didn't load; the spots are drawn without it. ${event.error?.message ?? ""}`);
  });

  let markers: Marker[] = [];
  const spotMarkers = new Map<string, { marker: Marker; el: HTMLElement }>();

  const padding = () => {
    const { top, bottom } = options.insets();
    const height = container.clientHeight;
    // Frame between the header and the sheet, in at least MIN_FRAME_PX.
    const room = Math.max(0, height - top - 2 * EDGE_PX - MIN_FRAME_PX);
    return { top: top + EDGE_PX, bottom: Math.min(bottom, room) + EDGE_PX, left: EDGE_PX, right: EDGE_PX };
  };

  return {
    show(next: MapMarkers) {
      for (const marker of markers) marker.remove();
      markers = [];
      spotMarkers.clear();
      const frame = new LngLatBounds();
      if (next.origin) {
        const el = document.createElement("div");
        el.className = "marker-origin";
        el.setAttribute("aria-label", "You are here");
        markers.push(new Marker({ element: el }).setLngLat([next.origin.lon, next.origin.lat]).addTo(map));
        frame.extend([next.origin.lon, next.origin.lat]);
      }
      // Drawn last first, so number 1 sits on top.
      for (const spot of [...next.spots].reverse()) {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "marker-spot";
        el.textContent = String(spot.rank);
        el.dataset["marker"] = spot.id;
        el.setAttribute("aria-label", `${spot.rank}. ${spot.name}`);
        el.addEventListener("click", (event) => {
          event.stopPropagation();
          options.onSelect(spot.id);
        });
        const marker = new Marker({ element: el }).setLngLat([spot.lon, spot.lat]).addTo(map);
        markers.push(marker);
        spotMarkers.set(spot.id, { marker, el });
        frame.extend([spot.lon, spot.lat]);
      }
      if (!frame.isEmpty()) {
        map.fitBounds(frame, { padding: padding(), maxZoom: FRAME_MAX_ZOOM, duration: 400 });
      }
    },
    highlight(id: string | undefined) {
      for (const [spotId, { el }] of spotMarkers) {
        const on = spotId === id;
        el.classList.toggle("is-selected", on);
        el.setAttribute("aria-pressed", String(on));
        el.style.zIndex = on ? "2" : "";
      }
      const chosen = id === undefined ? undefined : spotMarkers.get(id);
      if (chosen) map.easeTo({ center: chosen.marker.getLngLat(), padding: padding(), duration: 400 });
    },
  };
};
