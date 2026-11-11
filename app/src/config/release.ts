// The release config: the committed pin file `app/release.json`, which names
// the data host and the one data build this release was tested with (spec
// #27, "Release and CI"; ADR 0002). Nothing else in `src/` names a data
// origin.
//
//   dataBase  URL prefix of the hosted builds; relative resolves against the page
//   format    the tile and manifest format of the pinned build
//   build     the pinned build id, e.g. "20261111a"

import pinFile from "../../release.json";

export interface ReleaseConfig {
  dataBase: string;
  format: number;
  build: string;
}

const BUILD_ID = /^\d{8}[a-z]$/;

/** A release config from its JSON, or an error naming what is wrong with it. */
export function parseReleaseConfig(json: unknown): ReleaseConfig {
  const { dataBase, format, build } = (json ?? {}) as Record<string, unknown>;
  if (typeof dataBase !== "string" || dataBase === "") {
    throw new TypeError("release config: dataBase must be a non-empty URL");
  }
  if (typeof format !== "number" || !Number.isInteger(format) || format < 1) {
    throw new TypeError("release config: format must be a positive integer");
  }
  if (typeof build !== "string" || !BUILD_ID.test(build)) {
    throw new TypeError('release config: build must be a build id like "20261111a"');
  }
  return { dataBase, format, build };
}

/** This release's pin. */
export const RELEASE: ReleaseConfig = parseReleaseConfig(pinFile);
