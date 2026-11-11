// The sky slot's provenance (#50): where its value came from, and the line
// under the sentence that says so. Only a value the forecast filled carries
// SKY_CREDIT (spec #27, "Attribution placement").

import type { UnavailableReason } from "../forecast/forecast";
import { TIME_ZONE, toLocalIso } from "../solar/local-day";
import { h } from "./dom";

/** Where the sky slot's value came from. */
export type SkySource =
  /** Not asked: no origin yet, or the query has no window. */
  | { kind: "unfilled" }
  /** The forecast has been asked for and has not answered. */
  | { kind: "pending" }
  /** The forecast filled it, from a response fetched at `fetchedAtMs`. */
  | { kind: "forecast"; fetchedAtMs: number }
  /** No forecast for this window: the slot is for manual entry. */
  | { kind: "unavailable"; reason: UnavailableReason }
  /** Set by hand; a forecast arriving later does not overwrite it. */
  | { kind: "manual" };

/**
 * The credit a forecast-filled sky slot carries, inline beside the slot (spec
 * #27, "Attribution placement"). The About sheet credits the same two sources
 * from the manifest's `attribution` (`ciao_sun.manifest`), not from here.
 */
export const SKY_CREDIT = {
  source: "Met Office via Open-Meteo",
  licences: [
    { name: "CC BY-SA 4.0", url: "https://creativecommons.org/licenses/by-sa/4.0/" },
    { name: "CC BY 4.0", url: "https://creativecommons.org/licenses/by/4.0/" },
  ],
  note: "cloud cover categorised by Ciao Sun",
} as const;

const NO_FORECAST: Record<UnavailableReason, string> = {
  offline: "Offline, so no forecast: set the sky by hand.",
  "timed-out": "The forecast didn't load: set the sky by hand.",
  "request-failed": "The forecast didn't load: set the sky by hand.",
  "past-horizon": "Beyond the forecast: set the sky by hand.",
};

/** Under the sentence: the forecast's fetch time and credit, or why there is none. */
export function skyNote(source: SkySource): HTMLElement | null {
  if (source.kind === "unavailable") {
    return h("p", { class: "sky-note", "data-field": "sky-note" }, NO_FORECAST[source.reason]);
  }
  if (source.kind !== "forecast") return null;
  // The fetch time on the Europe/London clock, whatever the device's zone.
  const iso = toLocalIso(source.fetchedAtMs, TIME_ZONE);
  const link = (licence: { name: string; url: string }) =>
    h("a", { href: licence.url, target: "_blank", rel: "noopener" }, licence.name);
  const [bySa, by] = SKY_CREDIT.licences;
  return h(
    "p",
    { class: "sky-note", "data-field": "sky-credit" },
    h("span", { "data-field": "fetched-at" }, "Forecast fetched ", h("time", { datetime: iso }, iso.slice(11, 16))),
    ` · ${SKY_CREDIT.source} (`,
    link(bySa),
    ", ",
    link(by),
    `) · ${SKY_CREDIT.note}`,
  );
}
