// What the map reads from the build's manifest (schema: `ciao_sun.manifest`).

import type { Build, Manifest } from "../loader/loader";
import type { Basemap, Bounds, Credit } from "./map";

/** The manifest sources the map's corner ⓘ credits (spec #27, "Attribution placement"). */
export const MAP_CREDIT_SOURCES: readonly string[] = ["OpenStreetMap", "Protomaps"];

const isNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

/** The build's basemap, or undefined when the manifest has none (or one this app can't use). */
export function basemapOf(build: Build): Basemap | undefined {
  const section = build.manifest["basemap"];
  if (typeof section !== "object" || section === null) return undefined;
  const { bounds, minZoom, maxZoom } = section as Record<string, unknown>;
  if (!Array.isArray(bounds) || bounds.length !== 4 || !bounds.every(isNumber)) return undefined;
  if (!isNumber(minZoom) || !isNumber(maxZoom)) return undefined;
  return { tiles: `${build.url}basemap/{z}/{x}/{y}.mvt`, bounds: bounds as Bounds, minZoom, maxZoom };
}

/** The corner credits: the manifest's attribution text for OpenStreetMap and Protomaps, in its order. */
export function mapCredits(manifest: Manifest): Credit[] {
  const lines = Array.isArray(manifest["attribution"]) ? manifest["attribution"] : [];
  return lines.flatMap((line: unknown): Credit[] => {
    if (typeof line !== "object" || line === null) return [];
    const { source, text, licenceUrl } = line as Record<string, unknown>;
    if (typeof source !== "string" || !MAP_CREDIT_SOURCES.includes(source) || typeof text !== "string") return [];
    return [typeof licenceUrl === "string" ? { text, url: licenceUrl } : { text }];
  });
}
