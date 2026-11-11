// The scorer under test. This is the one place the golden-fixture harness
// learns about the JS scorer.

import type { Answer, Query, Status } from "../../src/contract";
import { answer } from "../../src/scorer/answer";
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

export const scorer: Scorer | undefined = (query, world) => answer(query, world.tiles);

/**
 * Why Answer parity is not yet checked for a fixture, from its Query and the
 * reference's status; undefined when it is. The JS scorer answers Morning
 * `ranked` Answers (#43). The Evening window, the fallback, lamp-only,
 * no-evening-window and not-covered are #44, which deletes this.
 */
export function answerParityPending(query: Query, status: Status): string | undefined {
  if (query.window === "morning" && status === "ranked") {
    return undefined;
  }
  return `pending #44: ${query.window} ${status}`;
}
