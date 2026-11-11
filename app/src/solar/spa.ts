// NREL SPA: the geometric position of the sun.
//
// Reda and Andreas, "Solar Position Algorithm for Solar Radiation
// Applications", NREL/TP-560-34302 (revised 2008). This follows pvlib's
// `spa.solar_position_numpy` step by step, because docs/solar-model.md names
// that as the reference. SPA's own refraction and rise/set routines are not
// ported: the model does not use them.

import { DEGREES_PER_RADIAN, RADIANS_PER_DEGREE } from "../angles";
import { B0, B1, L0, L1, L2, L3, L4, L5, NUTATION_ABCD, NUTATION_Y, R0, R1, R2, R3, R4 } from "./spa-tables";

/** Delta T (TT - UT1) in seconds: fixed for every query. */
export const DELTA_T_SECONDS = 67.0;
/** Observer altitude in metres: fixed for every query. */
export const OBSERVER_ALTITUDE_M = 0.0;

type Table = readonly (readonly number[])[];

/** x mod m with the sign of m, as Python's `%`. */
function mod(x: number, m: number): number {
  return ((x % m) + m) % m;
}

function periodicSum(table: Table, jme: number): number {
  let sum = 0;
  for (const [a, b, c] of table as readonly (readonly [number, number, number])[]) {
    sum += a * Math.cos(b + c * jme);
  }
  return sum;
}

/** sum of series[k] * jme^k, over 1e8. */
function series(tables: readonly Table[], jme: number): number {
  let total = 0;
  let power = 1;
  for (const table of tables) {
    total += periodicSum(table, jme) * power;
    power *= jme;
  }
  return total / 1e8;
}

/** [nutation in longitude, nutation in obliquity], degrees. */
function nutation(jce: number): [number, number] {
  const jce2 = jce * jce;
  const jce3 = jce2 * jce;
  const x = [
    297.85036 + 445267.11148 * jce - 0.0019142 * jce2 + jce3 / 189474, // mean elongation of the moon
    357.52772 + 35999.05034 * jce - 0.0001603 * jce2 - jce3 / 300000, // mean anomaly of the sun
    134.96298 + 477198.867398 * jce + 0.0086972 * jce2 + jce3 / 56250, // mean anomaly of the moon
    93.27191 + 483202.017538 * jce - 0.0036825 * jce2 + jce3 / 327270, // moon's argument of latitude
    125.04452 - 1934.136261 * jce + 0.0020708 * jce2 + jce3 / 450000, // moon's ascending node
  ] as const;
  let psi = 0;
  let epsilon = 0;
  for (let row = 0; row < NUTATION_Y.length; row++) {
    const y = NUTATION_Y[row]!;
    const [a, b, c, d] = NUTATION_ABCD[row] as readonly [number, number, number, number];
    const argument =
      RADIANS_PER_DEGREE * (y[0]! * x[0] + y[1]! * x[1] + y[2]! * x[2] + y[3]! * x[3] + y[4]! * x[4]);
    psi += (a + b * jce) * Math.sin(argument);
    epsilon += (c + d * jce) * Math.cos(argument);
  }
  return [psi / 36000000, epsilon / 36000000];
}

/** Mean obliquity of the ecliptic, arcseconds. */
function meanObliquity(jme: number): number {
  const u = jme / 10;
  const coefficients = [
    84381.448, -4680.93, -1.55, 1999.25, -51.38, -249.67, -39.05, 7.12, 27.87, 5.79, 2.45,
  ];
  let total = 0;
  for (let k = coefficients.length - 1; k >= 0; k--) {
    total = total * u + coefficients[k]!;
  }
  return total;
}

export interface SunPosition {
  /** True azimuth: degrees clockwise from true north, 0 <= azimuth < 360. */
  azimuth: number;
  /** Topocentric elevation of the disc centre with no refraction, degrees. */
  elevation: number;
}

/**
 * The sun's geometric position at an instant (Unix seconds, taken as UT1) for
 * an observer at sea level at `lat`, `lon` (degrees, north and east positive).
 */
export function sunPosition(unixSeconds: number, lat: number, lon: number): SunPosition {
  const jd = unixSeconds / 86400 + 2440587.5;
  const jde = jd + DELTA_T_SECONDS / 86400;
  const jc = (jd - 2451545) / 36525;
  const jce = (jde - 2451545) / 36525;
  const jme = jce / 10;

  // Earth's heliocentric position, then the sun's geocentric one.
  const radius = series([R0, R1, R2, R3, R4], jme); // AU
  const helioLongitude = mod(series([L0, L1, L2, L3, L4, L5], jme) * DEGREES_PER_RADIAN, 360);
  const helioLatitude = series([B0, B1], jme) * DEGREES_PER_RADIAN;
  const theta = mod(helioLongitude + 180, 360);
  const beta = -helioLatitude;

  const [deltaPsi, deltaEpsilon] = nutation(jce);
  const epsilon = meanObliquity(jme) / 3600 + deltaEpsilon; // true obliquity, degrees
  const aberration = -20.4898 / (3600 * radius);
  const lambda = theta + deltaPsi + aberration; // apparent sun longitude, degrees

  const meanSidereal = mod(
    280.46061837 + 360.98564736629 * (jd - 2451545) + 0.000387933 * jc * jc - (jc * jc * jc) / 38710000,
    360,
  );
  const sidereal = meanSidereal + deltaPsi * Math.cos(RADIANS_PER_DEGREE * epsilon);

  const epsilonRad = RADIANS_PER_DEGREE * epsilon;
  const lambdaRad = RADIANS_PER_DEGREE * lambda;
  const betaRad = RADIANS_PER_DEGREE * beta;
  const rightAscension = mod(
    DEGREES_PER_RADIAN *
      Math.atan2(
        Math.sin(lambdaRad) * Math.cos(epsilonRad) - Math.tan(betaRad) * Math.sin(epsilonRad),
        Math.cos(lambdaRad),
      ),
    360,
  );
  const declinationRad = Math.asin(
    Math.sin(betaRad) * Math.cos(epsilonRad) +
      Math.cos(betaRad) * Math.sin(epsilonRad) * Math.sin(lambdaRad),
  );

  // Topocentric: correct for the observer's place on the Earth's surface.
  const hourAngleRad = RADIANS_PER_DEGREE * mod(sidereal + lon - rightAscension, 360);
  const parallaxRad = RADIANS_PER_DEGREE * (8.794 / (3600 * radius));
  const latRad = RADIANS_PER_DEGREE * lat;
  const u = Math.atan(0.99664719 * Math.tan(latRad));
  const x = Math.cos(u) + (OBSERVER_ALTITUDE_M / 6378140) * Math.cos(latRad);
  const y = 0.99664719 * Math.sin(u) + (OBSERVER_ALTITUDE_M / 6378140) * Math.sin(latRad);
  const denominator =
    Math.cos(declinationRad) - x * Math.sin(parallaxRad) * Math.cos(hourAngleRad);
  const deltaAlphaRad = Math.atan2(
    -x * Math.sin(parallaxRad) * Math.sin(hourAngleRad),
    denominator,
  );
  const topoDeclinationRad = Math.atan2(
    (Math.sin(declinationRad) - y * Math.sin(parallaxRad)) * Math.cos(deltaAlphaRad),
    denominator,
  );
  const topoHourAngleRad = hourAngleRad - deltaAlphaRad;

  const elevation =
    DEGREES_PER_RADIAN *
    Math.asin(
      Math.sin(latRad) * Math.sin(topoDeclinationRad) +
        Math.cos(latRad) * Math.cos(topoDeclinationRad) * Math.cos(topoHourAngleRad),
    );
  // Astronomers' azimuth is measured westward from south; ours eastward from north.
  const astronomersAzimuth = mod(
    DEGREES_PER_RADIAN *
      Math.atan2(
        Math.sin(topoHourAngleRad),
        Math.cos(topoHourAngleRad) * Math.sin(latRad) - Math.tan(topoDeclinationRad) * Math.cos(latRad),
      ),
    360,
  );
  return { azimuth: mod(astronomersAzimuth + 180, 360), elevation };
}
