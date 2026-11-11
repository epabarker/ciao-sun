// The OS National Grid, as far as the data loader needs it: which 1 km tiles
// lie within reach of an origin. Tiles are named by grid ref
// (docs/tile-format-f1.md); positions are WGS84.
//
// The projection is the OS's own recipe ("A guide to coordinate systems in
// Great Britain"): WGS84 to OSGB36 by the 7-parameter Helmert transform, then
// the National Grid's transverse Mercator on Airy 1830. The Helmert step is
// good to a few metres, against pyproj's transform in the build; callers pad
// distances by GRID_ERROR_M.

/** Metres the Helmert transform may be off by; a reach is widened by it. */
export const GRID_ERROR_M = 10;

const KM = 1000;
const HUNDRED_KM = 100_000;
const GRID_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"; // the grid has no I
const GRID_REF = /^([A-HJ-Z]{2})(\d{2})(\d{2})$/;

const DEG = Math.PI / 180;
const ARCSEC = DEG / 3600;

// GRS80 (WGS84 to within a millimetre here) and Airy 1830.
const WGS84 = { a: 6_378_137, b: 6_356_752.3141 };
const AIRY = { a: 6_377_563.396, b: 6_356_256.909 };

// WGS84 -> OSGB36 Helmert parameters (OS guide, section 6.6).
const HELMERT = {
  tx: -446.448,
  ty: 125.157,
  tz: -542.06,
  s: 20.4894e-6,
  rx: -0.1502 * ARCSEC,
  ry: -0.247 * ARCSEC,
  rz: -0.8421 * ARCSEC,
};

// National Grid projection constants.
const F0 = 0.9996012717;
const LAT0 = 49 * DEG;
const LON0 = -2 * DEG;
const E0 = 400_000;
const N0 = -100_000;

function toCartesian(lat: number, lon: number, a: number, b: number): [number, number, number] {
  const e2 = 1 - (b * b) / (a * a);
  const nu = a / Math.sqrt(1 - e2 * Math.sin(lat) ** 2);
  return [nu * Math.cos(lat) * Math.cos(lon), nu * Math.cos(lat) * Math.sin(lon), (1 - e2) * nu * Math.sin(lat)];
}

function fromCartesian(x: number, y: number, z: number, a: number, b: number): [number, number] {
  const e2 = 1 - (b * b) / (a * a);
  const p = Math.hypot(x, y);
  let lat = Math.atan2(z, p * (1 - e2));
  for (let i = 0; i < 10; i++) {
    const nu = a / Math.sqrt(1 - e2 * Math.sin(lat) ** 2);
    lat = Math.atan2(z + e2 * nu * Math.sin(lat), p);
  }
  return [lat, Math.atan2(y, x)];
}

/** A WGS84 position as National Grid [easting, northing] metres. */
export function wgs84ToNationalGrid(latDeg: number, lonDeg: number): [number, number] {
  const [x1, y1, z1] = toCartesian(latDeg * DEG, lonDeg * DEG, WGS84.a, WGS84.b);
  const { tx, ty, tz, s, rx, ry, rz } = HELMERT;
  const s1 = 1 + s;
  const x2 = tx + x1 * s1 - y1 * rz + z1 * ry;
  const y2 = ty + x1 * rz + y1 * s1 - z1 * rx;
  const z2 = tz - x1 * ry + y1 * rx + z1 * s1;
  const [lat, lon] = fromCartesian(x2, y2, z2, AIRY.a, AIRY.b);
  return project(lat, lon);
}

function project(lat: number, lon: number): [number, number] {
  const { a, b } = AIRY;
  const e2 = 1 - (b * b) / (a * a);
  const n = (a - b) / (a + b);
  const sin = Math.sin(lat);
  const cos = Math.cos(lat);
  const tan2 = Math.tan(lat) ** 2;
  const nu = (a * F0) / Math.sqrt(1 - e2 * sin * sin);
  const rho = (a * F0 * (1 - e2)) / (1 - e2 * sin * sin) ** 1.5;
  const eta2 = nu / rho - 1;

  const dLat = lat - LAT0;
  const sLat = lat + LAT0;
  const m =
    b *
    F0 *
    ((1 + n + (5 / 4) * n ** 2 + (5 / 4) * n ** 3) * dLat -
      (3 * n + 3 * n ** 2 + (21 / 8) * n ** 3) * Math.sin(dLat) * Math.cos(sLat) +
      ((15 / 8) * n ** 2 + (15 / 8) * n ** 3) * Math.sin(2 * dLat) * Math.cos(2 * sLat) -
      (35 / 24) * n ** 3 * Math.sin(3 * dLat) * Math.cos(3 * sLat));

  const i = m + N0;
  const ii = (nu / 2) * sin * cos;
  const iii = (nu / 24) * sin * cos ** 3 * (5 - tan2 + 9 * eta2);
  const iiiA = (nu / 720) * sin * cos ** 5 * (61 - 58 * tan2 + tan2 ** 2);
  const iv = nu * cos;
  const v = (nu / 6) * cos ** 3 * (nu / rho - tan2);
  const vi = (nu / 120) * cos ** 5 * (5 - 18 * tan2 + tan2 ** 2 + 14 * eta2 - 58 * tan2 * eta2);

  const dl = lon - LON0;
  const northing = i + ii * dl ** 2 + iii * dl ** 4 + iiiA * dl ** 6;
  const easting = E0 + iv * dl + v * dl ** 3 + vi * dl ** 5;
  return [easting, northing];
}

function squareOrigin(letters: string): [number, number] | undefined {
  // The inverse of `ciao_sun.tiles._grid_letters` (OS guide, Annex C).
  const l1 = GRID_LETTERS.indexOf(letters[0]!);
  const l2 = GRID_LETTERS.indexOf(letters[1]!);
  if (l1 < 0 || l2 < 0) {
    return undefined;
  }
  const e100k = ((l1 % 5) - 2) * 5 + (l2 % 5);
  const n100k = 19 - Math.floor(l1 / 5) * 5 - Math.floor(l2 / 5);
  if (e100k < 0 || e100k > 6 || n100k < 0 || n100k > 12) {
    return undefined;
  }
  return [e100k * HUNDRED_KM, n100k * HUNDRED_KM];
}

/** The [easting, northing] of the south-west corner of a 1 km grid ref's square. */
export function gridRefOrigin(gridRef: string): [number, number] {
  const match = GRID_REF.exec(gridRef);
  const origin = match ? squareOrigin(match[1]!) : undefined;
  if (!match || !origin) {
    throw new RangeError(`${JSON.stringify(gridRef)} is not a 1 km OS grid ref like "ST5873"`);
  }
  return [origin[0] + Number(match[2]) * KM, origin[1] + Number(match[3]) * KM];
}

/**
 * The grid refs of `index` whose 1 km square comes within `reachM` (widened
 * by GRID_ERROR_M) of a WGS84 origin, sorted. The point-to-square distance of
 * `ciao_sun.reference.fixtures.tiles_touched`.
 */
export function gridRefsInReach(index: Iterable<string>, lat: number, lon: number, reachM: number): string[] {
  const [x, y] = wgs84ToNationalGrid(lat, lon);
  const reach = reachM + GRID_ERROR_M;
  const touched: string[] = [];
  for (const gridRef of [...index].sort()) {
    const [west, south] = gridRefOrigin(gridRef);
    const dx = Math.max(west - x, 0, x - (west + KM));
    const dy = Math.max(south - y, 0, y - (south + KM));
    if (dx * dx + dy * dy <= reach * reach) {
      touched.push(gridRef);
    }
  }
  return touched;
}
