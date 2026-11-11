// The build's coverage polygon (the manifest's `coverage`, GeoJSON Polygon or
// MultiPolygon in WGS84), and whether an origin is inside it.

export interface CoverageGeometry {
  type: "Polygon" | "MultiPolygon";
  coordinates: unknown;
}

type Ring = [number, number][];

function outerRings(coverage: CoverageGeometry): Ring[] {
  const polygons = (coverage.type === "Polygon" ? [coverage.coordinates] : coverage.coordinates) as Ring[][];
  if (!Array.isArray(polygons)) {
    throw new TypeError("malformed coverage coordinates");
  }
  return polygons.map((polygon) => polygon[0]!);
}

/**
 * Whether a WGS84 position is inside any outer ring of the coverage: the
 * even-odd test of `ciao_sun.coverage.Coverage.contains`, on plain degrees,
 * holes ignored.
 */
export function coverageContains(coverage: CoverageGeometry, lat: number, lon: number): boolean {
  for (const ring of outerRings(coverage)) {
    let inside = false;
    for (let i = 0; i < ring.length; i++) {
      const [lonA, latA] = ring[i]!;
      const [lonB, latB] = ring[(i + 1) % ring.length]!;
      if (latA > lat !== latB > lat && lon < lonA + ((lat - latA) * (lonB - lonA)) / (latB - latA)) {
        inside = !inside;
      }
    }
    if (inside) {
      return true;
    }
  }
  return false;
}
