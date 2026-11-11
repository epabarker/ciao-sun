// The two identifiers both the app and the release job check, in one place.
//
// This module imports nothing, so `scripts/release.ts` can import its values
// when Node runs the script by type stripping.

/**
 * A 1 km tile's OS grid reference, as docs/tile-format-f1.md defines it: two
 * letters A-Z, never I, and four digits ("ST5873"). The groups are the
 * letters, the easting km and the northing km.
 */
export const GRID_REF = /^([A-HJ-Z]{2})(\d{2})(\d{2})$/;

/** A data build id: its UTC date and a letter, e.g. "20261111a". */
export const BUILD_ID = /^\d{8}[a-z]$/;
