// The scorer under test. This is the one place the golden-fixture harness
// learns about the JS scorer: until it exists, Answer parity is skipped and
// everything else (tile decoding, sun track, sun events) still runs.
//
// To turn Answer parity on (#43, #44), import the scorer and export it here:
//
//   import { answer } from "../../src/scorer";
//   export const scorer: Scorer | undefined = (query, world) =>
//     answer(query, world.tiles, world.coverage);

import type { Answer, Query } from "../../src/contract";
import type { Tile } from "../../src/tile/decode";
import type { CoverageGeometry } from "./fixture-set";

export interface ScorerWorld {
  /** Exactly the tiles the fixture names (docs/fixtures.md, "tiles"). */
  tiles: readonly Tile[];
  /** The manifest's coverage polygon: an origin outside it is `not-covered`. */
  coverage: CoverageGeometry;
}

/** Pure: `(Query, tiles) -> Answer`. */
export type Scorer = (query: Query, world: ScorerWorld) => Answer | Promise<Answer>;

export const scorer: Scorer | undefined = undefined;
