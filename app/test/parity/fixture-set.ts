// Reads a build directory's golden fixtures from disk, in the hosted layout
// (docs/fixtures.md): <dataBase>/f<format>/<build>/{manifest.json,tiles/,fixtures/}.
//
// The set under test is the committed synthetic build unless the environment
// names another, which is how the release job points the same tests at the
// pinned real build once it has downloaded it:
//
//   CIAO_SUN_FIXTURES_DATA_BASE   directory holding f<format>/<build>/
//   CIAO_SUN_FIXTURES_BUILD       build id
//   CIAO_SUN_FIXTURES_FORMAT      format number (default 1)

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import type { Answer, Query, Status } from "../../src/contract";
import { type Tile, decodeTile } from "../../src/tile/decode";

export interface Pin {
  /** A directory here; the URL prefix of the hosted data in the app. */
  dataBase: string;
  format: number;
  build: string;
}

export const SYNTHETIC_PIN: Pin = {
  dataBase: fileURLToPath(new URL("../../../fixtures/synthetic", import.meta.url)),
  format: 1,
  build: "20261111a",
};

export function pinFromEnvironment(env: NodeJS.ProcessEnv = process.env): Pin {
  const dataBase = env.CIAO_SUN_FIXTURES_DATA_BASE;
  const build = env.CIAO_SUN_FIXTURES_BUILD;
  if (!dataBase && !build) {
    return SYNTHETIC_PIN;
  }
  if (!dataBase || !build) {
    throw new Error("Set both CIAO_SUN_FIXTURES_DATA_BASE and CIAO_SUN_FIXTURES_BUILD, or neither.");
  }
  return { dataBase: resolve(dataBase), format: Number(env.CIAO_SUN_FIXTURES_FORMAT ?? 1), build };
}

/** One line of `fixtures/index.json`. */
export interface IndexEntry {
  id: string;
  file: string;
  status: Status;
  tiles: string[];
}

export interface ReferenceSunTrack {
  start: string;
  stepMin: number;
  azimuth: number[];
  apparentElevation: number[];
}

export interface NearBoundary {
  toleranceDeg: number;
  /** Per candidateId, the sun-track minutes at which sun in view may differ. */
  candidates: Record<string, number[]>;
  /** The sun-track minutes at which "low sun" may differ, for every Candidate. */
  lowSunBand: number[];
}

/** `fixtures/<id>.json`. */
export interface FixtureDocument {
  query: Query;
  tiles: string[];
  answer: Answer;
  sunTrack: ReferenceSunTrack;
  nearBoundary: NearBoundary;
}

/** A GeoJSON Polygon or MultiPolygon in WGS84 longitude/latitude. */
export interface CoverageGeometry {
  type: "Polygon" | "MultiPolygon";
  coordinates: unknown;
}

/** A fixture with what the scorer under test is to be given. */
export interface LoadedFixture extends FixtureDocument {
  id: string;
  /** The decoded tiles named by `tiles`, in that order: exactly these and no others. */
  decodedTiles: Tile[];
  /** The manifest's coverage polygon. */
  coverage: CoverageGeometry;
}

export class FixtureSet {
  readonly buildDir: string;
  readonly entries: readonly IndexEntry[];
  readonly coverage: CoverageGeometry;
  private readonly tiles = new Map<string, Promise<Tile>>();

  constructor(readonly pin: Pin) {
    this.buildDir = resolve(pin.dataBase, `f${pin.format}`, pin.build);
    const manifest = this.json<{ format: number; build: string; coverage: CoverageGeometry }>(
      "manifest.json",
    );
    const index = this.json<{ format: number; build: string; fixtures: IndexEntry[] }>(
      "fixtures/index.json",
    );
    for (const [name, document] of [["manifest.json", manifest] as const, ["fixtures/index.json", index] as const]) {
      if (document.format !== pin.format || document.build !== pin.build) {
        throw new Error(
          `${name} is f${document.format}/${document.build}, not the pinned f${pin.format}/${pin.build}`,
        );
      }
    }
    this.entries = index.fixtures;
    this.coverage = manifest.coverage;
  }

  private json<T>(path: string): T {
    return JSON.parse(readFileSync(resolve(this.buildDir, path), "utf8")) as T;
  }

  /** One tile of the build, decoded once however many fixtures name it. */
  tile(gridRef: string): Promise<Tile> {
    let tile = this.tiles.get(gridRef);
    if (!tile) {
      const bytes = readFileSync(resolve(this.buildDir, "tiles", `${gridRef}.bin`));
      tile = decodeTile(new Uint8Array(bytes), gridRef);
      this.tiles.set(gridRef, tile);
    }
    return tile;
  }

  async load(entry: IndexEntry): Promise<LoadedFixture> {
    const document = this.json<FixtureDocument>(`fixtures/${entry.file}`);
    return {
      ...document,
      id: entry.id,
      decodedTiles: await Promise.all(document.tiles.map((gridRef) => this.tile(gridRef))),
      coverage: this.coverage,
    };
  }
}
