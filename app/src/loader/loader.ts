// The data loader: from the release config's pin to decoded tiles.
//
// 1. `openBuild` fetches `<dataBase>/f<format>/<build>/manifest.json` and
//    refuses, with `UnsupportedFormatError`, a manifest whose format this app
//    can't read, before any tile is requested (ADR 0002).
// 2. `Build.area(origin)` says whether the origin is in the coverage and, if
//    it is, fetches and decodes the tiles in reach of it. A tile is fetched
//    once per Build.
//
// `fetch` is injected; the URL layout is the spec's "Data hosting and layout".

import type { ReleaseConfig } from "../config/release";
import { MAX_WALK_CAP_MIN } from "../contract";
import { WALK_SPEED_M_PER_MIN } from "../router/world";
import { FORMAT, type Tile, UnsupportedFormatError, decodeTile } from "../tile/decode";
import { type CoverageGeometry, coverageContains } from "./coverage";
import { gridRefsInReach } from "./grid";

export type FetchLike = (url: string) => Promise<Response>;

/**
 * How far from the origin tiles are fetched: the 20 min walk cap, whatever
 * the query's max walk, as `ciao_sun.reference.fixtures.tiles_touched` does.
 * The nearest spot with sun beyond the limit is looked for out to the cap.
 */
export const TILE_REACH_M = MAX_WALK_CAP_MIN * WALK_SPEED_M_PER_MIN;

/** One line of the manifest's tile index. */
export interface TileEntry {
  bytes: number;
  sha256: string;
  candidates: number;
}

/** What the app reads of `manifest.json` (built by `ciao_sun.manifest`). */
export interface Manifest {
  format: number;
  build: string;
  coverage: CoverageGeometry;
  tiles: Record<string, TileEntry>;
  /** The rest (licence, attribution, survey years, basemap) is for the About sheet and the map. */
  [field: string]: unknown;
}

export type Area = { covered: false } | { covered: true; tiles: Tile[] };

export interface Build {
  readonly manifest: Manifest;
  /** `<dataBase>/f<format>/<build>/`, absolute, ending in "/". */
  readonly url: string;
  /** Whether the origin is covered, and the decoded tiles in reach of it if so. */
  area(origin: { lat: number; lon: number }): Promise<Area>;
}

export interface LoaderOptions {
  fetch: FetchLike;
  /** What a relative `dataBase` is resolved against: the page's URL in the app. */
  baseUrl?: string;
}

/** The data could not be fetched: the network, or the host answered with an error. */
export class DataUnavailableError extends Error {
  override name = "DataUnavailableError";
}

async function get(fetch: FetchLike, url: string): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch (cause) {
    throw new DataUnavailableError(`${url}: ${String(cause)}`, { cause });
  }
  if (!response.ok) {
    throw new DataUnavailableError(`${url}: HTTP ${response.status}`);
  }
  return response;
}

export function buildUrl(config: ReleaseConfig, baseUrl?: string): string {
  const dataBase = config.dataBase.endsWith("/") ? config.dataBase : `${config.dataBase}/`;
  return new URL(`f${config.format}/${config.build}/`, new URL(dataBase, baseUrl)).href;
}

/** Fetch and check the pinned build's manifest. */
export async function openBuild(config: ReleaseConfig, options: LoaderOptions): Promise<Build> {
  const url = buildUrl(config, options.baseUrl);
  const manifest = (await (await get(options.fetch, `${url}manifest.json`)).json()) as Manifest;
  if (manifest.format !== FORMAT) {
    throw new UnsupportedFormatError(typeof manifest.format === "number" ? manifest.format : Number.NaN);
  }
  if (manifest.build !== config.build) {
    throw new Error(`the manifest at ${url} is build ${manifest.build}, not the pinned ${config.build}`);
  }

  const tiles = new Map<string, Promise<Tile>>();
  const tile = (gridRef: string): Promise<Tile> => {
    let pending = tiles.get(gridRef);
    if (!pending) {
      pending = get(options.fetch, `${url}tiles/${gridRef}.bin`)
        .then(async (response) => decodeTile(new Uint8Array(await response.arrayBuffer()), gridRef))
        .catch((error: unknown) => {
          tiles.delete(gridRef);
          throw error;
        });
      tiles.set(gridRef, pending);
    }
    return pending;
  };

  return {
    manifest,
    url,
    async area(origin) {
      if (!coverageContains(manifest.coverage, origin.lat, origin.lon)) {
        return { covered: false };
      }
      const gridRefs = gridRefsInReach(Object.keys(manifest.tiles), origin.lat, origin.lon, TILE_REACH_M);
      return { covered: true, tiles: await Promise.all(gridRefs.map(tile)) };
    },
  };
}
