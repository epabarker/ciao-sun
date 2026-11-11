// The scorer under test. This is the one place the golden-fixture harness
// learns about the JS scorer.

import type { Answer, Query } from "../../src/contract";
import { answerWith } from "../../src/scorer/answer";
import type { SightOverrides } from "../../src/scorer/scoring";
import type { Tile } from "../../src/tile/decode";
import type { CoverageGeometry } from "./fixture-set";

export interface ScorerWorld {
  /** Exactly the tiles the fixture names (docs/fixtures.md, "tiles"). */
  tiles: readonly Tile[];
  /** The manifest's coverage polygon: an origin outside it is `not-covered`. */
  coverage: CoverageGeometry;
  /**
   * Sun in view and low sun to force at near-boundary minutes, when the
   * harness re-runs a Query with the reference's side of them (`referenceSight`).
   */
  sight?: SightOverrides;
}

/** Pure: `(Query, tiles) -> Answer`. */
export type Scorer = (query: Query, world: ScorerWorld) => Answer | Promise<Answer>;

export const scorer: Scorer | undefined = (query, world) =>
  answerWith(query, world.tiles, world.coverage, world.sight);
