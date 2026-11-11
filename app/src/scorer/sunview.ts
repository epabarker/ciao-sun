// Sun in view and Sky openness: a sun track against Horizon profiles.
// `ciao_sun.reference.sunview` is the reference.

import type { SunTrack } from "../solar/sun-track";
import { CODE_COUNT, PROFILE_SAMPLES, codeToDegrees } from "../tile/decode";

export const LOW_SUN_MIN_DEG = 0;
export const LOW_SUN_MAX_DEG = 30;
export const OPENNESS_SECTOR_MARGIN_DEG = 10;
export const OPENNESS_CUTOFF = 0.75;

const SAMPLES_PER_DEG = PROFILE_SAMPLES / 360;
const RADIANS_PER_DEGREE = Math.PI / 180;
const DEGREES_OF_CODE = Float64Array.from({ length: CODE_COUNT }, (_, code) => codeToDegrees(code));
/** What one profile sample adds to the sector sky-view fraction: cos^2(max(h, 0)). */
const OPEN_SKY_OF_CODE = DEGREES_OF_CODE.map((h) => {
  const c = Math.cos(Math.max(h, 0) * RADIANS_PER_DEGREE);
  return c * c;
});

const wrap = (i: number, n: number) => ((i % n) + n) % n;

/**
 * Whether the sun is in view at one Candidate, per minute from `start` to
 * `end` (1 or 0).
 *
 * In view means the apparent elevation of the disc centre exceeds the Horizon
 * profile at the sun's true azimuth, interpolated linearly between the two
 * neighbouring samples. A profile below 0 degrees is used as it is.
 */
export function sunInView(codes: Uint8Array, track: SunTrack, start: number, end: number): Uint8Array {
  const inView = new Uint8Array(Math.max(end - start, 0));
  for (let m = start; m < end; m++) {
    inView[m - start] = track.apparentElevation[m]! > horizonAt(codes, track.azimuth[m]!) ? 1 : 0;
  }
  return inView;
}

/** A Horizon profile at a true azimuth, interpolated linearly between the two neighbouring samples. */
export function horizonAt(codes: Uint8Array, azimuthDeg: number): number {
  const position = wrap(azimuthDeg, 360) * SAMPLES_PER_DEG;
  const below = Math.floor(position);
  const fraction = position - below;
  const before = DEGREES_OF_CODE[codes[wrap(below, PROFILE_SAMPLES)]!]!;
  const after = DEGREES_OF_CODE[codes[wrap(below + 1, PROFILE_SAMPLES)]!]!;
  return before * (1 - fraction) + after * fraction;
}

/**
 * One Candidate's Last sun: the last minute of the track's day with the sun in
 * view. It is looked for over the whole day, not only a window, so it can fall
 * after Nominal sunset where the Horizon profile is below 0 degrees. Null
 * when the sun is never in view. `forced` sets sun in view at some minutes,
 * as `SightOverrides` does.
 */
export function lastSun(
  codes: Uint8Array,
  track: SunTrack,
  forced: Readonly<Record<number, boolean>> = {},
): number | null {
  const inView = sunInView(codes, track, 0, track.length);
  for (const [minute, value] of Object.entries(forced)) {
    if (Number(minute) < inView.length) inView[Number(minute)] = value ? 1 : 0;
  }
  const last = inView.lastIndexOf(1);
  return last < 0 ? null : last;
}

/** Whether the sun's apparent elevation is 0-30 degrees (both included), per minute (1 or 0). */
export function lowSun(track: SunTrack, start: number, end: number): Uint8Array {
  const low = new Uint8Array(Math.max(end - start, 0));
  for (let m = start; m < end; m++) {
    const elevation = track.apparentElevation[m]!;
    low[m - start] = elevation >= LOW_SUN_MIN_DEG && elevation <= LOW_SUN_MAX_DEG ? 1 : 0;
  }
  return low;
}

/** The profile samples of the Sky openness sector over the minutes `start` to `end`. */
export function opennessSector(track: SunTrack, start: number, end: number): Int32Array {
  let least = Infinity;
  let greatest = -Infinity;
  for (let m = start; m < end; m++) {
    least = Math.min(least, track.azimuth[m]!);
    greatest = Math.max(greatest, track.azimuth[m]!);
  }
  const first = Math.ceil((least - OPENNESS_SECTOR_MARGIN_DEG) * SAMPLES_PER_DEG);
  const last = Math.floor((greatest + OPENNESS_SECTOR_MARGIN_DEG) * SAMPLES_PER_DEG);
  return Int32Array.from({ length: last - first + 1 }, (_, i) => wrap(first + i, PROFILE_SAMPLES));
}

/**
 * One Candidate's Sky openness: the sector sky-view fraction, the mean of
 * cos^2(max(h, 0)) over the profile samples of `sector` (`opennessSector`):
 * the sun path's true azimuth range, widened by 10 degrees each side, ends
 * included.
 */
export function skyOpenness(codes: Uint8Array, sector: Int32Array): number {
  let sum = 0;
  for (const sample of sector) {
    sum += OPEN_SKY_OF_CODE[codes[sample]!]!;
  }
  return sum / sector.length;
}

/** The runs of 1 in `mask` as [first index, index after the last]. */
export function runs(mask: Uint8Array): [number, number][] {
  const out: [number, number][] = [];
  let from = -1;
  for (let i = 0; i <= mask.length; i++) {
    const on = i < mask.length && mask[i] === 1;
    if (on && from < 0) {
      from = i;
    } else if (!on && from >= 0) {
      out.push([from, i]);
      from = -1;
    }
  }
  return out;
}
