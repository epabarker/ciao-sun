// The About sheet's content (spec #27, user stories 50-55): the credits,
// survey years and licence of the build actually loaded, read from its
// manifest, plus the fixed caveats.
//
// Nothing here names a data source: every credit, year and licence comes from
// the manifest (`ciao_sun.manifest`), so a new build's credits need no app
// change. A malformed field is left out rather than thrown on, so a bad
// manifest can't take down the answer screen. Only the caveats are fixed copy.

import type { Manifest } from "../loader/loader";

export interface Credit {
  source: string;
  text: string;
  licence?: string;
  /** http(s) only; anything else is dropped. */
  licenceUrl?: string;
}

export interface About {
  build?: string;
  licence?: { name: string; url?: string };
  /** In the manifest's display order. */
  credits: Credit[];
  /** Years the EA LIDAR in the build was flown, ascending. */
  surveyYears: number[];
}

/** The About content of a manifest; `undefined` while no manifest is loaded. */
export function readAbout(manifest: Manifest | undefined): About | undefined {
  if (!manifest) return undefined;
  const licence = record(manifest.licence);
  const licenceName = licence && text(licence.name);
  return {
    build: text(manifest.build),
    licence: licenceName ? { name: licenceName, url: httpUrl(licence.url) } : undefined,
    credits: (Array.isArray(manifest.attribution) ? manifest.attribution : []).flatMap((entry): Credit[] => {
      const line = record(entry);
      const source = line && text(line.source);
      const said = line && text(line.text);
      if (!source || !said) return [];
      return [{ source, text: said, licence: text(line.licence), licenceUrl: httpUrl(line.licenceUrl) }];
    }),
    surveyYears: (Array.isArray(manifest.lidarSurveyYears) ? manifest.lidarSurveyYears : [])
      .filter((year): year is number => Number.isInteger(year))
      .sort((a, b) => a - b),
  };
}

/** The ranking's reason as the spec labels it (GLOSSARY.md "Protocols factor"). */
export const PROTOCOLS_FACTOR = "Protocols factor: untested in humans";

/**
 * The fixed caveats, by key. Sources: ADR 0003 (leaf); spec #27 stories 52
 * and 53 (clutter, refraction); GLOSSARY.md "Protocols factor" (ranking); the
 * book's duration figures as `research/protocols-falsification` row C1
 * records them (duration).
 */
export const CAVEATS = {
  leaf: "Trees are treated as in full leaf all year, so winter sun may arrive a little earlier than shown.",
  clutter:
    "Stand clear of hedges and walls right beside you. The model ignores clutter that close, and it can still block your sun.",
  refraction:
    "First-sun times carry about ±1.5 min of refraction uncertainty, so read them as close, not exact.",
  ranking:
    "When the sky isn't overcast, spots are ranked by low-sun minutes (sun between 0° and 30° up), most first. " +
    "That follows the book Protocols' claim that low sun, at either end of the day, gives the best quality of light.",
  duration:
    "The Duration target of 10, 20 and 30 min for a clear, partly cloudy and overcast sky is Light Protocol 1's. " +
    "The book's figures disagree: Sleep Protocol 1 says at least 5–10 min when clear, 15 when cloudy and 30 when densely overcast. " +
    "The book cites no study for either, so treat the target as something to aim for, not a threshold.",
} as const;

export type CaveatKey = keyof typeof CAVEATS;

/** "2019", "2019 and 2021", "2017, 2019 and 2021". */
export function listYears(years: readonly number[]): string {
  if (years.length <= 1) return years.join("");
  return `${years.slice(0, -1).join(", ")} and ${years[years.length - 1]}`;
}

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function httpUrl(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : undefined;
  } catch {
    return undefined;
  }
}
