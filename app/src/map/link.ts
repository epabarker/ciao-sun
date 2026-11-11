// The link between the screen's state and the map: the screen calls `update`
// on every draw, and the map is asked to change only what changed, so a
// highlight does not reframe the map and a redraw does not move it.
//
// The map is made once, when the build opens. If it can't be made (no WebGL,
// or the factory fails), the link does nothing and the list carries on alone.

import type { Build } from "../loader/loader";
import type { Result } from "../ui/screen";
import { basemapOf, mapCredits } from "./manifest";
import type { MapFactory, MapMarkers, MapPoint, MapSurface } from "./map";

export interface MapView {
  origin?: MapPoint;
  result: Result;
  /** The highlighted spot's candidateId. */
  selected?: string;
}

export interface MapLink {
  update(view: MapView): void;
  /** Settles once the map is made, or has failed to be. */
  readonly ready: Promise<void>;
}

export interface LinkOptions {
  onSelect(id: string): void;
  insets(): { top: number; bottom: number };
}

/** The markers for a view: the origin, and the Answer's spots numbered in list order. */
export function markersOf(view: MapView): MapMarkers {
  const spots = view.result.kind === "answer" ? view.result.answer.spots : [];
  return {
    ...(view.origin ? { origin: { lat: view.origin.lat, lon: view.origin.lon } } : {}),
    spots: spots.map((spot, i) => ({ id: spot.candidateId, rank: i + 1, name: spot.name, lat: spot.lat, lon: spot.lon })),
  };
}

export function linkMap(factory: MapFactory, container: HTMLElement, build: Build, options: LinkOptions): MapLink {
  let surface: MapSurface | undefined;
  let latest: MapView | undefined;
  let shown: string | undefined;
  let highlighted: string | undefined;

  const sync = () => {
    if (!surface || !latest) return;
    const markers = markersOf(latest);
    const key = JSON.stringify(markers);
    if (key !== shown) {
      shown = key;
      surface.show(markers);
    }
    const selected = markers.spots.some((spot) => spot.id === latest!.selected) ? latest.selected : undefined;
    if (selected !== highlighted) {
      highlighted = selected;
      surface.highlight(selected);
    }
  };

  const ready = (async () => {
    try {
      surface = await factory(container, {
        basemap: basemapOf(build),
        credits: mapCredits(build.manifest),
        onSelect: options.onSelect,
        insets: options.insets,
      });
    } catch (error) {
      console.warn("No map: the list is shown alone.", error);
      container.classList.add("map-unavailable");
      return;
    }
    sync();
  })();

  return {
    ready,
    update(view) {
      latest = view;
      sync();
    },
  };
}
