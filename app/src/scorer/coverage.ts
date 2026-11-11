// The coverage polygon: the area a build produces Candidates for. An origin
// outside it is `not-covered`. `ciao_sun.coverage.Coverage.contains` is the
// reference, and this is the same test.

/** A position as GeoJSON writes it: longitude, then latitude, WGS84 degrees. */
export type Position = readonly number[];

/** The manifest's `coverage`: a GeoJSON Polygon or MultiPolygon in WGS84 longitude/latitude. */
export type CoverageGeometry =
  | { readonly type: "Polygon"; readonly coordinates: readonly (readonly Position[])[] }
  | { readonly type: "MultiPolygon"; readonly coordinates: readonly (readonly (readonly Position[])[])[] };

/**
 * Whether a WGS84 position is inside the coverage: inside any outer ring.
 *
 * Even-odd ray casting on plain longitude/latitude, each ring edge taken as a
 * straight line in degrees (no map projection). An edge counts when exactly
 * one of its ends has a latitude greater than `lat` and it crosses that
 * latitude at a longitude greater than `lon`. Every edge of a ring is taken,
 * the one from its last position back to its first included. Holes are
 * ignored.
 */
export function contains(coverage: CoverageGeometry, lat: number, lon: number): boolean {
  const polygons = coverage.type === "Polygon" ? [coverage.coordinates] : coverage.coordinates;
  for (const polygon of polygons) {
    const ring = polygon[0] ?? [];
    let inside = false;
    for (let i = 0; i < ring.length; i++) {
      const [lonA, latA] = ring[i]! as [number, number];
      const [lonB, latB] = ring[(i + 1) % ring.length]! as [number, number];
      if ((latA > lat) !== (latB > lat) &&lon < lonA + ((lat - latA) * (lonB - lonA)) / (latB - latA)) {
        inside = !inside;
      }
    }
    if (inside) {
      return true;
    }
  }
  return false;
}
